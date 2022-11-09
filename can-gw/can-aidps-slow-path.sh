#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2022 NXP

# This script runs the CAN perf script with default arguments to test CAN AIDPS slow path

echo "Simulate anomalous CAN traffic: the cycle time of frame is 100 ms. Only the first frame shall pass."
"$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"/canperf.sh -t can0 -r can1 -i 257 -o 256 -s 8 -g 100 -D 2000000000000000 -l 15

# Wait for everything to be flushed to tty
sleep 1

echo "Running the normal AIDPS case: all frames shall pass."
"$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"/canperf.sh -t can0 -r can1 -i 257 -o 256 -s 8 -g 1000 -D 2000000000000000 -l 15
