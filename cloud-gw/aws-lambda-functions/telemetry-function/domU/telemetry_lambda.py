#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-
# Client used for fetching data from the remote server

"""
Copyright 2021 NXP
"""

import datetime
import json
import logging
import os
import sys
import threading
import time

from remote_client import RemoteClient
from greengrasssdk import client

# Telemetry parameters
# time interval between MQTT packets
TELEMETRY_INTERVAL = "telemetry_interval"

# M7 core status query time
M7_STAT_QUERY_TIME = "m7_status_query_time_interval"

# M7 core status window size multiplier
# Used for getting M7 core load
M7_WINDOW_SIZE_MULTIPLIER = "m7_window_size_multiplier"

# server commands
GET_STATS_COMMAND="GET_STATS"
SET_PARAMS_COMMAND="SET_PARAMS"

# default gap between telemetry packets
TELEMETRY_SEND_INTERVAL = 1

# Locks for telemetry variable and socket
LOCK = threading.Lock()
SOCKET_COM_LOCK = threading.Lock()

# Setup logging to stdout.
LOGGER = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

# Creating a Greengrass core sdk client.
GGC_CLIENT = client("iot-data")

def __extract_parameter(event, parameter_name, parameter_type, min_value, default):
    """
    Extracts parameters from an event dictionary. If the event does not
    contain the desired value, the default is returned
    :param event: Event in json format
    :param parameter_name: Parameter name which shall be a key in the
    event dictionary
    :param parameter_type: Parameter type (int, float)
    :param min_value: Minimum accepted value
    :param default: Parameter default (in case the event does not contain
    the desired parameter, this value will be returned
    :return: updated parameter value/default
    """
    updated_param_value = event.get(parameter_name, default)
    # if the type is not correct, cast the parameter
    if not isinstance(updated_param_value, parameter_type):
        try:
            # cast to the expected format
            updated_param_value = parameter_type(updated_param_value)
        except ValueError:
            updated_param_value = default
    if updated_param_value != default:
        if updated_param_value < min_value:
            updated_param_value = default
        else:
            LOGGER.info("Updated %s", parameter_name.replace("_", " "))
    return updated_param_value

def telemetry_run():
    """
    This function is called every telemetry_interval seconds. In each
    call it sends an MQTT messages containing the host device's stats,
    a timestamp and the device name.
    """
    stats = dict()

    with SOCKET_COM_LOCK:
        system_telemetry = SOCKET.send_request(GET_STATS_COMMAND)

    if system_telemetry:
        # Set timestamp for current telemetry packet
        stats["Timestamp"] = int(time.time())
        stats["Datetime"] = str(datetime.datetime.fromtimestamp(int(time.time())))

        try:
            stats.update(json.loads(system_telemetry))
            try:
                GGC_CLIENT.publish(
                    topic=os.environ.get('telemetryTopic'),
                    queueFullPolicy="AllOrException",
                    payload=json.dumps(stats),
                )
            except Exception as exception:  # pylint: disable=broad-except
                LOGGER.error("Failed to publish message: %s", repr(exception))

        except ValueError:
            LOGGER.error("Malformed packet received from socket %s", system_telemetry)
    else:
        LOGGER.error("Did not receive packets from remote server")

    with LOCK:
        telemetry_interval = TELEMETRY_SEND_INTERVAL


    # Asynchronously schedule this function to be run again.
    threading.Timer(telemetry_interval, telemetry_run).start()

def function_handler(event, _):
    """
    This handler is used to update the telemetry_interval and to publish
    the board's uuid to the AWS console.

    :param event: The MQTT message in json format.
    :param context: A Lambda context object, it provides information.
    """
    # pylint: disable=global-statement
    global TELEMETRY_SEND_INTERVAL

    with LOCK:
        TELEMETRY_SEND_INTERVAL = \
            __extract_parameter(event=event, parameter_name=TELEMETRY_INTERVAL,
                                parameter_type=int, min_value=1,
                                default=TELEMETRY_SEND_INTERVAL)

    # Check if one or more config values have been updated.
    if set(event.keys()).intersection(
            set({TELEMETRY_INTERVAL, M7_STAT_QUERY_TIME, M7_WINDOW_SIZE_MULTIPLIER})):
        LOGGER.info("Got update event.")
        with SOCKET_COM_LOCK:
            SOCKET.send_fire_and_forget(SET_PARAMS_COMMAND + json.dumps(event))


# Start executing the function above.
# It will be executed every telemetry_interval seconds indefinitely.
#
SOCKET = RemoteClient()
telemetry_run()
