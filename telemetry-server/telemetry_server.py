#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Flask backend for the telemetry server.

Copyright 2022 NXP
"""

from flask import Flask, jsonify, request, render_template
from system_telemetry_collector import SystemTelemetryCollector

TELEMETRY = SystemTelemetryCollector(chart_window_size=300)
APP = Flask(__name__)

@APP.route('/system_telemetry')
def index():
    """ Flask macro to render the server webpage. """
    return render_template("index.html")

@APP.route('/fetch', methods=['GET', 'POST'])
def fetch_handler():
    """ Flask macro to handle the GET and POST events for the /fetch url.
    Used to send the chart data to the webpage. """
    # POST request
    if request.method == 'POST':
        print(request.get_json())  # parse as JSON
        return 'OK', 200
    # GET request
    TELEMETRY.update_data()
    # Serialize and use JSON headers for the output
    return jsonify(TELEMETRY.get_data())

@APP.route('/getdata/<value>', methods=['GET'])
def getdata_handler(value):
    """ Flask macro to handle the GET method for /getdata url.
    Used to receive input from the webpage.  """
    TELEMETRY.update_window_size(int(value))
    print(f"New window size = {value}")
    print(request.get_json())
    return 'OK', 200

if __name__ == '__main__':
    TELEMETRY.data_retriever_run()
    APP.run(host='0.0.0.0')
