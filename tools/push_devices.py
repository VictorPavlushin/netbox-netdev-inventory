#!/usr/bin/env python3

import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import getpass
import json
import logging
import socket
import sys
import argparse
from boltons.cacheutils import LRU
from netboxapi import NetboxAPI, NetboxMapper
from netbox_netdev_inventory.config import get_config
import requests
import yaml


def parse_args():
    parser = argparse.ArgumentParser(
        description="Push devices and models to netbox"
    )
    parser.add_argument(
        "devices", metavar="devices", type=str,
        help="Yaml file containing a definition of devices to poll"
    )
    parser.add_argument(
        "role", metavar="role", type=int,
        help="Device role id to use"
    )
    parser.add_argument(
        "site", metavar="site", type=int,
        help="Site id to use"
    )
    parser.add_argument(
        "--types", metavar="device_types",
        type=str, help="Yaml file containing a definition of device types"
    )
    parser.add_argument(
        "--threads",
        help="number of threads to run",
        dest="threads", default=10, type=int
    )
    parser.set_defaults(func=push_devices)

    arg_parser = parser
    args = arg_parser.parse_args()

    if hasattr(args, "func"):
        args.func(parsed_args=args)
    else:
        arg_parser.print_help()
        sys.exit(1)


def push_devices(parsed_args):
    netbox_api = NetboxAPI(**get_config()["netbox"])
    manufacturers = create_manufacturers(netbox_api)

    if parsed_args.types:
        try:
            create_device_types(
                netbox_api, parse_yaml_file(parsed_args.types),
                manufacturers,
            )
        except requests.exceptions.HTTPError as e:
            print(e.response.json())
            raise

    create_devices(
        netbox_api, parse_yaml_file(parsed_args.devices),
        threads=parsed_args.threads, role_id=parsed_args.role,
        site_id=parsed_args.site
    )


def parse_yaml_file(yaml_file):
    with open(yaml_file) as yaml_str:
        return yaml.safe_load(yaml_str)


def create_manufacturers(netbox_api):
    mapper = NetboxMapper(netbox_api, "dcim", "manufacturers")
    manufacturers = {}

    for name in ("Cisco", "Juniper"):
        name = str(name)
        try:
            manufacturer = next(mapper.get(slug=name.lower()))
        except StopIteration:
            manufacturer = mapper.post(name=name, slug=name.lower())

        manufacturers[name.lower()] = manufacturer

    return manufacturers


def create_devices(netbox_api, devices, role_id, site_id, threads=10):
    device_types_mapper = NetboxMapper(netbox_api, "dcim", "device-types")
    platforms_mapper = NetboxMapper(netbox_api, "dcim", "platforms")
    caches = {
        "device_types": LRU(
            on_miss=lambda slug: next(device_types_mapper.get(slug=slug))
        ),
        "platforms": LRU(
            on_miss=lambda slug: next(platforms_mapper.get(slug=slug))
        )
    }
    device_mapper = NetboxMapper(netbox_api, "dcim", "devices")

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = []
        for name, props in devices.items():
            future = executor.submit(
                _thread_push_device, device_mapper, caches, name, props,
                role_id, site_id
            )
            futures.append(future)

        try:
            [future.result() in concurrent.futures.as_completed(futures)]
        except requests.exceptions.HTTPError as e:
            print(e.response.data)
            raise


def _thread_push_device(device_mapper, caches, device, props,
                        role_id, site_id):
    device_type = props.pop("model")
    platform = props.pop("platform", None)

    name = str(device)
    try:
        device = next(device_mapper.get(name=name.lower()))
    except StopIteration:
        device = device_mapper.post(
            name=name, slug=name.lower(),
            device_type=caches["device_types"][device_type.lower()],
            device_role=role_id, site=site_id,
        )

    update_netbox_obj_from(device, props)
    if platform:
        device.platform = caches["platforms"][platform.lower()]
    device.put()


def create_device_types(netbox_api, types, manufacturers):
    mapper = NetboxMapper(netbox_api, "dcim", "device-types")
    for name, props in types.items():
        manufacturer_name = props.pop("manufacturer")

        name = str(name)
        try:
            t = next(mapper.get(slug=name.lower()))
        except StopIteration:
            t = mapper.post(
                model=name, slug=name.lower(),
                manufacturer=manufacturers[manufacturer_name]
            )

        update_netbox_obj_from(t, props)
        # Until issue #2272 is fixed on netbox
        t.__upstream_attrs__.remove("subdevice_role")
        t.put()

        create_device_type_interfaces(
            netbox_api, manufacturer_name, t, props["ports"]
        )


def create_device_type_interfaces(netbox_api, manufacturer,
                                  device_type, ports):
    mapper = NetboxMapper(netbox_api, "dcim", "interface-templates")

    for port_type, nb in ports.items():
        if nb > 1:
            start = 1 if manufacturer == "cisco" else 0
            port_names = (
                "{}/{}".format(port_type, i) for i in range(start, nb + start)
            )
        else:
            port_names = (port_type, )

        upstream_ports = {
            p.name for p in mapper.get(devicetype_id=device_type)
        }
        for name in port_names:
            if name not in upstream_ports:
                mapper.post(name=name, device_type=device_type)


def update_netbox_obj_from(netbox_obj, values):
    for k, v in values.items():
        setattr(netbox_obj, k, v)

    return netbox_obj


if __name__ == "__main__":
    parse_args()
