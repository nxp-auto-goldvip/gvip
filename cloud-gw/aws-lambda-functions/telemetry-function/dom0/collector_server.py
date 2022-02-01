#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-
# Telemetry collector server.
# Implements a socket on top of the V2XBR bridge.
# Sends telemetry data to clients running on a different Virtual Machine

"""
Copyright 2022 NXP
"""

from telemetry_aggregator import TelemetryAggregator
from remote_server import RemoteServer

class CollectorServer(RemoteServer):
    """
    A server used to collect telemetry data.
    """
    # pylint:disable=too-few-public-methods
    # Known commands for the server
    GET_STATS_COMMAND = "GET_STATS"
    SET_PARAMS_COMMAND = "SET_PARAMS"

    def __init__(self, server_config_filename="server_config"):
        """
        Class constructor
        :param server_config_filename: Name of the server configuration file.
        """
        RemoteServer.__init__(
            self, server_config_filename=server_config_filename)

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
            self.send(AGGREGATOR.get_stats())

        if data.startswith(self.SET_PARAMS_COMMAND):
            # update configuration parameters
            AGGREGATOR.update_configuration_parameters(
                data.replace(self.SET_PARAMS_COMMAND, ""))

if __name__ == "__main__":
    # Start the collector
    AGGREGATOR = TelemetryAggregator()
    AGGREGATOR.run()
    CollectorServer().run()
