#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Script used for starting the AWS IOT FleetWise engine on the S32G board
Copyright 2022-2023 NXP
"""
import argparse
import os
import subprocess
from utils import Utils


class FleetWiseDeploy:
    """ Wrapper class for AWS IOT FleetWise deployment """
    CONFIG_PATH = "/etc/aws-iot-fleetwise/"
    CONFIG_FILE = "goldvip-config.json"

    def __init__(self, netif, archive=""):
        """
        Checks the existing configuration on the board, verifies connectivity
        and updates date and time
        :param netif: Network interface used to connect to the cloud.
        :param archive: Input archive containing the certificates and the private key
        generated in cloud.
        """
        self.__netif = netif
        self.__archive = archive
        if self.__archive:
            self.deploy_config_archive()

        self.check_config()
        self.check_connection()
        Utils.sync_system_datetime()

    def deploy_config_archive(self):
        """
        Un-tars the configuration archive in the CONFIG_PATH directory
        """
        print(f"Copying the configuration files to {self.CONFIG_PATH}...")
        if not os.path.exists(self.__archive):
            raise Exception(f"Input archive does not exist: {self.__archive}")

        try:
            subprocess.check_output([f'tar -xf {self.__archive} -C {self.CONFIG_PATH}'],
                                    shell=True)
        except subprocess.CalledProcessError as err:
            raise Exception(f"Failed to untar the input archive to {self.CONFIG_PATH}") from err

    def check_config(self):
        """
        Checks if the configuration file is available in the rootfs
        of the board
        """
        print("Checking configuration files...")
        if not os.path.exists(os.path.join(self.CONFIG_PATH, self.CONFIG_FILE)):
            raise Exception(f"Expected FleetWise config json file {self.CONFIG_FILE} "
                            f"does not exist in {self.CONFIG_PATH}, please provide the "
                            f"archive as input to the script")

    def check_connection(self):
        """
        Checks whether an internet connection is available for the
        interface.
        """
        print("Checking the internet connection...")
        interfaces = os.listdir('/sys/class/net/')
        if self.__netif not in interfaces:
            raise Exception(f"Invalid interface received, expected a member "
                            f"of the list: {interfaces}")

        try:
            subprocess.check_output([f'ping 8.8.8.8 -I {self.__netif} -c 4'], shell=True)
        except subprocess.CalledProcessError as err:
            raise Exception(f"Could not detect an active internet connection on the "
                            f"{self.__netif} interface, please connect the associated phy "
                            f"and run `udhcpc -i {self.__netif}`") from err
        print("Network connected!")

    @staticmethod
    def start_fleetwise():
        """
        Starts the fleetwise engine on the S32G board
        """
        os.system("service aws-iot-fwe restart")


def main():
    """ Parse the arguments and setup FleetWise. """
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                     description='Starts AWS IOT FleetWise on the board')
    parser.add_argument('--netif', dest='netif', type=str, default='xenbr0',
                        help='The network interface used to connect to open internet.')
    parser.add_argument('--input-archive', dest='archive_path', type=str, default="",
                        help='The input archive containing the FleetWise certificates.'
                             'If not provided, the system will check if previous deployments'
                             'were made.')

    args = parser.parse_args()
    FleetWiseDeploy(args.netif, args.archive_path).start_fleetwise()


# entry point
if __name__ == '__main__':
    main()
