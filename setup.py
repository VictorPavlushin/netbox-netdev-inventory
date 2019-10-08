#!/usr/bin/env python3

from setuptools import setup, find_packages
import netbox_netdev_inventory

with open("README.rst") as readme_file:
    readme = readme_file.read()

requirements = [
    "appdirs", "cachetools", "defusedxml", "lxml", "napalm", "netboxapi",
    "simplejson", "tqdm"
]
setup_requirements = [
    "pytest-runner",
]
test_requirements = [
    "pytest", "pytest-cov", "pytest-mock",
]

setup(
    author=netbox_netdev_inventory.__author__,
    author_email=netbox_netdev_inventory.__email__,
    classifiers=[
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
    ],
    description="Microservice import into netbox devices in production",
    install_requires=requirements,
    long_description=readme,
    include_package_data=True,
    keywords="netbox_netdev_inventory",
    name="netbox_netdev_inventory",
    packages=find_packages(include=["netbox_netdev_inventory", "netbox_netdev_inventory.*"]),
    package_data={
        "netbox_netdev_inventory": ["templates/**"]
    },
    setup_requires=setup_requirements,
    test_suite="tests",
    tests_require=test_requirements,
    url="https://github.com/VictorPavlushin/netbox-netdev-inventory",
    version=netbox_netdev_inventory.__version__,
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'netbox-netdev-inventory = netbox_netdev_inventory.__main__:parse_args',
        ],
    }
)
