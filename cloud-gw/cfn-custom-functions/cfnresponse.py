#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
A module which implements the cloudformation response utility function.
Copyright 2021, 2023 NXP
"""

from __future__ import print_function

import json
import urllib3


SUCCESS = "SUCCESS"
FAILED = "FAILED"


def send(event, context, response_status, response_data,
         physical_resource_id=None):
    """
    Sends a http response.
    :param event: A json event.
    :param context: A Lambda context object, it provides information.
    :param response_status:
    :param response_data: Json data.
    :param physical_resource_id: Id of the resource.
    :param no_echo: Boolean flag.
    :param reason: Optional verbose reason.
    """
    response_url = event['ResponseURL']
    http = urllib3.PoolManager()

    print(response_url)

    response_body = {
        'Status': response_status,
        'Reason': f"See the details in CloudWatch Log Stream: {context.log_stream_name}",
        'PhysicalResourceId': physical_resource_id or context.log_stream_name,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'NoEcho': False,
        'Data': response_data
    }

    json_response_body = json.dumps(response_body)

    print("Response body:")
    print(json_response_body)

    headers = {
        'content-type': '',
        'content-length': str(len(json_response_body))
    }

    try:
        response = http.request(
            'PUT', response_url, headers=headers, body=json_response_body)
        print("Status code:", response.status)
    # pylint: disable=broad-exception-caught
    except Exception as exception:
        print("send(..) failed executing http.request(..):", exception)
