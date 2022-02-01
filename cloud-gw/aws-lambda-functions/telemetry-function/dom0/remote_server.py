#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-
# Generic collector server.

"""
Copyright 2021-2022 NXP
"""

import ipaddress
import socket
import os
import time

from abc import ABC, abstractmethod

class RemoteServer(ABC):
    """
    Generic server listener, this class covers the basic functionality of a socket:
    create and accept incoming connections.
    This abstract class is meant to be extended and not used directly.
    """

    # pylint: disable=too-many-arguments
    def __init__(self,
                 port=None, host=None,
                 buffer_size=None,
                 max_clients=1,
                 server_config_filename=None):
        """
        Class constructor
        :param port: Port on which the server waits for incoming connections.
        :param host: Server ip.
        :param buffer_size: Send-receive buffer size.
        :param max_clients: Maximum number of concurrent clients.
        :param server_config_filename: Name of the server configuration file.
        """
        self.__sock = None
        self.__conn = None
        self.__port = port
        self.__receive_buffer_size = buffer_size

        server_config = {}
        if server_config_filename:
            server_config = RemoteServer.__get_server_configuration(server_config_filename)
            self.__port = int(server_config['server_port'])
            self.__receive_buffer_size = int(server_config['buffer_size'])

        self.__host = server_config.get('server_address', host)
        self.__max_clients = max_clients

        self.__create_socket()

    @staticmethod
    def __get_server_configuration(server_config_filename):
        """
        Retrieves the server configuration from the server_config file
        :param server_config_filename: the server configuration filename
        :return: dictionary containing the configuration parameters
        """
        server_config = dict.fromkeys(["server_address", "server_port", "buffer_size"])
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               server_config_filename), 'r', encoding="utf-8") as file_:
            for line in file_:
                for key in server_config:
                    if key in line:
                        # get config from configuration file
                        server_config[key] = line.split("=")[-1].strip()

        # check whether all configurations are present
        if not all(server_config.values()):
            raise Exception(f"Failed to retrieve configuration for server: found {server_config}")
        try:
            ipaddress.ip_address(server_config["server_address"])
            int(server_config["server_port"])
            int(server_config["buffer_size"])
        except ValueError as exc:
            raise Exception(f"Invalid IP address provided {server_config}") from exc

        return server_config

    def __create_socket(self):
        """
        This method creates a socket by binding it to the hostname and the port
        given in the constructor.If the socket cannot be created (either the IP
        is not configured for local interfaces or the port is in use)
        the script retries every 10 seconds.
        """
        while True:
            try:
                self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.__sock.bind((self.__host, self.__port))
                self.__sock.listen(self.__max_clients)
                break
            # pylint: disable=broad-except
            except BaseException as exc:
                print(f"Failed to open the socket for {self.__host}:{self.__port} {repr(exc)}")
                time.sleep(10)

    def __accept(self):
        """
        This method waits for data to be received from clients.
        This method shall be called in a loop in order to have server
        listening continuously for new connections.
        :return: data received from the client
        """
        self.__conn, _ = self.__sock.accept()
        return self.__conn.recv(self.__receive_buffer_size).decode()

    def send(self, data):
        """
        Sends data to client
        :param data: Payload to be send to the client.
        """
        self.__conn.send(data.encode())

    def run(self):
        """
        Class runnable, will be called whenever the user wants to start the server listener
        """
        while True:
            received_data = self.__accept()
            self.dispatch(received_data)

    @abstractmethod
    def dispatch(self, data):
        """
        Abstract dispatch method.
        :param data: Data received from client.
        """
