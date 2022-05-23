#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2022 NXP

# This script runs the CAN perf script with specific arguments to test the multi pdu path

SCRIPTS_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"

payloadA=$("${SCRIPTS_DIR}"/gen_multi_pdu_payload.sh -i 1 -s 12 -D 111111111111111111111111 -i 2 -s 12 -D 222222222222222222222222 \
                           -i 3 -s 28 -D 33333333333333333333333333333333333333333333333333333333 )
payloadB=$("${SCRIPTS_DIR}"/gen_multi_pdu_payload.sh -i 4 -s 12 -D 444444444444444444444444 -i 5 -s 12 -D 555555555555555555555555 \
                           -i 6 -s 28 -D 66666666666666666666666666666666666666666666666666666666 )

"${SCRIPTS_DIR}"/canperf-multi.sh -m -g 2 -l 10 -s 64 -t can1 -r can0 -i 95 -D "${payloadA}" -i 96 -D "${payloadB}" -o 97 -o 98 -o 99 

