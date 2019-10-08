from collections import defaultdict
from contextlib import ContextDecorator
import logging
import socket
import napalm

from netbox_netdev_inventory.exceptions import (
    NoReverseFoundError, DeviceNotSupportedError
)
from netbox_netdev_inventory.vendors import DeviceParsers, StubParser
from netbox_netdev_inventory.tools import is_macaddr

logger = logging.getLogger("netbox_importer")


class DeviceImporter(ContextDecorator):

    def __init__(self, hostname, napalm_driver_name, target=None, creds=None,
                 napalm_optional_args=None, discovery_protocol='lldp'):
        self.hostname = hostname
        if not creds:
            creds = (None, None)
        self.target = target or hostname

        driver = napalm.get_network_driver(napalm_driver_name)
        self.device = driver(
            hostname=self.target, username=creds[0], password=creds[1],
            optional_args=napalm_optional_args
        )
        self.specific_parser = self._get_specific_device_parser(
            napalm_driver_name
        )
        self.discovery_protocol = discovery_protocol
        self.napalm_driver_name = napalm_driver_name

    def _get_specific_device_parser(self, os):
        try:
            parser_class = getattr(DeviceParsers, os).value
        except AttributeError:
            logger.info(
                "{} is not totally supported, will be limited to napalm "
                "features"
            )
            parser_class = StubParser

        return parser_class(self.device)

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        if self.device.device:
            self.close()

    def open(self):
        self.device.open()

    def close(self):
        self.device.close()

    def poll(self):
        assert self.device.device

        props = {}

        logging.debug("Trying to resolve the primaries IP")
        try:
            props.update(self.resolve_primary_ip())
        except NoReverseFoundError:
            logger.error(
                "Cannot fill primary ip for host %s, no reverse found.",
                self.hostname
            )

        try:
            props.update(self._handle_serial_num())
        except DeviceNotSupportedError:
            logger.error(
                "Cannot fetch serial, device %s not supported", self.hostname
            )

        self._handle_interfaces_props(props)

        return props

    def resolve_primary_ip(self):
        """
        Resolve primary IPs from hostname

        :return: {"primary_ipv4": ipv4, "primary_ipv6": ipv6}, each key will
                 exist if a reverse exists for this host
        """
        main_ip = {}

        assoc_proto_socket = (
            ("primary_ip4", socket.AF_INET), ("primary_ip6", socket.AF_INET6)
        )
        for proto, socket_type in assoc_proto_socket:
            try:
                main_ip[proto] = socket.getaddrinfo(
                    self.hostname, None, socket_type
                )[0][4][0]
            except socket.gaierror as e:
                logger.debug(
                    "Error resolving a reverse for %s for family %s: %s",
                    self.hostname, socket_type, e
                )

        if not main_ip:
            raise NoReverseFoundError(self.hostname)

        return main_ip

    def _handle_serial_num(self):
        assert self.device.device

        try:
            serial = self.device.get_facts()["serial_number"]
        except IndexError:
            raise DeviceNotSupportedError(self.hostname)

        return {"serial": serial} if serial else {}

    def _handle_interfaces_props(self, props):
        logger.debug("Get properties of each interface")
        interfaces = self.get_interfaces()
        logger.debug("Get IP setup on each interface")
        interfaces = self.fill_interfaces_ip(interfaces)

        props["interfaces"] = interfaces
        return props

    def get_interfaces(self):
        assert self.device.device

        napalm_interfaces = self.device.get_interfaces()

        interfaces = {}
        trunks = []
        # sort to test it more easily
        for ifname, napalm_ifprops in sorted(napalm_interfaces.items()):
            is_subif, parent_if = self._is_subinterface(ifname)
            if is_subif:
                trunks.append(parent_if)
                continue

            if not is_macaddr(napalm_ifprops["mac_address"]):
                napalm_ifprops["mac_address"] = None

            _type = self.specific_parser.get_interface_type(ifname)
            if _type == "Other":
                logger.info("Switch %s iface type for the port %s not defined.",
                            self.hostname, ifname)
            try:
                mode = {
                    "access": "Access",
                    "trunk": "Tagged",
                    "static access": "Access",
                    None: None
                }[self.specific_parser.get_interface_mode(ifname)]
            except NotImplementedError:
                mode = None
            except KeyError as ex:
                logger.debug("Switch %s Interface %s unknown mode: %s.",
                             self.hostname, ifname, ex)
                mode = None

            interfaces[ifname] = {
                "enabled": napalm_ifprops["is_enabled"],
                # Netbox max descr size is 100 char
                "description": (
                    napalm_ifprops["description"] or ""
                )[:100],
                "mac_address": napalm_ifprops["mac_address"] or None,
                # wait for this pull request
                # https://github.com/napalm-automation/napalm/pull/531
                "mtu": napalm_ifprops.get("mtu", None),
                "type": _type,
                "mode": mode,
                "untagged_vlan": None,
                "tagged_vlans": [],
            }

            if mode == "Access":
                try:
                    interfaces[ifname]["untagged_vlan"] = \
                        self.specific_parser.get_interface_access_vlan(ifname)
                except NotImplementedError:
                    interfaces[ifname]["untagged_vlan"] = None

            try:
                vlans = self.specific_parser.get_interface_vlans(ifname)
            except NotImplementedError:
                vlans = None

            if vlans:
                interfaces[ifname]["tagged_vlans"] = vlans


        for ifname, data in interfaces.items():
            if data["mode"] == "Tagged":
                try:
                    navive = self.specific_parser.get_interface_netive_vlan(ifname)
                except NotImplementedError:
                    navive = None
                if navive in data["tagged_vlans"]:
                    interfaces[ifname]["untagged_vlan"] = navive
                    interfaces[ifname]["tagged_vlans"].pop(navive)

        for trunk in trunks:
            if trunk in interfaces:
                interfaces[trunk]["mode"] = "Tagged"

        interfaces_lag = self.specific_parser.get_interfaces_lag(interfaces)
        for ifname, lag in interfaces_lag.items():
            try:
                real_lag_name = (
                    self._search_key_case_insensitive(interfaces, lag)
                )
            except KeyError:
                logger.error("%s not exist in polled interfaces", lag)
                continue

            interfaces[ifname]["lag"] = real_lag_name
            interfaces[real_lag_name]["type"] = (
                "Link Aggregation Group (LAG)"
            )

        return interfaces

    def _is_subinterface(self, interface):
        ifsplit = interface.split(".")
        if len(ifsplit) > 1 and ifsplit[0].lower() != "vlan":
            return True, ifsplit[0]
        else:
            return False, interface

    def _search_key_case_insensitive(self, dictionary, key):
        if key in dictionary:
            return key

        for k in dictionary.keys():
            if k == key or isinstance(key, str) and k.lower() == key.lower():
                return k

        raise KeyError()

    def fill_interfaces_ip(self, interfaces=None):
        assert self.device.device

        if interfaces is None:
            interfaces = defaultdict(dict)
            skip_unlisted_if = False
        else:
            skip_unlisted_if = True

        for ifname, ifprops in self.device.get_interfaces_ip().items():
            is_subif, parent_if = self._is_subinterface(ifname)
            if is_subif:
                ifname = parent_if

            if skip_unlisted_if and ifname not in interfaces:
                logger.debug(
                    "Interface {} has IP but was not listed".format(ifname)
                )
                continue

            if not interfaces[ifname].get("ip"):
                interfaces[ifname]["ip"] = []

            interfaces[ifname]["ip"].extend(
                "{}/{}".format(ip, ip_props["prefix_length"])
                for proto in ("ipv4", "ipv6")
                if ifprops.get(proto, None)
                for ip, ip_props in ifprops[proto].items()
            )

        return interfaces

    def get_neighbours(self):
        """
        Either try the specific way to get lldp, cdp neighbours, or try using napalm
        if not supported

        :return neighbours: [{
                "local_port": local port name,
                "hostname": neighbour hostname (if handled),
                "port": neighbour port name,
                "mgmt_id": neighbour id # only with specific parser
            }]
        """
        assert self.device.device
        if self.discovery_protocol == "cdp":
            yield from self.get_cdp_neighbours()
        elif self.discovery_protocol == "multiple" and \
                self.napalm_driver_name in ['ios', 'nxos', 'nxos_ssh']:
            yield from self.get_multiple_neighbours()
        else:
            yield from self.get_lldp_neighbours()

    def get_multiple_neighbours(self):
        neighbours = [n for n in self.get_cdp_neighbours()]
        for n in self.get_lldp_neighbours():
            if not any(self.specific_parser.get_abrev_if(elem['local_port']) \
                       == self.specific_parser.get_abrev_if(n['local_port']) \
                       for elem in neighbours):
                yield n
        for n in neighbours:
            yield n

    def get_cdp_neighbours(self):
        """
        Either try the specific way to get cdp neighbours

        :return neighbours: [{
                "local_port": local port name,
                "hostname": neighbour hostname (if handled),
                "port": neighbour port name,
            }]
        """
        try:
            yield from self.specific_parser.get_detailed_cdp_neighbours()
        except NotImplementedError:
            logger.error("%s platform does not support cdp", self.platform)
            return []

    def get_lldp_neighbours(self):
        """
        Either try the specific way to get lldp neighbours, or try using napalm
        if not supported

        :return neighbours: [{
                "local_port": local port name,
                "hostname": neighbour hostname (if handled),
                "port": neighbour port name,
                "mgmt_id": neighbour id # only with specific parser
            }]
        """

        try:
            yield from self.specific_parser.get_detailed_lldp_neighbours()
        except NotImplementedError:
            napalm_neighbours = self.device.get_lldp_neighbors()
            for port, port_neighbours in napalm_neighbours.items():
                for neighbour in port_neighbours:
                    yield {
                        "local_port": port,
                        "hostname": neighbour["hostname"],
                        "port": neighbour["port"]
                    }
