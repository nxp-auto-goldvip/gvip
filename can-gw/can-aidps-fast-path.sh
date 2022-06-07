#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2022 NXP

# This script runs the CAN perf script with default arguments to test CAN AIDPS fast path

echo "Simulate anomalous CAN traffic: the size of the frame is 7 when the expected size is 8. All frames shall be dropped."
"$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"/canperf.sh -t can0 -r can1 -i 289 -o 289 -s 7 -g 1000 -D 2000000000000000 -l 15

# Wait for everything to be flushed to tty
sleep 1

echo "Running the normal AIDPS case: all frames shall pass."
"$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"/canperf.sh -t can0 -r can1 -i 289 -o 289 -s 8 -g 1000 -D 2000000000000000 -l 15
