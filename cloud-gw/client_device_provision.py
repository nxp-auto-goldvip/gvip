#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Retrieves the data required to provision a client device for it to
connect to the Greengrass core on v2xdomu.

The provisioning data is stored for subsequent connections.

Copyright 2022-2024 NXP
"""

import ipaddress
import json
import hashlib
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

from utils import Utils, GREENGRASS_ROOT_PATH


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
    GG_CA = "GG_CA"

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
            use_rpmb=False,
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
        :param use_rpmb: Use the OP-TEE RPMB secure storage to store the certificates.
        :param verbose: Verbosity flag.
        """

        cfn_stack_outputs = Utils.pull_stack_outputs(
            boto3.client('cloudformation'),
            cfn_stack_name)
        self.__ggv2_core_name = Utils.get_cfn_output_value(
            cfn_stack_outputs, 'CoreThingName')
        self.__s3_bucket_name = Utils.get_cfn_output_value(
            cfn_stack_outputs, 'CertificateBucket')

        self.__thing_name = thing_name
        self.__mqtt_topic = mqtt_topic
        self.__region = aws_region_name
        self.__device_port = device_port
        self.__mqtt_port = mqtt_port
        self.__clean_provision = clean_provision
        self.__time_sync = time_sync
        self.__verbose = verbose
        self.__use_rpmb = use_rpmb
        self.__gg_ip = None

        self.cert_pem_key, self.cert_priv_key, self.gg_ca_key = self.__compute_cert_keys()

        self.data = {}
        self.client_device_data = {}
        self.client_certificates = {
            self.cert_pem_key : None,
            self.cert_priv_key : None,
            self.gg_ca_key : None
        }

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

        self.__certs_archive = self.CERTS_ARCHIVE_TEMPLATE.substitute(thing=thing_name)

        if device_ip:
            self.client_device_data[self.DEVICE_IP] = device_ip
        elif device_hwaddr:
            self.client_device_data[self.DEVICE_MAC] = device_hwaddr
        else:
            # pylint: disable=broad-exception-raised
            raise Exception("Must provide either IP / MAC address of the device in the deployment configuration.")

    def __compute_cert_keys(self, maxlen=64):
        """
        Compile the names of the key certificates to be used in RPMB secure storage.
        The key used in RPMB has a maximum length of 64 characters.
        The key must include the thing name in order for keys from different stacks to be distinguishable,
        but the thing name contains the name fo the CFN stack, which can be of any length.
        If the keys exceed the maximum length, instead of using the thing name,
        a hash of the thing name is used.
        :param maxlen: maximum length of the key.
        """
        cert_pem_key = f"{self.__thing_name}/{self.CERT_PEM}"
        cert_priv_key = f"{self.__thing_name}/{self.CERT_PRIV}"
        gg_ca_key = f"{self.__thing_name}/{self.GG_CA}"

        if (len(cert_pem_key) >= maxlen or
                len(cert_priv_key) >= maxlen or
                len(gg_ca_key) >= maxlen):

            hash_m = hashlib.md5()
            hash_m.update(self.__thing_name.encode())
            thing_name_hashed = hash_m.hexdigest()[0:20]

            cert_pem_key = f"{thing_name_hashed}/{self.CERT_PEM}"
            cert_priv_key = f"{thing_name_hashed}/{self.CERT_PRIV}"
            gg_ca_key = f"{thing_name_hashed}/{self.GG_CA}"

        return cert_pem_key, cert_priv_key, gg_ca_key

    def __attach_thing_to_ggcore(self):
        """
        Associates the client device to the Greengrass core thing.
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
        if self.__use_rpmb:
            found_certs = True
            for key in [self.cert_pem_key, self.cert_priv_key]:
                cert = Utils.read_from_rpmb(key)
                if cert:
                    self.client_certificates[key] = cert
                else:
                    found_certs = False
                    break

            if found_certs:
                return
        elif (self.client_device_data.get(self.CERT, None) and
                self.client_device_data[self.CERT].get(self.cert_pem_key, None) and
                self.client_device_data[self.CERT].get(self.cert_priv_key, None)):
            self.client_certificates[self.cert_pem_key] = self.client_device_data[self.CERT][self.cert_pem_key]
            self.client_certificates[self.cert_priv_key] = self.client_device_data[self.CERT][self.cert_priv_key]
            return

        s3_client = boto3.client('s3')

        Utils.check_certificates_tarball(s3_client, self.__s3_bucket_name, self.__certs_archive)

        gzip = BytesIO()
        s3_client.download_fileobj(self.__s3_bucket_name, self.__certs_archive, gzip)
        gzip.seek(0)

        with tarfile.open(fileobj=gzip, mode='r:gz') as tar:
            for member in tar.getmembers():
                if member.name in [self.CERT_PRIV]:
                    self.client_certificates[self.cert_priv_key] = \
                        tar.extractfile(member).read().decode("utf-8")
                if member.name in [self.CERT_PEM]:
                    self.client_certificates[self.cert_pem_key] = \
                        tar.extractfile(member).read().decode("utf-8")

        if not all(self.client_certificates):
            # pylint: disable=broad-exception-raised
            raise Exception("One or more certificates couldn't be found.")

        # Saving the certificates to RPMB.
        if self.__use_rpmb:
            Utils.write_to_rpmb(self.cert_priv_key, self.client_certificates[self.cert_priv_key])
            Utils.write_to_rpmb(self.cert_pem_key, self.client_certificates[self.cert_pem_key])

        if self.__verbose:
            print("Retrieved certificates.")

    def __get_greengrass_ca_discovery(self, nb_retries=20, wait_time=5):
        """
        Get the public Certificate Authority of the greengrass core device via
        greengrass discover api.
        :param nb_retries: Number of times to retry fetching the Certificate Authority.
        :param wait_time: Wait time in seconds between retries.
        :return bool: Success or failure.
        """
        with tempfile.NamedTemporaryFile(mode="w+") as certpath, \
             tempfile.NamedTemporaryFile(mode="w+") as keypath:

            # Write the certificates to temporary files.
            certpath.write(self.client_certificates[self.cert_pem_key])
            keypath.write(self.client_certificates[self.cert_priv_key])

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
                    continue

                try:
                    # Save the Greengrass Certitficate Authority from the request.
                    response = json.loads(ret.text)
                    self.client_certificates[self.gg_ca_key] \
                        = response["GGGroups"][0]["CAs"][0]

                    if self.__verbose:
                        print("Greengrass certificate authority retrieved.")

                    # Saving the certificate to RPMB.
                    if self.__use_rpmb:
                        Utils.write_to_rpmb(self.gg_ca_key, self.client_certificates[self.gg_ca_key])

                    return True
                except KeyError:
                    time.sleep(wait_time)

                    if i < nb_retries - 1 and self.__verbose:
                        print("Certificate Authority not found, retrying...")

        return False

    def __get_greengrass_ca_local(self, nb_retries=60, wait_time=2):
        """
        Retrieve the Greengrass CA from local path.
        The CA is available after a successful deployment of the Greengrass core.

        :param nb_retries: Number of times to retry fetching the Certificate Authority.
        :param wait_time: Wait time in seconds between retries.
        :return bool: Success or failure.
        """
        gg_ca_local_path = f"{GREENGRASS_ROOT_PATH}/work/aws.greengrass.clientdevices.Auth/ca.pem"

        for i in range(nb_retries):
            try:
                with open(gg_ca_local_path, mode="r", encoding="utf-8") as ca:
                    self.client_certificates[self.gg_ca_key] = ca.read()

                return True
            except KeyError:
                time.sleep(wait_time)

                if i < nb_retries - 1 and self.__verbose:
                    print("Certificate Authority not found, retrying...")

        return False

    def __get_greengrass_ca(self):
        """
        Retrieve the Greengrass CA.
        First, it tries to retrieve it via the Greengrass Discovery APIs, from cloud.
        If this does not work, try to use the CA from local filesystem.

        The second option is used as a last resort as it is not oficially supported:
        https://github.com/awsdocs/aws-iot-greengrass-v2-developer-guide/issues/20
        """
        # Check if the Greengrass certificate authority was already downloaded.
        if self.__use_rpmb:
            cert = Utils.read_from_rpmb(self.gg_ca_key)
            if cert:
                self.client_certificates[self.gg_ca_key] = cert
                return
        elif (self.client_device_data.get(self.CERT, None) and
                self.client_device_data[self.CERT].get(self.gg_ca_key, None)):
            self.client_certificates[self.gg_ca_key] = self.client_device_data[self.CERT][self.gg_ca_key]
            return

        if self.__get_greengrass_ca_discovery() or self.__get_greengrass_ca_local():
            return

        # pylint: disable=broad-exception-raised
        raise Exception("Greengrass CA not found.")

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
            bytes(self.client_certificates[self.cert_priv_key], 'utf-8'),
            bytes(self.client_certificates[self.cert_pem_key], 'utf-8'),
            bytes(self.__mqtt_topic, 'utf-8'),
            bytes(self.client_certificates[self.gg_ca_key], 'utf-8'),
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
        if not self.__use_rpmb:
            self.client_device_data[self.CERT] = self.client_certificates

        with open(self.DATA_FILE, "w+", encoding="utf-8") as data_file:
            self.data[self.__thing_name] = self.client_device_data
            json.dump(self.data, data_file, indent=4)

    def execute(self):
        """
        Retrieves the required data to be provisioned to a client device.
        """
        self.__attach_thing_to_ggcore()

        self.__get_endpoint()
        self.__extract_certificate()
        self.__get_greengrass_ca()

        # Retrieve the device ip using the mac, only if the mac is specified.
        if self.client_device_data.get(self.DEVICE_MAC, None):
            self.__find_device_ip()
        else:
            # Find the local ip of the interface connected to the client device.
            self.__gg_ip = self.__find_local_ip()
            self.__update_connectivity_info()

        self.provision()
        self.save_data()
