#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-
# Application data collector server.
# Implements a socket on localhost.
# Receives data from local sources and sends them to the cloud.

"""
Copyright 2022 NXP
"""

import json
import threading
import traceback

from remote_server import RemoteServer

class AppDataCollectorServer(RemoteServer):
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
        RemoteServer.__init__(
            self,
            max_clients=max_clients,
            server_config_filename=server_config_filename)
        self.__data = {}

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
        # pylint: disable=broad-except
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
