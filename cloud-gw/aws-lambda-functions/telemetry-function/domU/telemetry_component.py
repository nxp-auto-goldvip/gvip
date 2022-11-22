#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-
# Client used for fetching data from the remote server

"""
Copyright 2021-2022 NXP
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
# Verbosity flag
VERBOSE_FLAG = "verbose"
VERBOSE = False

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

def extract_parameter(message, parameter_name, parameter_type, default, min_value=None):
    """
    Extracts parameters from an message dictionary. If the message does not
    contain the desired value, the default is returned
    :param message: Event in json format
    :param parameter_name: Parameter name which shall be a key in the
    message dictionary
    :param parameter_type: Parameter type (int, float, bool)
    :param default: Parameter default (in case the event does not contain
    :param min_value: Minimum accepted value
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
    if min_value and updated_param_value != default:
        if updated_param_value < min_value:
            updated_param_value = default
        else:
            LOGGER.info("Updated %s", parameter_name.replace("_", " "))
    return updated_param_value

def publish_to_topic(topic, payload, qos=model.QOS.AT_LEAST_ONCE):
    """
    Publish a payload to an MQTT topic.
    :param topic: Mqtt topic.
    :param payload: Payload to be sent.
    :param qos: Quality of service.
    """
    try:
        operation = IPC_CLIENT.new_publish_to_iot_core()

        operation.activate(model.PublishToIoTCoreRequest(
            topic_name=topic,
            qos=qos,
            payload=payload,
        ))

        operation.get_response().result(timeout=1.0)
    # pylint: disable=broad-except
    except Exception as exception:
        LOGGER.error("Failed to publish message: %s", repr(exception))

# pylint: disable=too-many-branches
def telemetry_collect_and_publish(verbose=False):
    """
    :param verbose: Verbosity flag
    This function is called every telemetry_interval seconds.
    In each call it publishes MQTT messages for the system telemetry,
    idps data, and app data (if applicable).
    """
    with SOCKET_COM_LOCK:
        data = SOCKET.send_request(GET_STATS_COMMAND)

    try:
        data = json.loads(data.decode())

        system_telemetry = data.get('system_telemetry', None)
        app_data = data.get('app_data', None)
        idps_data = data.get('idps_stats', None)

        timestamp = time.time()
        # Set timestamp for current telemetry packet
        time_values = {"Timestamp": int(timestamp),
                       "Datetime": str(datetime.datetime.fromtimestamp(timestamp))}

        if system_telemetry:
            try:
                # Send the telemetry statistics.
                system_telemetry.update(time_values)
                publish_to_topic(
                    topic=os.environ.get('telemetryTopic'),
                    payload=json.dumps(system_telemetry).encode())
                if verbose:
                    LOGGER.info("Sent system telemetry to topic: %s data: %s",
                        os.environ.get('telemetryTopic'), system_telemetry)
            except ValueError:
                LOGGER.error("Malformed packet received from socket %s", system_telemetry)

        if idps_data:
            try:
                topic = f"{os.environ.get('telemetryTopic')}/idps"
                idps_data.update(time_values)
                publish_to_topic(
                    topic=topic,
                    payload=json.dumps(idps_data).encode())
                if verbose:
                    LOGGER.info("Sent IDSP data to topic: %s data: %s", topic, idps_data)
            except ValueError:
                LOGGER.error("Malformed packet received from socket %s", idps_data)

        if app_data:
            for topic_suffix, data_list in app_data.items():
                # If the topic suffix is None use the generic application data topic suffix
                if not topic_suffix:
                    topic_suffix = os.environ.get('AppDataTopicSuffix')

                topic = f"{os.environ.get('telemetryTopic')}/{topic_suffix}"

                for data in data_list:
                    # Add the timestamp to the data.
                    data["Timestamp"] = int(timestamp)
                    publish_to_topic(
                        topic=topic,
                        payload=json.dumps(data).encode())
                    if verbose:
                        LOGGER.info("Sent app data to topic: %s data: %s", topic, data)

    # pylint: disable=broad-except
    except Exception as exception:
        LOGGER.error("Failed to get telemetry: %s \nData received from dom0: %s", exception, data)


def telemetry_run():
    """
    This function loops every telemetry_interval seconds.
    In each loop it calls the telemetry_collect_and_publish function.
    """
    while True:
        loop_entry_time = time.time()

        with LOCK:
            telemetry_interval = TELEMETRY_SEND_INTERVAL
            verbose = VERBOSE

        telemetry_collect_and_publish(verbose=verbose)

        loop_exec_time = time.time() - loop_entry_time
        next_run = telemetry_interval - loop_exec_time

        # discard calculation in case the telemetry interval was spent
        # while running the function
        if next_run < 0:
            next_run = telemetry_interval

        # Sleep until the next call, taking into account
        # how much time has been spent while the function was executing
        time.sleep(next_run)


class StreamHandler(client.SubscribeToIoTCoreStreamHandler):
    """A class for handling incoming MQTT events.
    """

    def on_stream_event(self, event: model.IoTCoreMessage) -> None:
        """
        Handling the incoming configuration event.
        """
        # pylint: disable=global-statement
        global TELEMETRY_SEND_INTERVAL
        global VERBOSE

        try:
            message = json.loads(str(event.message.payload, "utf-8"))

            with LOCK:
                TELEMETRY_SEND_INTERVAL = \
                    extract_parameter(message=message, parameter_name=TELEMETRY_INTERVAL,
                                      parameter_type=int, default=TELEMETRY_SEND_INTERVAL,
                                      min_value=1)
                VERBOSE = \
                    extract_parameter(message=message, parameter_name=VERBOSE_FLAG,
                                      parameter_type=bool, default=VERBOSE)

            # Check if one or more config values have been updated.
            if set(message.keys()).intersection(
                    set({TELEMETRY_INTERVAL, VERBOSE_FLAG, M7_STAT_QUERY_TIME, M7_WINDOW_SIZE_MULTIPLIER})):
                LOGGER.info("Got update message.")
                with SOCKET_COM_LOCK:
                    SOCKET.send_fire_and_forget(SET_PARAMS_COMMAND + json.dumps(message))
        # pylint: disable=broad-except
        except Exception as exception:
            LOGGER.error(exception)


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
        LOGGER.error(exception)
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
threading.Thread(target=telemetry_run).start()

# Start listening for configuration messages on the configuration topic.
listen_for_config()
