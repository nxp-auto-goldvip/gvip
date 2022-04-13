#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Retrieves from the cloud and sends the provisioning data to the
SJA application via sockets.
Provisioning data implies: aws endpoint, sja thing name, sja thing
certificates, mqtt topic, greengrass ip, greengrass certificate authority

Copyright 2021-2022 NXP
"""

import json
import socket
import subprocess
import struct
import tarfile
import tempfile
import time

from io import BytesIO

import requests
import boto3

from utils import Utils

# pylint: disable=too-many-instance-attributes
class SjaProvisioningClient():
    """ Implements the client which sends the provisioning data to the server on SJA. """

    # Port used for connection, must match that used by the server on the SJA side.
    SJA_PORT = 8080

    # Certificate tarball name.
    SJA_CERTIFICATE = "Sja_Certificate.tar.gz"

    # pylint: disable=too-many-arguments
    def __init__(
            self, cfn_stack_name,
            aws_region_name, netif,
            mqtt_port, sja_hwaddr='00:04:9f:06:12:00'):
        """
        :param cfn_stack_name: The name of the deployed CloudFormation stack.
        :param aws_region_name: The AWS region where the stack was deployed.
        :param netif: The network interface used to connect to open internet.
        :param mqtt_port: The port used by MQTT connections.
        :param sja_hwaddr: Mac address of SJA1110, it must match the address
                           configured in the SJA application.
        """
        self.__region = aws_region_name
        self.__netif = netif
        self.__mqtt_port = mqtt_port
        self.__sja_hwaddr = sja_hwaddr

        self.__aws_endpoint = None
        self.__greengrass_ca = None
        self.__greengrass_ip = None
        self.__sja_ip_addr = None

        self.__certificates_keys = {
            'certs/certificate.private.key': None,
            'certs/certificate.pem': None,
        }
        self.__topic = "s32g/sja/switch/" + cfn_stack_name
        self.__thing_name = cfn_stack_name + "_SjaThing"

        cfn_stack_outputs = Utils.pull_stack_outputs(
            boto3.client('cloudformation'),
            cfn_stack_name)

        self.__ggv2_core_name = Utils.get_cfn_output_value(cfn_stack_outputs, 'CoreThingName')
        self.__s3_bucket_name = Utils.get_cfn_output_value(cfn_stack_outputs, 'CertificateBucket')

    def __attach_sja_to_ggcore(self):
        ggv2_client = boto3.client('greengrassv2')

        ggv2_client.batch_associate_client_device_with_core_device(
            entries=[
                {
                    'thingName': self.__thing_name
                }
            ],
            coreDeviceThingName=self.__ggv2_core_name
        )

    def __get_endpoint(self):
        """
        Retrieves the cloud endpoint.
        """
        self.__aws_endpoint = boto3.client('iot').describe_endpoint(
            endpointType='iot:Data-ATS'
        )['endpointAddress']

        print(f"Retrieved endpoint: {self.__aws_endpoint}")

    def __update_connectivity_info(self):
        """
        Update the connectivity information for the client devices of the
        Greengrass Core Device Thing.
        """
        connectivity_info = [
            {
                'HostAddress': f'{self.__greengrass_ip}',
                'Id': f'{self.__greengrass_ip}',
                'Metadata': '',
                'PortNumber': self.__mqtt_port
            }
        ]

        boto3.client('greengrass').update_connectivity_info(
            ConnectivityInfo=connectivity_info,
            ThingName=self.__ggv2_core_name
        )

        print("Updated Core connectivity information.")

    def __extract_certificate(self):
        """
        Extract the thing certificate from certificate s3 bucket
        created by the CFN stack.
        """
        s3_client = boto3.client('s3')

        Utils.check_certificates_tarball(s3_client, self.__s3_bucket_name, self.SJA_CERTIFICATE)

        gzip = BytesIO()
        s3_client.download_fileobj(self.__s3_bucket_name, self.SJA_CERTIFICATE, gzip)
        gzip.seek(0)

        with tarfile.open(fileobj=gzip, mode='r:gz') as tar:
            for member in tar.getmembers():
                if member.name in self.__certificates_keys:
                    self.__certificates_keys[member.name] = tar.extractfile(member).read()

        if not all(self.__certificates_keys.values()):
            raise Exception("One or more certificates couldn't be found.")

        print("Retrieved certificates.")

    def __get_greengrass_ca(self, nb_retries=60, wait_time=10):
        """
        Get the public Certificate Authority of the greengrass core device via
        greengrass discover api.
        :param nb_retries: Number of times to retry fetching the Certificate Authority.
        :param wait_time: Wait time in seconds between retries.
        """
        with tempfile.NamedTemporaryFile(mode="w+") as certpath, \
             tempfile.NamedTemporaryFile(mode="w+") as keypath:

            # Write the SJA thing's certificate to temporary files.
            certpath.write(self.__certificates_keys['certs/certificate.pem'].decode("utf-8"))
            keypath.write(self.__certificates_keys['certs/certificate.private.key'].decode("utf-8"))

            certpath.flush()
            keypath.flush()

            # Create the request url.
            url = f"https://greengrass-ats.iot.{self.__region}.amazonaws.com:8443"\
                  f"/greengrass/discover/thing/{self.__thing_name}"

            for i in range(nb_retries):
                # Send the request with the certificate paths.
                ret = requests.get(url, cert=(certpath.name, keypath.name))

                # Save the Greengrass Certitficate Authority from the request.
                response = json.loads(ret.text)
                try:
                    self.__greengrass_ca = response["GGGroups"][0]["CAs"][0]

                    print("Greengrass certificate authority retrieved.")
                    return
                except KeyError:
                    time.sleep(wait_time)

                    if i < nb_retries - 1:
                        print("Certificate Authority not found, retrying...")

        raise Exception(f"Greengrass CA not found in request response: {response}")

    def __get_netif_ip(self, netif=None):
        """
        Get the local network ip.
        :param netif: the network interface for which we get the ip.
        """
        if not netif:
            netif = self.__netif

        out = str(subprocess.check_output(['ip', '-o', '-f', 'inet', 'a', 's', netif]))

        try:
            ip_and_mask = out.partition('inet')[2].strip().split()[0]
            ip_addr, _, mask = ip_and_mask.partition('/')
        except IndexError:
            print(f"Interface {netif} has no ip.")
            return None, None

        print(f"Found ip '{ip_addr}' for interface '{netif}'")
        return ip_addr, mask

    def __find_sja_ip(self, nb_tries=3):
        """
        Discovers SJA1110 knowing its mac address, and saves its ip address.
        :param nb_tries: number of tries to get the sja1110 ip.
        """

        # pylint: disable=import-outside-toplevel
        from scapy.all import srp
        from scapy.layers.l2 import ARP, Ether

        # List the network interfaces with their subnet ip and mask
        netif_list = [(netif, *self.__get_netif_ip(netif)) for _, netif in socket.if_nameindex()]

        for i in range(nb_tries):
            for netif, ip_addr, mask in netif_list:
                if netif == 'lo' or not ip_addr:
                    continue

                try:
                    arp_request = ARP(pdst=f"{ip_addr}/{mask}")
                    brodcast = Ether(dst="ff:ff:ff:ff:ff:ff")
                    arp = brodcast / arp_request
                    answered = srp(arp, iface=netif, timeout=20, verbose=True)[0]
                except OSError:
                    print("Network is down")
                    continue

                for element in answered:
                    if self.__sja_hwaddr in element[1].hwsrc:
                        self.__sja_ip_addr = element[1].psrc
                        print(f"Found sja1110 ip address: {self.__sja_ip_addr}")
                        return

                if i < nb_tries - 1:
                    print("SJA1110 ip not found, retrying...")

        raise Exception("Could not find ip address of SJA1110.")

    def send(self):
        """
        Create a connection to the client running on the sja1110 and provision
        the application with the aws endpoint, thing name, certificates, and topic.
        """
        sock = socket.socket()
        ack = "OK"

        # Connect to the SJA local server
        sock.connect((self.__sja_ip_addr, SjaProvisioningClient.SJA_PORT))

        outbound_data = [
            bytes(self.__aws_endpoint, 'utf-8'),
            bytes(self.__thing_name, 'utf-8'),
            self.__certificates_keys['certs/certificate.private.key'],
            self.__certificates_keys['certs/certificate.pem'],
            bytes(self.__topic, 'utf-8'),
            bytes(self.__greengrass_ca, 'utf-8'),
            bytes(self.__greengrass_ip, 'utf-8')
        ]

        for data in outbound_data:
            payload_size = struct.pack("i", len(data))

            # First send the byte count of the data.
            sock.sendall(payload_size)

            # Send the data.
            sock.sendall(data)
            recv = sock.recv(len(ack))

            # Check for ACK.
            if recv == bytes(ack, 'utf-8'):
                print("Data sent and acknowledged was received.")
            else:
                print(f"Send failed. Ack message: {recv}")
                break

        # close the connection
        sock.close()

    def execute(self):
        """
        Get and set the fields and then send them to the sja1110 application.
        """
        self.__attach_sja_to_ggcore()
        self.__greengrass_ip, _ = self.__get_netif_ip()
        self.__update_connectivity_info()
        self.__find_sja_ip()
        self.__get_endpoint()
        self.__extract_certificate()
        self.__get_greengrass_ca()
        self.send()
