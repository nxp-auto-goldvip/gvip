#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-
# Client used for fetching data from the remote server

"""
Copyright 2021-2023 NXP
"""

import datetime
import json
import logging
import numbers
import os
import sys
import threading
import time

import awsiot.greengrasscoreipc
from awsiot.greengrasscoreipc import client
from awsiot.greengrasscoreipc import model

from dds_telemetry_sub import DDSTelemetrySubscriber

# Telemetry parameters
# time interval between MQTT packets
TELEMETRY_INTERVAL = "telemetry_interval"

# Verbosity flag
VERBOSE_FLAG = "verbose"
VERBOSE = False

# default gap between telemetry packets
TELEMETRY_SEND_INTERVAL = 1

# Locks for telemetry variable and socket
LOCK = threading.Lock()

# Setup logging to stdout
LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format="%(asctime)s|%(levelname)s| %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")

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
    the desired parameter, this value will be returned
    :param min_value: Minimum accepted value
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
    # pylint: disable=broad-exception-caught
    except Exception as exception:
        LOGGER.error("Failed to publish message: %s", repr(exception))

#pylint: disable=too-many-locals
def aggregate_telemetry(telemetry_data):
    """
    This function parses multiple instances of the telemetry dict and aggregates the data in a single dict
    :param telemetry_data: List that contains the telemetry data to be aggregated.
    """

    # We must "merge" all the instance of the statistics received
    # Initialize the CAN IDPS and APP Data dicts with default values
    can_idps_data = {"global_stats": {"m7_anomalies": 0, "llce_anomalies": 0}, "idps_data": []}
    app_data = {}
    # It will collect all the system telemetry data that represent an average value (e.g. CPU Load)
    avg_dict = {}
    # It will collect all the system telemetry data that are supposed to be summed over an interval (e.g. PFE
    # packets)
    count_dict = {}
    # Iterate through all the received DDS messages
    for msg in telemetry_data:
        stats = json.loads(msg)
        idps_stats = stats.get('idps_stats', None)
        try:
            # Append the new IDPS statistics
            can_idps = idps_stats["can_idps"]
            can_idps_data["global_stats"]["m7_anomalies"] += can_idps["global_stats"]["m7_anomalies"]
            can_idps_data["global_stats"]["llce_anomalies"] += can_idps["global_stats"]["llce_anomalies"]
            can_idps_data["idps_data"].extend(can_idps["idps_data"])
        except (KeyError, TypeError):
            # Nothing to add if idps_stats is not in the message
            pass

        # Append the APP Data
        app = json.loads(msg).get('app_data', None)
        if app:
            for topic in app:
                if topic in app_data:
                    app_data[topic].extend(app[topic])
                else:
                    app_data[topic] = app[topic]
        # Add the system stats from the telemetry
        system_stats = stats.get('system_telemetry')
        for k, stat in system_stats.items():
            # If it's a number than it is a statistic
            if isinstance(stat, numbers.Number):
                # Currently only the PFE stats that don't end with 'ps' (per second) are values that represent
                # an average
                if k.startswith('pfe') and not k.endswith('ps'):
                    count_dict[k] = count_dict.get(k, 0) + stat
                else:
                    avg_dict[k] = avg_dict.get(k, 0) + stat
    for k in avg_dict:
        avg_dict[k] /= len(telemetry_data)
    idps_data = {"can_idps": can_idps_data}
    data = json.loads(telemetry_data[0])
    data = data.get('system_telemetry')
    system_telemetry = {**data, **count_dict, **avg_dict}
    return system_telemetry, app_data, idps_data

#pylint: disable=too-many-locals, too-many-branches
def telemetry_collect_and_publish(verbose=False):
    """
    :param verbose: Verbosity flag
    This function is called every telemetry_interval seconds.
    In each call it publishes MQTT messages for the system telemetry,
    idps data, and app data (if applicable).
    """
    telemetry_data = DDS_Sub.receive()

    if not telemetry_data:
        LOGGER.error("No data received from the DDS subscriber: %s", telemetry_data)

    # It should be empty only if a timeout occured
    try:
        system_telemetry, app_data, idps_data = aggregate_telemetry(telemetry_data)

        timestamp = time.time()
        # Set timestamp for current telemetry packet
        time_values = {"Timestamp": int(timestamp),
                       "Datetime": str(datetime.datetime.fromtimestamp(timestamp))}

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
            LOGGER.error("Malformed packet received: %s", system_telemetry)

        try:
            topic = f"{os.environ.get('telemetryTopic')}/idps"
            idps_data.update(time_values)
            publish_to_topic(
                topic=topic,
                payload=json.dumps(idps_data).encode())
            if verbose:
                LOGGER.info("Sent IDPS data to topic: %s data: %s", topic, idps_data)
        except ValueError:
            LOGGER.error("Malformed packet received: %s", idps_data)

        if app_data:
            for topic_suffix, data_list in app_data.items():
                # If the topic suffix is None use the generic application data topic suffix
                if not topic_suffix:
                    topic_suffix = os.environ.get('AppDataTopicSuffix')

                topic = f"{os.environ.get('telemetryTopic')}/{topic_suffix}"

                for data in data_list:
                    # Add the timestamp to the data.
                    if isinstance(data, dict):
                        data["Timestamp"] = int(timestamp)
                    else:
                        LOGGER.error("Invalid app data received, must be dictionary.")
                        continue

                    publish_to_topic(
                        topic=topic,
                        payload=json.dumps(data).encode())
                    if verbose:
                        LOGGER.info("Sent app data to topic: %s data: %s", topic, data)
    # pylint: disable=broad-exception-caught
    except Exception as exception:
        LOGGER.error("Failed to get telemetry: %s \nData received from dom0: %s", exception, telemetry_data)

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
                                      parameter_type=bool, default=VERBOSE) # TODO, send verbosity flag to dom0 with dds
        # pylint: disable=broad-exception-caught
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
    # pylint: disable=broad-exception-caught
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
DDS_Sub = DDSTelemetrySubscriber(
    dds_domain_participant="TelemetryParticipantLibrary::TelemetryGGComponentParticipant")

# Start executing the function above.
# It will be executed every telemetry_interval seconds indefinitely.
threading.Thread(target=telemetry_run).start()

# Start listening for configuration messages on the configuration topic.
listen_for_config()
