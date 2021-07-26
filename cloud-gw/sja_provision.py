#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Retrieves from the cloud and sends the provisioning data to the
SJA application via sockets.
Provisioning data implies: aws endpoint, sja thing name, sja thing
certificates, mqtt topic, greengrass ip, greengrass certificate authority

Copyright 2021 NXP
"""

import socket
import subprocess
import struct
import tarfile

from io import BytesIO
from scapy.all import srp
from scapy.layers.l2 import ARP, Ether

import boto3

from utils import Utils

# pylint: disable=too-many-instance-attributes
class SjaProvisioningClient():
    """ Implements the client which sends the provisioning data to the server on SJA. """

    # Port used for connection, must match that used by the server on the SJA side.
    SJA_PORT = 8080

    def __init__(self, cfn_stack_name, aws_region_name, netif, sja_hwaddr='00:04:9f:06:12:00'):
        """
        :param cfn_stack_name: The name of the deployed CloudFormation stack.
        :param aws_region_name: The AWS region where the stack was deployed.
        :param netif: The network interface used to connect to open internet.
        :param sja_hwaddr: Mac address of SJA1110, it must match the address
                           configured in the SJA application.
        """
        self.aws_endpoint = None
        self.thing_name = None
        self.greengrass_ca = None
        self.greengrass_ip = None
        self.greengrass_mask = None
        self.sja_ip_addr = None

        self.certificates_keys = {
            'certs/certificate.private.key': None,
            'certs/certificate.pem': None,
        }

        self.topic = "s32g/sja/switch/" + cfn_stack_name

        # Check if the AWS credentials were provided
        if boto3.session.Session().get_credentials() is None:
            raise Exception('There are no AWS credentials defined. '
                            'Please define them via environment variables.')

        boto3.setup_default_session(region_name=aws_region_name)

        self.cfn_stack_name = cfn_stack_name
        self.netif = netif

        self.sja_hwaddr = sja_hwaddr

    def __get_endpoint_and_thing(self):
        """
        Retrieves the cloud endpoint and set the thing name.
        """
        self.aws_endpoint = boto3.client('iot').describe_endpoint(
            endpointType='iot:Data-ATS'
        )['endpointAddress']

        print("Retrieved endpoint: %s" % self.aws_endpoint)

        # Set the sja thing name
        self.thing_name = self.cfn_stack_name + "_SjaThing"

    def __extract_certificate(self):
        """
        Extract the thing certificate from certificate s3 bucket
        created by the CFN stack.
        """
        s3_client = boto3.client('s3')
        cfn_client = boto3.client('cloudformation')

        cfn_stack_outputs = Utils.pull_stack_outputs(
            cfn_client,
            self.cfn_stack_name)

        s3_bucket_name = Utils.get_cfn_output_value(cfn_stack_outputs, 'CertificateBucket')

        Utils.check_certificates_tarball(s3_client, s3_bucket_name, Utils.SJA_CERTIFICATE)

        gzip = BytesIO()
        s3_client.download_fileobj(s3_bucket_name, Utils.SJA_CERTIFICATE, gzip)
        gzip.seek(0)

        with tarfile.open(fileobj=gzip, mode='r:gz') as tar:
            for member in tar.getmembers():
                if member.name in self.certificates_keys:
                    self.certificates_keys[member.name] = tar.extractfile(member).read()

        if not all(self.certificates_keys.values()):
            raise Exception("One or more certificates couldn't be found.")

        print("Retrieved certificates.")

    def __get_greengrass_ca(self):
        """
        Get the public Certificate Authority of the greengrass group.
        """
        gg_client = boto3.client('greengrass')

        group_id = None
        group_ca_id = None

        # Find the group id
        groups = gg_client.list_groups()

        for group in groups['Groups']:
            if self.cfn_stack_name in group['Name']:
                group_id = group['Id']
                break

        if group_id is None:
            raise Exception("Group Id not found.")

        # Find group CA id
        group_cas = gg_client.list_group_certificate_authorities(
            GroupId=group_id
        )

        group_ca_id = group_cas['GroupCertificateAuthorities'][0]['GroupCertificateAuthorityId']

        if not group_ca_id:
            raise Exception("Group CA not found.")

        certificate_authority = gg_client.get_group_certificate_authority(
            CertificateAuthorityId=group_ca_id,
            GroupId=group_id
        )

        self.greengrass_ca = certificate_authority['PemEncodedCertificate']

        print("Greengrass certificate authority retrieved.")

    def __get_greengrass_ip(self):
        """
        Get the local network ip.
        """
        out = str(subprocess.check_output(['ip', '-o', '-f', 'inet', 'a', 's', self.netif]))
        ip_and_mask = out.partition('inet')[2].strip().split()[0]
        self.greengrass_ip, _, self.greengrass_mask = ip_and_mask.partition('/')

        print("Local network ip found: %s" % self.greengrass_ip)

    def __find_sja_ip(self):
        """
        Discovers SJA1110 knowing its mac address, and saves its ip address.
        """
        arp_request = ARP(pdst=f"{self.greengrass_ip}/{self.greengrass_mask}")
        brodcast = Ether(dst="ff:ff:ff:ff:ff:ff")
        arp = brodcast / arp_request
        answered = srp(arp, timeout=20, verbose=False)[0]

        for element in answered:
            if self.sja_hwaddr in element[1].hwsrc:
                self.sja_ip_addr = element[1].psrc
                print(f"Found sja1110 ip address: {self.sja_ip_addr}")
                return

        raise Exception("Could not find ip address of SJA1110.")

    def send(self):
        """
        Create a connection to the client running on the sja1110 and provision
        the application with the aws endpoint, thing name, certificates, and topic.
        """
        sock = socket.socket()
        ack = "OK"

        # Connect to the SJA local server
        sock.connect((self.sja_ip_addr, SjaProvisioningClient.SJA_PORT))

        outbound_data = [
            bytes(self.aws_endpoint, 'utf-8'),
            bytes(self.thing_name, 'utf-8'),
            self.certificates_keys['certs/certificate.private.key'],
            self.certificates_keys['certs/certificate.pem'],
            bytes(self.topic, 'utf-8'),
            bytes(self.greengrass_ca, 'utf-8'),
            bytes(self.greengrass_ip, 'utf-8')
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
        self.__get_greengrass_ip()
        self.__find_sja_ip()
        self.__get_endpoint_and_thing()
        self.__extract_certificate()
        self.__get_greengrass_ca()
        self.send()
