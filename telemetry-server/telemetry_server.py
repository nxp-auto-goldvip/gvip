#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Flask backend for the telemetry server.

Copyright 2022-2023 NXP
"""

import logging
import sys

from flask import Flask, jsonify, render_template
from system_telemetry_collector import SystemTelemetryCollector

TELEMETRY = SystemTelemetryCollector(chart_window_size=300)
APP = Flask(__name__)

LOGGER = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

@APP.route('/system_telemetry')
def index():
    """ Flask macro to render the server webpage. """
    return render_template("index.html")

@APP.route('/fetch', methods=['GET'])
def fetch_handler():
    """ Flask macro to handle the GET event for the /fetch url.
    Used to send the chart data to the webpage. """
    TELEMETRY.update_data()
    # Serialize and use JSON headers for the output
    return jsonify(TELEMETRY.get_data())

@APP.route('/getdata/<value>', methods=['GET'])
def getdata_handler(value):
    """ Flask macro to handle the GET method for /getdata url.
    Used to receive input from the webpage.  """
    TELEMETRY.update_window_size(int(value))
    LOGGER.info("New window size = %d\n", int(value))
    return 'OK', 200

if __name__ == '__main__':
    TELEMETRY.data_retriever_run()
    APP.run(host='0.0.0.0')
