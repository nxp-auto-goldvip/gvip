#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-
# Client used for fetching data from the remote server

"""
Copyright 2021 NXP
"""

import ipaddress
import logging
import os
import socket
import sys
import time

# Setup logging to stdout.
LOGGER = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

class RemoteClient:
    """Class used for remote client abstraction."""
    def __init__(self):
        """
        :param port: port on which machine is listening
        :param host: server host ip
        """
        server_config = self.__get_server_configuration()
        self.__host = server_config["server_address"]
        self.__port = int(server_config["server_port"])
        self.__receive_buffer_size = int(server_config["buffer_size"])
        self.__socket = None
        # check that socket is available, if not, send a packet every
        # 10 seconds until the socket server becomes available
        while False is self.send_fire_and_forget("DUMMY_PACKET"):
            LOGGER.error("Server not available for %s:%s",
                         self.__host, self.__port)
            time.sleep(10)
        LOGGER.info("Succesfully connected to server %s:%s",
                    self.__host, self.__port)

    @staticmethod
    def __get_server_configuration():
        """
        Retrieves the server configuration from the server_config file
        :return: dictionary containing the configuration parameters
        """
        server_config = dict.fromkeys(["server_address", "server_port", "buffer_size"])
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "server_config"), 'r') as file_:
            for line in file_:
                for key in server_config:
                    if key in line:
                        # get config from configuration file
                        server_config[key] = line.split("=")[-1].strip()

        # check whether all configurations are present
        if not all(server_config.values()):
            err = "Failed to retrieve configuration for server: found {0}".format(server_config)
            LOGGER.error(err)
            raise Exception (err)
        try:
            ipaddress.ip_address(server_config["server_address"])
            int(server_config["server_port"])
            int(server_config["buffer_size"])
        except ValueError as exc:
            raise Exception("Invalid IP address provided {0}".
                            format(server_config)) from exc

        return server_config

    def __send(self, message_buffer, timeout=1):
        """Connects to the remote server and sends a command using a specific prefix.
        :param message_buffer: buffer which will be sent to remote machine
        :param timeout: receive command timeout, in order to avoid blocking calls on receive method
        :return True if message has been sent correctly, False otherwise
        """
        self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if timeout:
            self.__socket.settimeout(timeout)

        try:
            # Connection might not be stable, hence we connect every time for higher reliability
            self.__socket.connect((self.__host, self.__port))
            self.__socket.send(message_buffer.encode())
            return True
        # pylint: disable=broad-except
        except Exception:
            LOGGER.error("Failed to send message to %s:%s", self.__host, self.__port)
            return False


    def __receive(self):
        """
        Method used for receiving information from remote machine. In case timeout has
        been set, method will not return any output, in order to avoid blocking calls
        """
        try:
            received_buffer = self.__socket.recv(self.__receive_buffer_size)
        # pylint: disable=broad-except
        except Exception:
            LOGGER.error("Failed to receive any reply from server in time")
            return ''
        return received_buffer

    def send_fire_and_forget(self, message_buffer):
        """
        Sends a message to the server without waiting for a reply
        :param message_buffer: data message
        :return True if message has been sent correctly, False otherwise
        """
        return self.__send(message_buffer)

    def send_request(self, message_buffer):
        """
        Sends a message to the server and waits for a reply
        :param message_buffer: data message
        :return server reply/None
        """
        if True is self.__send(message_buffer):
            return self.__receive()
        return None


    def close(self):
        """This method closes a socket for reading and writing (receive and send operations)."""
        self.__socket.shutdown(socket.SHUT_WR)
        self.__socket.close()
