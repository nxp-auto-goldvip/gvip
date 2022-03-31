#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2022 NXP

# This script runs the CAN perf script with specific arguments to test the secure onboard communication functionality

SCRIPTS_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"

# Data payload we want to send
authentic_payload="234D73672073656375726564207573696E6720484D4143205348412D32353623"

# The key is currently hard coded in this file and inside the can-gw software running on the M7
# In order to update the key one needs to update it here and to update the init value inside the M7 software
mac_key="4e5850494e5850494e5850494e5850494e5850494e5850494e5850494e585049"

# The data ids are configured here and inside the M7 SecOC module configuration
data_id_sw="0040"

# Default settings for software crypto: Tx frame with ID 64 on can0 , Rx frame with ID 66 on can1 , DLC 64 , 10 second period, 2ms gap between frames
common_params=(-g 2 -s 64 -t can0 -r can1 -i 64 -o 66 -l 10)

echo "Simulate unsecured traffic: The payload does not contain a authentication code. All frames shall be dropped."
"${SCRIPTS_DIR}"/canperf.sh "${common_params[@]}" -D "${authentic_payload}"
# Wait for everything to be flushed to tty
sleep 1

# Generate a secure payload and check if secure payload generation completed successfully
if ! secure_payload=$("${SCRIPTS_DIR}"/gen_secure_payload.sh -i "${data_id_sw}" -k "${mac_key}" -D "${authentic_payload}"); then
    echo "Secure payload generation failed."
    echo "${secure_payload}"
    exit 1
fi

echo "Simulate secured traffic using cryptographic primitives implemented in software:"
"${SCRIPTS_DIR}"/canperf.sh "${common_params[@]}" -D "${secure_payload}"
