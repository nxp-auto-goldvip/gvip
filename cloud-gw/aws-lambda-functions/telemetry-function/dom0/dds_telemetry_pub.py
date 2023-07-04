#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-
# Telemetry collector server.
# Implements a DDS publisher on top of the V2XBR bridge.
# Sends telemetry data to clients running on a different Virtual Machine

"""
Copyright 2022-2023 NXP
"""
import logging
import os
import time
import sys
from telemetry_aggregator import TelemetryAggregator

import rticonnextdds_connector as rti

# Setup logging to stdout.
LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format="%(asctime)s|%(levelname)s| %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")

class DDSTelemetryPublisher():
    """
    A server used to collect telemetry data.
    """
    DDS_DOMAIN_PARTICIPANT = "TelemetryParticipantLibrary::TelemetryDom0Participant"
    DDS_WRITER = "TelemetryPublisher::TelemetryWriter"
    # Skew in seconds over which we reinitialize the DDS Writer.
    TIME_SKEW = 10

    def __init__(self):
        """
        Class constructor
        """
        self.__init_writer()
        self.timestamp_prev = None

    def __init_writer(self):
        """
        Initialize the DDS Writer.
        """
        rti_connector = rti.Connector(self.DDS_DOMAIN_PARTICIPANT,
                                      os.path.dirname(os.path.realpath(__file__)) + os.path.sep + "dds_telemetry.xml")
        self.__dds_writer = rti_connector.get_output(self.DDS_WRITER)
        LOGGER.info("Initialized DDS Writer")

    def __check_timestamp(self):
        """
        Check if the timestamp has increased more than TIME_SKEW,
        and if so reinitialize the DDS Writer.
        """
        if self.timestamp_prev and abs(time.time() - self.timestamp_prev) > 10:
            self.__init_writer()

        self.timestamp_prev = time.time()

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
            try:
                self.__check_timestamp()

                self.send(AGGREGATOR.get_stats())
                time.sleep(1)
            # pylint: disable=broad-exception-caught
            except Exception as exception:
                LOGGER.error("Failed to send data, exception: %s", exception)

if __name__ == "__main__":
    # Start the collector
    AGGREGATOR = TelemetryAggregator()
    AGGREGATOR.run()
    DDSTelemetryPublisher().run()
