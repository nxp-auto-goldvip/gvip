#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-
# Telemetry collector server.
# Implements a DDS publisher on top of the V2XBR bridge.
# Sends telemetry data to clients running on a different Virtual Machine

"""
Copyright 2022 NXP
"""
import os
import time
from telemetry_aggregator import TelemetryAggregator

import rticonnextdds_connector as rti

class DDSTelemetryPublisher():
    """
    A server used to collect telemetry data.
    """
    DDS_DOMAIN_PARTICIPANT = "TelemetryParticipantLibrary::TelemetryDom0Participant"
    DDS_WRITER = "TelemetryPublisher::TelemetryWriter"
    def __init__(self):
        """
        Class constructor
        """
        rti_connector = rti.Connector(self.DDS_DOMAIN_PARTICIPANT,
                                      os.path.dirname(os.path.realpath(__file__)) + os.path.sep + "dds_telemetry.xml")
        self.__dds_writer = rti_connector.get_output(self.DDS_WRITER)

    def send(self, data):
        """
        Sends data to subscriber
        :param data: Payload to be sent to the subscriber.
        """
        self.__dds_writer.instance.set_string("stats", data)
        self.__dds_writer.write()

    def run(self):
        """
        Class runnable, will be called whenever the user wants to start sending data
        """
        while True:
            self.__dds_writer.instance.set_string("stats", AGGREGATOR.get_stats())
            self.__dds_writer.write()
            time.sleep(1)

if __name__ == "__main__":
    # Start the collector
    AGGREGATOR = TelemetryAggregator()
    AGGREGATOR.run()
    DDSTelemetryPublisher().run()
