#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Auxiliary functions used for the provisioning scripts.

Copyright 2021-2024 NXP
"""

import ctypes
import os
import re
import subprocess
import time

GREENGRASS_ROOT_PATH = "/greengrass/v2/"


class Utils():
    """ Class containing general utility methods. """
    # Time in seconds used to wait for wpa_supplicant initialization.
    WPA_WAIT_TIME = 3

    # RPMB secure storage TA
    SEC_STORAGE_TA_SO = "optee_certificate_secure_storage.so"

    @staticmethod
    def execute_command(command, timeout=None):
        """
        Execute a command (process with arguments), capturing stdout, stderr and returns code.
        :param command: the command to execute
        :return: return code, stdout and stderr output
        """
        # pylint: disable=consider-using-with
        proc = subprocess.Popen(command, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, shell=True)

        try:
            std_out, std_err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            std_out, std_err = proc.communicate()

        if proc.returncode != 0:
            err_msg = f'Execution of command {command} resulted in error.\n'\
                      f'stdout: {std_out}\nstderr: {std_err}'
            raise Exception(err_msg)

        return proc.returncode, std_out, std_err

    @staticmethod
    def retry(func, retries, *args):
        """
        Retry the execution of a method (with arguments) on any exception.
        :param func: the function handler to execute
        :param retries: the number of retries to be made
        :param *args: the arguments used to call the function
        :return: value returned by the method
        """
        ret = None

        while retries:
            try:
                ret = func(*args)
            # pylint: disable=broad-exception-caught
            except Exception:
                retries -= 1
                time.sleep(5)
            else:
                break
        else:
            raise Exception(f'retry failed: {func.__name__}')

        return ret

    @staticmethod
    def setup_network_interface(netif, netip=None, setup_ifmetric=True):
        """
        Setup a given network interface to be used for internet connection.
        :param netif: the network interface name.
        :param netip: optional IP to be set statically on the given interface.
        :param setup_ifmetric: sets the ifmetric priorities
        """
        try:
            print('Checking the internet connection...')
            Utils.execute_command(f'ping -c4 -I{netif} 8.8.8.8')
        # pylint: disable=broad-exception-caught
        except Exception:
            print('Setting up the network interface...')

            # Bring up the given interface.
            Utils.execute_command(f'ip link set dev {netif} up')

            if netip:
                print('Setting up static IP address...')
                Utils.execute_command(f'ip address add {netip} dev {netif}')
            else:
                print('Getting an IP address using DHCP client...')
                Utils.execute_command(f'udhcpc -nq -i{netif} -t10')

        if setup_ifmetric:
            # Increase the route metric so the given network interface will be used by default for
            # access to open internet.
            print(f"Setting '{netif}' as the default network interface...")
            default_routes = Utils.execute_command('ip route show default to match 8.8.8.8')[1]
            for dev in re.findall(r"dev\s+(\S+)", default_routes.decode()):
                if dev != netif:
                    Utils.execute_command(f'ifmetric {dev} 1024')
            Utils.execute_command(f'ifmetric {netif} 0')

    @staticmethod
    def sync_system_datetime(sync_iface=None, ip_ver='v4'):
        """
        Force a system datetime update by restarting the ntp daemon.
        :param sync_iface: the network interface which is used to synchronize the NTP timedate.
        :param ip_ver: IP version (v4/v6/all).
        """
        ntpd_path = os.path.join('/usr', 'sbin', 'ntpd')
        ntpd_pid_filename = os.path.join('/var', 'run', 'ntpd.pid')

        restart_ntp_service = f'{ntpd_path} -u ntp:ntp -p {ntpd_pid_filename} -g'
        sync_system_timedate = f'{ntpd_path} -gq'

        if sync_iface and isinstance(sync_iface, str):
            sync_system_timedate += f" -I {sync_iface}"

        if ip_ver in ('v4', 'v6'):
            sync_system_timedate += " -4" if ip_ver == 'v4' else " -6"
        elif ip_ver != 'all':
            raise ValueError(f'Unrecognized IP version value: {ip_ver}')

        try:
            # Stop the ntp daemon, if it is running.
            Utils.execute_command('pkill ntpd || true')
            print('Synchronizing the system datetime with the ntp servers...')
            # Start the ntp to force the timedate sync.
            Utils.execute_command(sync_system_timedate, timeout=60)
        # pylint: disable=broad-exception-caught
        except Exception as exception:
            print(f'Datetime sync failed: {exception}')
        finally:
            # Re-establish the ntp service.
            Utils.execute_command(restart_ntp_service)

    @staticmethod
    def pull_stack_outputs(cfn_client, cfn_stack_name):
        """
        Return a list of the cloudformation stack outputs.
        :param cfn_client: boto3 cloudformation client.
        :param cfn_stack_name: cloudformation stack name.
        """
        matching_stacks = cfn_client.describe_stacks(StackName=cfn_stack_name)['Stacks']

        if len(matching_stacks) != 1:
            raise Exception(f"The '{cfn_stack_name}' CloudFormation stack does not exist.")

        return matching_stacks[0]['Outputs']

    @staticmethod
    def get_cfn_output_value(cfn_outputs, key):
        """
        Extract values from the CloufFormation stack's output list based on a given key.
        :param cfn_outputs: the outputs of CloudFormation stack.
        :param key: the OutputKey to search for.
        """
        matching_outputs = [output_data for output_data in cfn_outputs
                            if output_data['OutputKey'] == key]

        if len(matching_outputs) != 1:
            raise Exception(f"Couldn't find '{key}' in the output list.")

        return matching_outputs[0]['OutputValue']

    @staticmethod
    def check_certificates_tarball(s3_client, bucket_name, tar_name):
        """
        Check whether the specified bucket and tarball exists.
        :param s3_client: boto3 s3 client.
        :param bucket_name: name of the s3 bucket containing the certificates.
        :param tar_name: name of the tar object.
        """
        response = s3_client.head_bucket(Bucket=bucket_name)
        if response['ResponseMetadata']['HTTPStatusCode'] != 200:
            raise Exception(
                f"Bucket '{bucket_name}' does not exist or you don't have permission to access it.")

        bucket_contents = s3_client.list_objects(Bucket=bucket_name)['Contents']
        if len(bucket_contents) == 0:
            raise Exception("S3 bucket is empty.")

        for s3_object in bucket_contents:
            if s3_object['Key'] == tar_name:
                return tar_name

        raise Exception(f"Bucket {bucket_name} does not contain tarball {tar_name}.")

    @staticmethod
    def write_to_rpmb(key, data):
        """
        Call the optee_certificate_secure_storage Trusted Application
        to store a key:data pair in RPMB secure storage.
        :param key: The object key.
        :param data: The data to be written.
        """
        print(f"Writing certificate {key} to RPMB secure storage.")

        try:
            # Loading shared object
            c_lib = ctypes.CDLL(Utils.SEC_STORAGE_TA_SO)

            # Calling rpmb_put
            c_lib.rpmb_put.restype = ctypes.c_int
            ret = c_lib.rpmb_put(key.encode(), data.encode())

            if ret != 0:
                raise Exception(f"Failed to write key {key} to RPMB.")
        # pylint: disable=broad-exception-caught
        except Exception as exp:
            print(f"Failed to write to RPMB. Error: {exp}")

    @staticmethod
    def read_from_rpmb(key):
        """
        Call the optee_certificate_secure_storage Trusted Application
        to retrieve the data corresponding to a key from RPMB secure storage.
        :param key: The object key.
        """
        print(f"Retrieving certificate {key} from RPMB secure storage.")

        try:
            # Loading shared object
            c_lib = ctypes.CDLL(Utils.SEC_STORAGE_TA_SO)

            buffer_len = ctypes.c_int.in_dll(c_lib, "buffer_len").value

            # Calling rpmb_get
            c_lib.rpmb_get.restype = ctypes.c_int
            data = ctypes.create_string_buffer(buffer_len)
            ret = c_lib.rpmb_get(key.encode(), data)

            if ret < 0:
                print("Certificate not found in RPMB secure storage.")
                return None

            return data.value.decode('utf-8')
        # pylint: disable=broad-exception-caught
        except Exception as exp:
            print(f"Failed to read from RPMB. Error: {exp}")
            return None
