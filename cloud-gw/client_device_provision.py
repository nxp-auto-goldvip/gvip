#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Retrieves the data required to provision a client device for it to
connect to the greengrass core on v2xdomu.

The provisioning data is stored for subsequent connections.

Copyright 2022-2023 NXP
"""

import ipaddress
import json
import socket
import subprocess
import struct
import tarfile
import tempfile
import time
import os

from io import BytesIO
from string import Template

import requests
import boto3

from utils import Utils


# pylint: disable=too-many-instance-attributes
class ClientDeviceProvisioningClient():
    """
    Implements a client which sends the provisioning data to a client device.
    """
    # Keys for the client data dictionary.
    # The certificate which the client device uses to authentificate itself
    CERT = "certificate"
    CERT_PRIV = "certs/certificate.private.key"
    CERT_PEM = "certs/certificate.pem"
    # The AWS endpoing
    ENDPOINT = "AWS endpoint"
    # Greengrass certificate authority
    GG_CA = "Greengrass Certificate Authority"

    # We must provide either the client device's local ip or its
    # Hwaddr which we use to find its ip.
    DEVICE_IP = "Device ip"
    DEVICE_MAC = "Device mac"

    # Name of the client device data file
    DATA_FILE = "/home/root/cloud-gw/client_device_data.json"

    CERTS_ARCHIVE_TEMPLATE = Template("${thing}_certificates.tar.gz")

    # pylint: disable=too-many-arguments
    def __init__(
            self, thing_name,
            mqtt_topic, cfn_stack_name,
            aws_region_name,
            device_port, mqtt_port,
            device_ip=None, device_hwaddr=None,
            clean_provision=False,
            time_sync=False,
            verbose=True):
        """
        :param thing_name: Name of the Decive Thing to connect to.
        :param mqtt_topic: MQTT topic for the device.
        :param cfn_stack_name: Cloudformation stack name.
        :param aws_region_name: AWS region name.
        :param device_port: Eth port to connect to the device.
        :param mqtt_port: MQTT port.
        :param device_ip: IP address of the device thing.
        :param device_hwaddr: MAC address of the device thing.
        :param clean_provision: Forces the download of the provisioning data
                                even if it has already been downloaded.
        :param time_sync: Synchronize the date and time between the core and
                          client devices.
        :param verbose: Verbosity flag.
        """

        cfn_stack_outputs = Utils.pull_stack_outputs(
            boto3.client('cloudformation'),
            cfn_stack_name)
        self.__ggv2_core_name = Utils.get_cfn_output_value(
            cfn_stack_outputs, 'CoreThingName')
        self.__s3_bucket_name = Utils.get_cfn_output_value(
            cfn_stack_outputs, 'CertificateBucket')

        self.data = {}
        self.client_device_data = {}

        if os.path.exists(self.DATA_FILE):
            with open(self.DATA_FILE, "r", encoding="utf-8") as data_file:
                try:
                    self.data = json.load(data_file)
                except json.decoder.JSONDecodeError:
                    print("Invalid JSON string in client device configuration "
                          "data file. Re-creating the configuration.")
                    data_file.close()
                    os.remove(self.DATA_FILE)
                else:
                    self.client_device_data = self.data.get(thing_name, {})

        self.__thing_name = thing_name
        self.__mqtt_topic = mqtt_topic
        self.__region = aws_region_name
        self.__device_port = device_port
        self.__mqtt_port = mqtt_port
        self.__clean_provision = clean_provision
        self.__time_sync = time_sync
        self.__verbose = verbose
        self.__gg_ip = None

        self.__certs_archive = self.CERTS_ARCHIVE_TEMPLATE.substitute(thing=thing_name)

        if device_ip:
            self.client_device_data[self.DEVICE_IP] = device_ip
        elif device_hwaddr:
            self.client_device_data[self.DEVICE_MAC] = device_hwaddr
        else:
            # pylint: disable=broad-exception-raised
            raise Exception("Must provide either IP / MAC address of the device in the deployment configuration.")

    def __attach_thing_to_ggcore(self):
        """
        Associates the client device to the greengrass core thing.
        """
        ggv2_client = boto3.client('greengrassv2')

        ggv2_client.batch_associate_client_device_with_core_device(
            entries=[
                {
                    'thingName': self.__thing_name
                }
            ],
            coreDeviceThingName=self.__ggv2_core_name
        )

    @staticmethod
    def __get_netif_ip(netif, verbose):
        """
        Get the local network ip.
        :param netif: the network interface for which we get the ip.
        """

        out = str(subprocess.check_output(['ip', '-o', '-f', 'inet', 'a', 's', netif]))

        try:
            ip_and_mask = out.partition('inet')[2].strip().split()[0]
            ip_addr, _, mask = ip_and_mask.partition('/')
        except IndexError:
            if verbose:
                print(f"Interface {netif} has no ip.")
            return None, None

        if verbose:
            print(f"Found ip '{ip_addr}' for interface '{netif}'")
        return ip_addr, mask

    def __update_connectivity_info(self):
        """
        Update the connectivity information for the client devices of the
        Greengrass Core Device Thing.
        """
        connectivity_info = [
            {
                'HostAddress': f'{self.__gg_ip}',
                'Id': f'{self.__gg_ip}',
                'Metadata': '',
                'PortNumber': self.__mqtt_port
            }
        ]

        boto3.client('greengrass').update_connectivity_info(
            ConnectivityInfo=connectivity_info,
            ThingName=self.__ggv2_core_name
        )

        if self.__verbose:
            print("Updated Core connectivity information.")

    def __find_local_ip(self):
        """
        Find the IP address of the network interface connected to the device.
        :return: IP address as a string or None
        """
        netif_list = [
            (netif, *self.__get_netif_ip(netif, self.__verbose)) \
            for _, netif in socket.if_nameindex()
        ]

        for netif, ip_addr, mask in netif_list:
            if not ip_addr:
                continue

            if (ipaddress.ip_address(self.client_device_data[self.DEVICE_IP]) in
                    ipaddress.ip_network(f"{ip_addr}/{mask}", strict=False)):
                return ip_addr

        # pylint: disable=broad-exception-raised
        raise Exception("Could not find local ip address.")

    def __find_device_ip(self, nb_tries=4):
        """
        Discover the device ip knowing its mac address.
        :param nb_tries: number of tries to get the device ip.
        """
        # Check if the device ip was already found
        if (self.client_device_data.get(self.DEVICE_IP, None)
                and not self.__clean_provision):
            # If we have the device ip we still need the local ip
            self.__gg_ip = self.__find_local_ip()
            self.__update_connectivity_info()
            return

        # pylint: disable=import-outside-toplevel
        from scapy.all import srp
        from scapy.layers.l2 import ARP, Ether

        # List the network interfaces with their subnet ip and mask
        netif_list = [
            (netif, *self.__get_netif_ip(netif, self.__verbose)) \
            for _, netif in socket.if_nameindex()
        ]

        for i in range(nb_tries):
            for netif, ip_addr, mask in netif_list:
                if netif == 'lo' or not ip_addr:
                    continue

                try:
                    arp = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=f"{ip_addr}/{mask}")
                    answered = srp(arp, iface=netif, timeout=10 * (i + 1), verbose=True)[0]
                except OSError:
                    print("Network is down")
                    continue

                for element in answered:
                    if (self.client_device_data[self.DEVICE_MAC]
                            in element[1].hwsrc):
                        self.client_device_data[self.DEVICE_IP] = element[1].psrc
                        print(f"Found ip address: " \
                              f"{self.client_device_data[self.DEVICE_IP]} " \
                              f"of device {self.__thing_name}")

                        # Get the local ip for the network interface where
                        # we found the client device.
                        self.__gg_ip, _ = self.__get_netif_ip(netif, self.__verbose)
                        # Update conectivity information with the greengrass ip.
                        self.__update_connectivity_info()
                        return

                if i < nb_tries - 1 and self.__verbose:
                    print("Device ip not found, retrying...")

        # pylint: disable=broad-exception-raised
        raise Exception(f"Could not find ip address of device {self.__thing_name}.")

    def __get_endpoint(self):
        """
        Retrieves the cloud endpoint.
        """
        # Check if the endpoint has already been retrieved
        if (self.client_device_data.get(self.ENDPOINT, None)
                and not self.__clean_provision):
            return

        self.client_device_data[self.ENDPOINT] = \
            boto3.client('iot').describe_endpoint(endpointType='iot:Data-ATS')['endpointAddress']

        if self.__verbose:
            print(f"Retrieved endpoint: "\
                  f"{self.client_device_data[self.ENDPOINT]}")

    def __extract_certificate(self):
        """
        Extract the thing certificate from certificate s3 bucket
        created by the CFN stack.
        """
        # Check if the certificates were already downloaded.
        if (self.client_device_data.get(self.CERT, None)
                and not self.__clean_provision):
            return

        self.client_device_data[self.CERT] = {}

        s3_client = boto3.client('s3')

        Utils.check_certificates_tarball(s3_client, self.__s3_bucket_name, self.__certs_archive)

        gzip = BytesIO()
        s3_client.download_fileobj(self.__s3_bucket_name, self.__certs_archive, gzip)
        gzip.seek(0)

        with tarfile.open(fileobj=gzip, mode='r:gz') as tar:
            for member in tar.getmembers():
                if member.name in [self.CERT_PRIV, self.CERT_PEM]:
                    self.client_device_data[self.CERT][member.name] = \
                        tar.extractfile(member).read().decode("utf-8")

        if not all(self.client_device_data[self.CERT]):
            # pylint: disable=broad-exception-raised
            raise Exception("One or more certificates couldn't be found.")

        if self.__verbose:
            print("Retrieved certificates.")

    def __get_greengrass_ca(self, nb_retries=60, wait_time=10):
        """
        Get the public Certificate Authority of the greengrass core device via
        greengrass discover api.
        :param nb_retries: Number of times to retry fetching the Certificate Authority.
        :param wait_time: Wait time in seconds between retries.
        """
        # Check if the greengrass certificate authority was already downloaded.
        if (self.client_device_data.get(self.GG_CA, None)
                and not self.__clean_provision):
            return

        with tempfile.NamedTemporaryFile(mode="w+") as certpath, \
             tempfile.NamedTemporaryFile(mode="w+") as keypath:

            # Write the certificates to temporary files.
            certpath.write(self.client_device_data[self.CERT][self.CERT_PEM])
            keypath.write(self.client_device_data[self.CERT][self.CERT_PRIV])

            certpath.flush()
            keypath.flush()

            # Create the request url.
            url = f"https://greengrass-ats.iot.{self.__region}.amazonaws.com:8443"\
                  f"/greengrass/discover/thing/{self.__thing_name}"

            for i in range(nb_retries):
                try:
                    # Send the request with the certificate paths.
                    ret = requests.get(url, cert=(certpath.name, keypath.name), timeout=10)
                    ret.raise_for_status()
                except requests.exceptions.RequestException as err:
                    if self.__verbose:
                        print(f"The request for thing discovery failed (reason: {err}). "
                              "Retrying...")

                # Save the Greengrass Certitficate Authority from the request.
                response = json.loads(ret.text)
                try:
                    self.client_device_data[self.GG_CA] \
                        = response["GGGroups"][0]["CAs"][0]

                    if self.__verbose:
                        print("Greengrass certificate authority retrieved.")
                    return
                except KeyError:
                    time.sleep(wait_time)

                    if i < nb_retries - 1 and self.__verbose:
                        print("Certificate Authority not found, retrying...")

        # pylint: disable=broad-exception-raised
        raise Exception(f"Greengrass CA not found in request response: {response}")

    def provision(self):
        """
        Create a connection to the client running on the client devices and provision
        the application with the aws endpoint, thing name, certificates, and topic.
        """
        sock = socket.socket()
        ack = "OK"

        # Connect to the Device
        sock.connect((
            self.client_device_data[self.DEVICE_IP],
            self.__device_port))

        outbound_data = [
            bytes(self.client_device_data[self.ENDPOINT], 'utf-8'),
            bytes(self.__thing_name, 'utf-8'),
            bytes(self.client_device_data[self.CERT][self.CERT_PRIV], 'utf-8'),
            bytes(self.client_device_data[self.CERT][self.CERT_PEM], 'utf-8'),
            bytes(self.__mqtt_topic, 'utf-8'),
            bytes(self.client_device_data[self.GG_CA], 'utf-8'),
            bytes(self.__gg_ip, 'utf-8'),
        ]

        # Optional: ensure the time on the client devices is synchronized so
        # that certificates are valid
        if self.__time_sync:
            outbound_data.append(int(time.time()).to_bytes(4, 'little'))

        for data in outbound_data:
            payload_size = struct.pack("i", len(data))

            # First send the byte count of the data.
            sock.sendall(payload_size)

            # Send the data.
            sock.sendall(data)
            recv = sock.recv(len(ack))

            # Check for ACK.
            if recv != bytes(ack, 'utf-8'):
                sock.close()
                # pylint: disable=broad-exception-raised
                raise Exception(f"Send failed. Ack message: {recv}")

        if self.__verbose:
            print(f"Successfully provisioned device {self.__thing_name}")

        # close the connection
        sock.close()

    def save_data(self):
        """
        Saves the client data.
        """
        with open(self.DATA_FILE, "w+", encoding="utf-8") as data_file:
            self.data[self.__thing_name] = self.client_device_data
            json.dump(self.data, data_file, indent=4)

    def execute(self):
        """
        Retrieves the required data to be provisioned to a client device.
        """
        self.__attach_thing_to_ggcore()

        # Retrieve the device ip using the mac, only if the mac is specified.
        if self.client_device_data.get(self.DEVICE_MAC, None):
            self.__find_device_ip()
        else:
            # Find the local ip of the interface connected to the client device.
            self.__gg_ip = self.__find_local_ip()
            self.__update_connectivity_info()

        self.__get_endpoint()
        self.__extract_certificate()
        self.__get_greengrass_ca()
        self.provision()
        self.save_data()
