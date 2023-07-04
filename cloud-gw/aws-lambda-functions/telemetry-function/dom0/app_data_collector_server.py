#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-
# Application data collector server.
# Implements a socket on localhost.
# Receives data from local sources and sends them to the cloud.

"""
Copyright 2022-2023 NXP
"""

import ipaddress
import json
import os
import socket
import threading
import time
import traceback

class AppDataCollectorServer():
    """
    A server which serves as an entry point for local applications,
    allowing them to send data to AWS through the Cloud Gateway.
    """

    LOCK = threading.Lock()

    def __init__(self, max_clients=10, server_config_filename="local_server_config"):
        """
        Class constructor
        :param max_clients: Maximum number of concurrent clients.
        :param server_config_filename: Name of the server configuration file.
        """
        self.__sock = None
        self.__conn = None

        server_config = self.__get_server_configuration(server_config_filename)
        self.__port = int(server_config['server_port'])
        self.__receive_buffer_size = int(server_config['buffer_size'])

        self.__host = server_config.get('server_address')
        self.__max_clients = max_clients

        self.__create_socket()
        self.__data = {}

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

    def dispatch(self, data):
        """
        Receives data from an application and adds it to the
        dictionary of data waiting to be transmitted.
        An application can send data in the following format:
        {
            "app_data": <package> or <list of packages>,
            "mqtt_topic": <topic>
        }
        The mqtt_topic field is optional.
        :param data: The received data as a string.
        """

        if not data:
            return

        try:
            data = json.loads(data)

            with self.LOCK:
                if "app_data" in data:
                    # If no topic is specified the data will be sent to
                    # the application data mqtt topic.
                    topic = data.get("mqtt_topic_suffix", None)

                    # We keep a list of data payloads waiting to be
                    # transmitted for each unique topic.
                    # The payload can be a list of packages, or a single package.
                    if isinstance(data["app_data"], list):
                        data_list = data["app_data"]
                    else:
                        data_list = [data["app_data"]]

                    if topic in self.__data:
                        self.__data[topic].extend(data_list)
                    else:
                        self.__data[topic] = data_list
        # pylint: disable=broad-exception-caught
        except Exception:
            traceback.print_exc()
            print(f"Failed to parse data: {data}")

    def get_data(self):
        """
        Function called to retrieve the collected data.
        The data has the following format:
        {
            "mqtt topic 1": [payload 1, payload 2, ...],
            ...
        }
        """
        with self.LOCK:
            data = self.__data
            self.__data = {}
            if not data:
                return {}
            return {"app_data": data}

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
            # pylint: disable=broad-exception-caught
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
