#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-
# Client used for fetching data from the remote publisher

"""
Copyright 2021-2023 NXP
"""

import logging
import os
import sys
import time

import rticonnextdds_connector as rti

# Setup logging to stdout.
LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format="%(asctime)s|%(levelname)s| %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")

# pylint: disable=too-few-public-methods
class DDSTelemetrySubscriber:
    """Class used for remote client abstraction."""
    DDS_READER = "TelemetrySubscriber::TelemetryReader"
    # Skew in seconds over which we reinitialize the DDS Reader.
    TIME_SKEW = 10

    def __init__(self, dds_domain_participant):
        """
        Class constructor.
        :param dds_domain_participant: Name of the DDS participant.
        """
        self.dds_domain_participant = dds_domain_participant
        self.__init_reader()
        self.timestamp_prev = None

    def __init_reader(self):
        """
        Initialize the DDS Reader.
        """
        rti_connector = rti.Connector(self.dds_domain_participant,
                                      os.path.dirname(os.path.realpath(__file__)) + os.path.sep + "dds_telemetry.xml")
        self.__dds_reader = rti_connector.get_input(self.DDS_READER)

        # wait for the server to be available
        self.__dds_reader.wait()
        LOGGER.info("Initialized DDS Reader")

    def __check_timestamp(self):
        """
        Check if the timestamp has increased more than TIME_SKEW,
        and if so reinitialize the DDS reader.
        """
        if self.timestamp_prev and abs(time.time() - self.timestamp_prev) > self.TIME_SKEW:
            self.__init_reader()

        self.timestamp_prev = time.time()

    def receive(self, timeout=2000):
        """
        Method used for receiving information from remote machine. In case timeout has
        been set, method will not return any output, in order to avoid blocking calls
        :param timeout: receive command timeout in milliseconds, in order to avoid blocking calls on wait method
        """
        received_buffers = []

        self.__check_timestamp()

        try:
            self.__dds_reader.wait(timeout)
            self.__dds_reader.take()
            for sample in self.__dds_reader.samples.valid_data_iter:
                received_buffers.append(sample.get_string("stats"))
        except rti.TimeoutError:
            pass
        return received_buffers
