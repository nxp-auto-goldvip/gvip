#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-
# Client used for fetching data from the remote publisher

"""
Copyright 2023 NXP
"""

import logging
import os
import sys
import threading

import rticonnextdds_connector as rti

# Setup logging to stdout.
LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format="%(asctime)s|%(levelname)s| %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")

# pylint: disable=too-few-public-methods
class DDSLightsSubscriber:
    """Class used for DDS Lights subscriber."""
    DDS_READERS = ["LightsSubscriber::HeadLampReader",
                   "LightsSubscriber::RearLightReader",
                   "LightsSubscriber::HazardLightsReader",
                   "LightsSubscriber::LicensePlateLightReader",
                   "LightsSubscriber::StopLampReader"
                   ]

    def __init__(self, dds_domain_participant):
        """
        Class constructor.
        :param dds_domain_participant: Name of the DDS participant.
        """
        self.dds_domain_participant = dds_domain_participant
        self.__lock = threading.Lock()
        self.__init_reader()

    def __init_reader(self):
        """
        Initialize the DDS Reader and starts a thread for each topic.
        """
        threads = []
        rti_connector = rti.Connector(self.dds_domain_participant,
                                      os.path.dirname(os.path.realpath(__file__)) + os.path.sep + "rti_dds_lights.xml")
        self.__event = threading.Event()
        LOGGER.info("Initialized DDS Reader")

        for topic_name in self.DDS_READERS:
            dds_reader = rti_connector.get_input(topic_name)
            thr = threading.Thread(target=self.receive, args = (dds_reader, topic_name, 2000))
            thr.start()
            threads.append(thr)
        try:
            self.__event.wait()
        except KeyboardInterrupt:
            self.__event.set()
            for thr in threads:
                thr.join()
            rti_connector.close()

    def receive(self, reader, name, timeout=3000):
        """
        Method used for receiving information from M7. In case timeout has
        been set, method will not return any output, in order to avoid blocking calls
        :param reader: The DDS reader used to access the samples
        :param name: The name of the DDS reader
        :param timeout: receive command timeout in milliseconds, in order to avoid blocking calls on wait method
        """
        while not self.__event.is_set():
            try:
                reader.wait(timeout)
                with self.__lock:
                    reader.take()
                    for sample in reader.samples.valid_data_iter:
                        print(name, ': ', sample.get_dictionary())
            except rti.TimeoutError:
                LOGGER.info("Timeout %s", name)

if __name__ == "__main__":
    DDS_Sub = DDSLightsSubscriber(dds_domain_participant="LightsParticipantLibrary::LightsParticipant")
