#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2020-2021 NXP
"""

import json
import logging
import os
import platform
import sys
import threading

from datetime import datetime
from time import time
from threading import Timer

from greengrasssdk import client

from cpu_stats import CpuStats
from dev_mem_uid import get_uid
from mem_stats import MemStats
from net_stats import NetStats
from m7_stats import M7CoreMovingAverage

TELEMETRY_INTERVAL = "telemetry_interval"
M7_STATUS_QUERY_TIME_INTERVAL = "m7_status_query_time_interval"
M7_WINDOW_SIZE_MULTIPLIER = "m7_window_size_multiplier"

# This is a dict beacuse it needs to be a mutable object.
# A configuration file which contains:
# telemetry_interval: time in seconds between telemetry messages
# telemetry_topic: MQTT topic
# m7_status_query_time_interval: freqency of M7 core status queries per second
CONFIG = {}

with open("config.json") as config_file:
    CONFIG = json.load(config_file)

# Retrieving platform information to send from Greengrass Core.
MY_PLATFORM = platform.platform()

# These objects are global because they need to be persistent.
CS = CpuStats()
NS = NetStats(["pfe2", "pfe0"])
M7 = M7CoreMovingAverage(
    max_window_size=CONFIG[TELEMETRY_INTERVAL] / CONFIG[M7_STATUS_QUERY_TIME_INTERVAL],
    m7_status_query_time_interval=CONFIG[M7_STATUS_QUERY_TIME_INTERVAL])

M7.start()

# A lock for accesing the config variable.
LOCK = threading.Lock()

# Setup logging to stdout.
LOGGER = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

# Creating a greengrass core sdk client.
CLIENT = client("iot-data")


def stats_to_json():
    """
    Compiles a dictionary of all telemetry statistics.

    :returns: a string formatted as a json containing all our stats.
    :rtype: str
    """
    CS.step(process=True)
    NS.step()

    cpu_stats = CS.get_load(scale_to_percents=True)
    mem_stats = MemStats.get_telemetry(verbose=False)
    net_stats = NS.get_load()
    m7_stats = M7CoreMovingAverage.get_load()

    platform_name = {
        "Timestamp" : int(time()),
        "Datetime" : str(datetime.fromtimestamp(int(time()))),
        "Device" : MY_PLATFORM,
        "board_uuid_high" : get_uid()[0],
        "board_uuid_low" : get_uid()[1],
    }

    tot_stats = {
        **platform_name,
        **net_stats,
        **cpu_stats,
        **mem_stats,
        **m7_stats
    }

    return json.dumps(tot_stats)


def telemetry_run():
    """
    A function that runs indefineatly.

    This function is called every telemetry_interval seconds. In each
    call it sends an MQTT messages containing the host device's stats,
    a timestamp and the device name.
    """

    try:
        CLIENT.publish(
            topic=os.environ.get('telemetryTopic'),
            queueFullPolicy="AllOrException",
            payload=stats_to_json(),
        )
    except Exception as exception: # pylint: disable=broad-except
        LOGGER.error("Failed to publish message: %s", repr(exception))

    LOCK.acquire()
    telemetry_interval = CONFIG[TELEMETRY_INTERVAL]
    LOCK.release()

    # Asynchronously schedule this function to be run again.
    Timer(telemetry_interval, telemetry_run).start()


def update_measurements(event):
    """
    Check if the event contains new values for the configuration,
    and updates it accordingly.
    :param event: The MQTT message in json format.
    """
    if TELEMETRY_INTERVAL in event:
        telemetry_interval = event[TELEMETRY_INTERVAL]
        if not isinstance(telemetry_interval, int) or telemetry_interval <= 0:
            telemetry_interval = CONFIG[TELEMETRY_INTERVAL]
        else:
            LOCK.acquire()
            CONFIG[TELEMETRY_INTERVAL] = telemetry_interval
            LOCK.release()
            LOGGER.info("Updated Telemetry Interval")
    else:
        telemetry_interval = CONFIG[TELEMETRY_INTERVAL]

    if M7_STATUS_QUERY_TIME_INTERVAL in event:
        m7_status_query_time_interval = event[M7_STATUS_QUERY_TIME_INTERVAL]
        if (not isinstance(m7_status_query_time_interval, float)
                or m7_status_query_time_interval <= 0):
            m7_status_query_time_interval = CONFIG[M7_STATUS_QUERY_TIME_INTERVAL]
        else:
            CONFIG[M7_STATUS_QUERY_TIME_INTERVAL] = m7_status_query_time_interval
            LOGGER.info("Updated M7 query interval")
    else:
        m7_status_query_time_interval = CONFIG[M7_STATUS_QUERY_TIME_INTERVAL]

    if M7_WINDOW_SIZE_MULTIPLIER in event:
        m7_window_size_multiplier = event[M7_WINDOW_SIZE_MULTIPLIER]
        if not isinstance(m7_window_size_multiplier, int) or m7_window_size_multiplier <= 0:
            m7_window_size_multiplier = CONFIG[M7_WINDOW_SIZE_MULTIPLIER]
        else:
            CONFIG[M7_WINDOW_SIZE_MULTIPLIER] = m7_window_size_multiplier
            LOGGER.info("Updated m7 window size multiplier")
    else:
        m7_window_size_multiplier = CONFIG[M7_WINDOW_SIZE_MULTIPLIER]

    M7CoreMovingAverage.update_measurement(
        new_m7_status_query_time_interval=m7_status_query_time_interval,
        telemetry_interval=telemetry_interval,
        m7_window_size_multiplier=m7_window_size_multiplier)


def function_handler(event, _):
    """
    This handler is used to update the telemetry_interval and to publish
    the board's uuid to the AWS console.

    :param event: The MQTT message in json format.
    :param context: A Lambda context object, it provides information.
    """

    # If the event specifies this field we send the board uuid to the cloud.
    # The purpose is to easily interrogate the uuid of all connected boards.
    if "display_uuid" in event:
        try:
            uuid_dict = {
                "board_uuid_high" : get_uid()[0],
                "board_uuid_low" : get_uid()[1],
            }

            CLIENT.publish(
                topic=os.environ.get('telemetryTopic') + "/uuid",
                queueFullPolicy="AllOrException",
                payload=json.dumps(uuid_dict),
            )
        except Exception as exception: # pylint: disable=broad-except
            LOGGER.error("Failed to publish uuid: %s", repr(exception))

    # Check if one or more config values have been updated.
    if set(event.keys()).intersection(set({
            TELEMETRY_INTERVAL,
            M7_STATUS_QUERY_TIME_INTERVAL,
            M7_WINDOW_SIZE_MULTIPLIER})):

        LOGGER.info("Got update event.")
        update_measurements(event)

# Start executing the function above.
# It will be executed every telemetry_interval seconds indefinitely.
telemetry_run()
