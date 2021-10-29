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

import awsiot.greengrasscoreipc
from awsiot.greengrasscoreipc import client
from awsiot.greengrasscoreipc import model

from remote_client import RemoteClient

# Telemetry parameters
# time interval between MQTT packets
TELEMETRY_INTERVAL = "telemetry_interval"

# M7 core status query time
M7_STAT_QUERY_TIME = "m7_status_query_time_interval"

# M7 core status window size multiplier
# Used for getting M7 core load
M7_WINDOW_SIZE_MULTIPLIER = "m7_window_size_multiplier"

# server commands
GET_STATS_COMMAND = "GET_STATS"
SET_PARAMS_COMMAND = "SET_PARAMS"

# default gap between telemetry packets
TELEMETRY_SEND_INTERVAL = 1

# Locks for telemetry variable and socket
LOCK = threading.Lock()
SOCKET_COM_LOCK = threading.Lock()

# Setup logging to stdout
LOGGER = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

# Creating a interprocess comunication client
IPC_CLIENT = awsiot.greengrasscoreipc.connect()

def extract_parameter(message, parameter_name, parameter_type, min_value, default):
    """
    Extracts parameters from an message dictionary. If the message does not
    contain the desired value, the default is returned
    :param message: Event in json format
    :param parameter_name: Parameter name which shall be a key in the
    message dictionary
    :param parameter_type: Parameter type (int, float)
    :param min_value: Minimum accepted value
    :param default: Parameter default (in case the event does not contain
    the desired parameter, this value will be returned
    :return: updated parameter value/default
    """
    updated_param_value = message.get(parameter_name, default)
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
    stats = {}

    with SOCKET_COM_LOCK:
        system_telemetry = SOCKET.send_request(GET_STATS_COMMAND)

    if system_telemetry:
        # Set timestamp for current telemetry packet
        stats["Timestamp"] = int(time.time())
        stats["Datetime"] = str(datetime.datetime.fromtimestamp(int(time.time())))

        try:
            stats.update(json.loads(system_telemetry))
            operation = IPC_CLIENT.new_publish_to_iot_core()

            operation.activate(model.PublishToIoTCoreRequest(
                topic_name=os.environ.get('telemetryTopic'),
                qos=model.QOS.AT_LEAST_ONCE,
                payload=json.dumps(stats).encode(),
            ))

            try:
                operation.get_response().result(timeout=1.0)
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

class StreamHandler(client.SubscribeToIoTCoreStreamHandler):
    """A class for handling incoming MQTT events.
    """

    def on_stream_event(self, event: model.IoTCoreMessage) -> None:
        """
        Handling the incoming configuration event.
        """
        # pylint: disable=global-statement
        global TELEMETRY_SEND_INTERVAL

        try:
            message = json.loads(str(event.message.payload, "utf-8"))

            with LOCK:
                TELEMETRY_SEND_INTERVAL = \
                    extract_parameter(message=message, parameter_name=TELEMETRY_INTERVAL,
                                      parameter_type=int, min_value=1,
                                      default=TELEMETRY_SEND_INTERVAL)

            # Check if one or more config values have been updated.
            if set(message.keys()).intersection(
                    set({TELEMETRY_INTERVAL, M7_STAT_QUERY_TIME, M7_WINDOW_SIZE_MULTIPLIER})):
                LOGGER.info("Got update message.")
                with SOCKET_COM_LOCK:
                    SOCKET.send_fire_and_forget(SET_PARAMS_COMMAND + json.dumps(message))
        # pylint: disable=broad-except
        except Exception as exception:
            print(exception)


def listen_for_config():
    """ Subscribe to the MQTT configuration topic, listen and handle incoming
    configuration messages.
    """
    try:
        request = model.SubscribeToIoTCoreRequest()
        request.topic_name = os.environ.get('telemetryTopic') + "/config"
        request.qos = model.QOS.AT_MOST_ONCE
        handler = StreamHandler()
        operation = IPC_CLIENT.new_subscribe_to_iot_core(handler)
        future = operation.activate(request)

        # Wait for incoming configuration messages.
        future.result()

        # Keep this running forever
        while True:
            time.sleep(10)
    # pylint: disable=broad-except
    except Exception as exception:
        print(exception)
        # Close the connection and restart.
        operation.close()
        listen_for_config()


# pylint: disable=unused-argument
def function_handler(event, _):
    """To create a lambda function
    we need to specify a handler function.
    """

# Connect with the telemetry agregator service on dom0.
SOCKET = RemoteClient()

# Start executing the function above.
# It will be executed every telemetry_interval seconds indefinitely.
telemetry_run()

# Start listening for configuration messages on the configuration topic.
listen_for_config()
