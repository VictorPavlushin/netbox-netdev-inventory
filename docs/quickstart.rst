.. _quickstart:

==========
Quickstart
==========

.. currentmodule:: netbox_netprod_importer

Netbox should reflect the status of your production. Its philosophy is that
your production should be configured related to Netbox, but Netbox should not
be synced from what is currently running.

However, moving to Netbox can be complicated depending on the current knowledge
base. For this case, if you trust how your production is configured, Netbox can
be populated the 1st time from what is currently running, to then make Netbox
the single source of truth and base the production around it.

netbox-netprod-importer has 2 main functions:
  - :ref:`import devices data <import>`
  - :ref:`interconnect <interconnect>`

Import will fetch the current status of a list of devices. Interconnect will
build a graph of neighbours to create connections between each other inside
Netbox.


.. contents:: Table of Contents
   :depth: 3


Installation
------------

Run::

  pip3 install netbox_netprod_importer

Or by using setuptools::

  python3 ./setup.py install

netbox-netprod-importer is tested under python 3.4 to 3.7


Configuration
-------------

.. _quickstart_configuration:

The configuration is quite minimal yaml file::

    ########################
    #### Global options ####
    ########################

    ## Be more verbose ##
    verbose: None

    ## Disable ssl warnings in urllib3 ##
    disable_ssl_warnings: False


    ################
    #### Netbox ####
    ################

    netbox:
      # Netbox API URL
      url: "https://netbox.tld/api"
      # username: "user"
      # password: "password"
      # or to use a token instead
      token: "CHANGEME"


    ##########################
    #### Interconnections ####
    ##########################

    # On some devices, LLDP will expose the host FQDN. If devices are stored on
    # Netbox only by their hostname, the interconnection process will not be able
    # to find them. Fill this list to strip the domain name from exposed names.
    remove_domains:
      - "foo.tld"
      - "bar.tld"

    # vim: set ts=2 sw=2:

Adapt it and save it either as:

  - `~/.config/netbox-netprod-importer/config.yml`
  - `/etc/netbox-netprod-importer/config.yml`

Or can be set with the environment variable ``CONFIG_PATH``. Example:
``CONFIG_PATH=./config.yml netbox-netprod-importer …``

To turn off unverified HTTPS warning messages request:
`InsecureRequestWarning: Unverified HTTPS request is being made. Advised
verification verification is strongly advised. See:
https://urllib3.readthedocs.io/en/latest/advanced-usage.html#ssl-warnings
InsecureRequestWarning)`
In the configuration file, set the `disable_ssl_warnings` option to `True`
Default `False`


Device list
-----------

.. _quickstart_device_list:

To import the state of some devices, netbox-netprod-importer takes a yaml that
lists which hosts to target. One device is declared like the following::

    switch-fqdn:
      # Napalm driver name to use
      driver: napalm_driver_name
      # optional. Will be used instead of the switch fqdn to init the connection
      target: some_ip
      # optional. Only needed for interconnect
      discovery_protocol: lldp, cdp or multiple


Read the documentation of each subparser to use it in netbox-netprod-importer.

discovery_protocol can take the values "lldp", "cdp" or "multiple". Since the CDP protocol
is proprietary, it is only supported by CISSCO equipment. CDP detection only
works with nxos, nxos_ssh and ios drivers.

Filter
------

.. _quickstart_filter:

To import the status of some devices, netbox-netprod-importer accepts yaml,
which lists the criteria for selecting devices to target. It looks like this::

    #Mandatory section, but may be empty.
    #Used with interconnect and inventory.
    discovery_protocol:
        #[driver]: [discovery protocol]
        ios: cdp
        nxos: multiple
        nxos_ssh: multiple
        junos: lldp

    #Filter section, device selection criteria are prescribed.
    filter:
        q:
        region:
            - england
        site:
            - london
            - birmingham
        rack:
        status: 1
        role:
        tenant_group:
        tenant:
            - it
        manufacturer:
            - cisco
        device_type:
        mac_address:
        has_primary_ip: True
        platform:
        virtual_chassis_member:
        console_ports:
        console_server_ports:
        power_ports:
        power_outlets:
        interfaces:
        pass_through_ports:

Full online documentation on filter keys is available on a running NetBox instance
in /api/docs/, section GET /dcim/devices/
Most filter keys accept slug input

Mandatory in the platform you need to specify the NAPALM driver

Example
~~~~~~~

3 switches are wanted to be imported:

  - `switch-1.foo.tld`, which is a Cisco Nexus. The IP to target will be
    deduced by resolving the fqdn/hostname.
  - `switch-2.bar.tld`, which is a Juniper. `switch-2.bar.tld` does not
    resolve, so an IPv4 will be specified as target.
  - `switch-3.foo.tld`, which is a Cisco Nexus. The IP to target will be
    deduced by resolving the fqdn/hostname. And also determine the
    interconnect via cdp. The cdp protocol works so far with nxos,
    nxos_ssh and ios
  - `switch-4.foo.tld`, which is a Cisco Nexus. The IP to target will be
    deduced by resolving the fqdn/hostname. And also determine the
    interconnect via cdp and lldp. The `multiple` option only works for
    nxos, nxos_ssh and ios.


To declare 2 switches, define a yaml named `devices.yaml`::

    switch-1.foo.tld:
      driver: "nxos_ssh"

    switch-2.bar.tld:
      driver: "junos"
      target: "192.0.2.3"

    switch-3.foo.tld:
      driver: "nxos"
      discovery_protocol: "cdp"

    switch-4.foo.tld:
      driver: "nxos"
      discovery_protocol: "multiple"

Then to use it::

    $ netbox-netprod-importer import -f devices.yaml


Import and interconnect
-----------------------

Import is meant to import the state of some devices, like creating their
interfaces, attaching their IP, etc. The complete documentation and list of
feature can be found :ref:`here <import>`.

Import a list of devices::

    $ netbox-netprod-importer import -f devices.yaml

Once all devices interfaces are created, with the previous command, neighbours
can be discovered and interconnected between each other::

    $ netbox-netprod-importer interconnect -f devices.yaml

Full documentation for the interconnect feature can be found
:ref:`here <interconnect>`.

You can also run an inventory, which first starts the import and then the interconnect::

    $ netbox-netprod-importer inventory -F filter.yaml

