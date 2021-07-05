#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-
# Telemetry collector server.
# Implements a socket on top of the V2XBR bridge.
# Sends telemetry data to clients running on a different Virtual Machine

"""
Copyright 2021 NXP
"""

import ipaddress
import socket
import os
import time

from telemetry_aggregator import TelemetryAggregator

class RemoteServer:
    """
    Generic server listener, this class covers the basic functionality of a socket:
    create and accept incoming connections.
    """
    # Known commands for the server
    GET_STATS_COMMAND = "GET_STATS"
    SET_PARAMS_COMMAND = "SET_PARAMS"
    # maximum simultaneous connections
    MAX_CLIENTS=1
    def __init__(self):
        """
        Class constructor
        """
        server_config = self.__get_server_configuration()
        # port on which the server waits for incoming connections
        self.__port = int(server_config["server_port"])
        # server ip
        self.__host = server_config["server_address"]
        # send-receive buffer size. If data size is bigger than this value
        # it will be trimmed
        self.__receive_buffer_size = int(server_config["buffer_size"])
        self.__sock = None
        self.__conn = None
        self.__create_socket()

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
            raise Exception ("Failed to retrieve configuration for server: found {0}".
                             format(server_config))
        try:
            ipaddress.ip_address(server_config["server_address"])
            int(server_config["server_port"])
            int(server_config["buffer_size"])
        except ValueError as exc:
            raise Exception("Invalid IP address provided {0}".
                            format(server_config)) from exc

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
                self.__sock.listen(self.MAX_CLIENTS)
                break
            # pylint: disable=broad-except
            except BaseException as exc:
                print ("Failed to open the socket for {0}:{1} {2}".
                       format(self.__host, self.__port, repr(exc)))
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

    def __send(self, data):
        """
        Sends data to client
        :return:
        """
        self.__conn.send(data.encode())

    def dispatch(self, data):
        """
        This method dispatches messages received from clients and depending on the message type,
        command will be processed accordingly
        :param data: command received from clients.
        """
        if not data:
            return

        if data.startswith(self.GET_STATS_COMMAND):
            # reply with stats
            self.__send(AGGREGATOR.get_stats())

        if data.startswith(self.SET_PARAMS_COMMAND):
            # update configuration parameters
            AGGREGATOR.update_configuration_parameters(
                data.replace(self.SET_PARAMS_COMMAND, ""))

    def run(self):
        """
        Class runnable, will be called whenever user wants to start the server listener
        """
        while True:
            received_data = self.__accept()
            self.dispatch(received_data)

if __name__ == "__main__":
    # Start telemetry collector
    AGGREGATOR = TelemetryAggregator()
    AGGREGATOR.run()
    RemoteServer().run()
