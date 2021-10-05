#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2020-2021 NXP

# This script is used to simulate a virtual CAN network so that the user can test the CAN-GW and get some performance overview.
# It generates pre-defined CAN traffic on a configured interface and logs the received frames on a configured interface from Linux.
# It is also measuring the throughput and the core load during the run and generates the performance report afterwards.

set -Ee

# ID of the CAN message received on Linux(routing dest)
rx_id=notset

# ID of the CAN message transmited frm Linux(routing src)
tx_id=notset

# CAN Interfaces used by Linux to transmit CAN frames
can_tx_interface=notset

# CAN Interfaces used by Linux to receive CAN frames
can_rx_interface=notset

# Time in ms between two consecutive CAN frames
frame_gap_ms=notset

# Log used for generated CAN frames
tx_log=/tmp/cangen.log

# Log used for received CAN frames
rx_log=/tmp/candump.log

# Log used for received CAN frames over ETH
can_to_eth_log=/tmp/can2eth.log

# CAN frame data size in bytes
can_frame_data_size=notset

# Time period in ms of generating CAN frames
time_gen=notset

# Linux candump job identifier
pid_candump=0

# Linux cangen job identifier
pid_cangen=0

# Number of CAN frame sent from Linux
tx_frames_count=0

# Number of CAN frame received in Linux
rx_frames_count=0

readonly integer_regex="^[0-9]+$"

# Set trap handler for Ctrl-C and ERR signal
set_trap() {
        trap 'stop_cangen ; exit 1' INT
        trap 'echo "An error occurred in file $0, at line ${BASH_LINENO[0]}" && stop_cangen ; exit 1' ERR
}

# Print usage information
usage() {
        echo -e "Usage: ./$(basename "$0") [options]
OPTIONS:
        -t | --can-tx <can i/f name>     CAN transmit interface, e.g., can0 or can1
        -r | --can-rx <can i/f name>     CAN receive interface, e.g., can0 or can1
        -i | --tx-id <hexvalue>          Transimited CAN message ID.
        -o | --rx-id <hexvalue>          Received CAN message ID.    
        -g | --gap <ms>                  Frame gap in milliseconds between two consecutive generated CAN frames
        -s | --size <bytes>              CAN frame data size in bytes. For CAN frames with variable size, use 'i'
        -l | --length <seconds>          The length of the CAN traffic generation session
        -h | --help                      help
"
}

# Parse the user arguments
check_input() {
        while [[ $# -gt 0 ]]; do
                case "${1}" in
                -g | --gap)
                        shift
                        frame_gap_ms=${1}
                        if [[ ! "${frame_gap_ms}" =~ ${integer_regex} ]]; then
                                echo "Frame gap must be a positive integer number"
                                exit 1
                        fi
                        shift
                        ;;
                -i | --tx-id)
                        shift
                        tx_id=${1}
                        if [[ ! "${tx_id}" =~ ${integer_regex} ]]; then
                                echo "CAN ID must be a positive integer number"
                                exit 1
                        fi
                        if [[ -z "${tx_id}" ]] || [[ 10#${tx_id} -lt 0 ]] || [[ 10#${tx_id} -gt 799 ]]; then
                                echo "CAN ID must be greater than 0 and less than 799"
                                exit 1
                        fi
                        shift
                        ;;
                -o | --rx-id)
                        shift
                        rx_id=${1}
                        if [[ ! "${rx_id}" =~ ${integer_regex} ]]; then
                                echo "CAN ID must be a positive integer number"
                                exit 1
                        fi
                        if [[ -z "${rx_id}" ]] || [[ 10#${rx_id} -lt 0 ]] || [[ 10#${rx_id} -gt 799 ]]; then
                                echo "CAN ID must be greater than 0 and less than 799"
                                exit 1
                        fi
                        shift
                        ;;
                -t | --can-tx)
                        shift
                        can_tx_interface=${1}
                        if [[ "${can_tx_interface}" != "can0" ]] && [[ "${can_tx_interface}" != "can1" ]]; then
                                echo "Transmit interface is incorrect!"
                                exit 1
                        fi
                        shift
                        ;;
                -r | --can-rx)
                        shift
                        can_rx_interface=${1}
                        if [[ "${can_rx_interface}" != "can0" ]] && [[ "${can_rx_interface}" != "can1" ]] && [[ "{$can_rx_interface}" == "${can_tx_interface}" ]]; then
                                echo "Receive interface is incorrect!"
                                exit 1
                        fi
                        shift
                        ;;
                -s | --size)
                        shift
                        can_frame_data_size=${1}
                        if [[ "${can_frame_data_size}" =~ ${integer_regex} ]]; then
                                if ((can_frame_data_size < 1 || can_frame_data_size > 64)); then
                                        echo "Frame size must be a positive integer between 1 and 64 or 'i', received ${can_frame_data_size}"
                                        exit 1
                                fi
                        else
                                if [[ "${can_frame_data_size}" != "i" ]]; then
                                        echo "Frame size must be a positive integer between 1 and 64 or 'i', received ${can_frame_data_size}"
                                        exit 1
                                fi
                        fi
                        shift
                        ;;
                -l | --length)
                        shift
                        time_gen=${1}
                        if ! [[ "${time_gen}" =~ ${integer_regex} ]]; then
                                echo "Length must be a positive integer number"
                                exit 1
                        fi
                        ((time_gen *= 1000))
                        shift
                        ;;
                -h | --help) usage && exit 0 ;;
                *)
                        echo "$0: Invalid option $1"
                        usage
                        exit 1
                        ;;
                esac
        done
        # Check if both CAN Ids are set by user
        if [[ "$tx_id" == "notset" ]] || [[ "$rx_id" == "notset" ]]; then
                echo "CAN routing message IDs should be set by user."
                usage
                exit 1
        fi

        # Check if both CAN interfaces are set by user
        if [[ "${can_tx_interface}" == "notset" ]] || [[ "${can_rx_interface}" == "notset" ]]; then
                echo "CAN routing interfaces should be set by user."
                usage
                exit 1
        fi

        # Check if CAN data frame size is set by user
        if [[ "$can_frame_data_size" == "notset" ]]; then
                echo "CAN data frame size should be set by user."
                usage
                exit 1
        fi

        # Check if time period for generating CAN traffic is set by user
        if [[ "$time_gen" == "notset" ]]; then
                echo "time period for generating CAN traffic should be set by user."
                usage
                exit 1
        fi

        # Check if time gap between consecutive CAN frames is set by user
        if [[ "$frame_gap_ms" == "notset" ]]; then
                echo "period between two consecutive generated CAN frames should be set by user."
                usage
                exit 1
        fi

        rx_id=$(printf %x "${rx_id}")
        tx_id=$(printf %x "${tx_id}")
        echo "Transmit CAN id         : ${tx_id}"
        echo "Receive CAN id          : ${rx_id}"
        echo "CAN transmit interface  : ${can_tx_interface}"
        echo "CAN receive interface   : ${can_rx_interface}"
}

# Bring CAN interfaces up
setup_can() {
        ip link set "${can_tx_interface}" down
        ip link set "${can_rx_interface}" down
        ip link set "${can_tx_interface}" up type can bitrate 1000000 sample-point 0.75 dbitrate 4000000 dsample-point 0.8 fd on
        ip link set "${can_rx_interface}" up type can bitrate 1000000 sample-point 0.75 dbitrate 4000000 dsample-point 0.8 fd on

        if [[ "${tx_id}" == "e4" ]] || [[ "${tx_id}" == "e5" ]]; then
            service avtp_listener restart ${can_to_eth_log}
        fi
        sleep 1
}

# Terminate cangen and candump processes
stop_cangen() {
        disown ${pid_cangen}
        kill ${pid_cangen} 2>/dev/null
        # wait for in-flight frames to be processed by candump
        sleep 1
        disown ${pid_candump}
        kill ${pid_candump} 2>/dev/null
        
        if [[ "${tx_id}" == "e4" ]] || [[ "${tx_id}" == "e5" ]]; then
            service avtp_listener stop
        fi
}

# Run performance measurements by running the candump listener on the RX interface and
# by generating can traffic on the TX interface using cangen.
run_perf() {
        # Mask used to match only the desired CAN Id
        id_filter=FFFFFFFF

        # Clean up any previous logs
        rm -f "${tx_log}" "${rx_log}"

        # Run candump on can_rx_interface interface expecting CAN id rx_id. Swap byte
        # order argument (-S) is used to facilitate incremental payload checking
        candump -S "${can_rx_interface}","${rx_id}":"${id_filter}" >${rx_log} &
        pid_candump=$!

        # Get time base
        start_time_ms=$(date +%s%3N)
        current_time_ms=${start_time_ms}

        # Start cangen on can_tx_interface interface with requested frame size and gap
        cangen "${can_tx_interface}" -g "${frame_gap_ms}" -p 10 -b -I "${tx_id}" -L "${can_frame_data_size}" -D i -v -v >${tx_log} &
        pid_cangen=$!

        # Compute M7 load during the canperf run
        local m7_load_file="/tmp/m7_load"
        # Clear file.
        : >"${m7_load_file}"

        # Start M7 core load measurement
        python3 "$(dirname "${BASH_SOURCE[0]}")/m7_core_load.py" --file "${m7_load_file}" --time $((time_gen / 1000)) &

        echo "Running CAN generator..."
        # Wait until requested session length expires
        while [[ $((current_time_ms - start_time_ms)) -lt ${time_gen} ]]; do
                current_time_ms=$(date +%s%3N)
        done
        stop_cangen

        # Read the series of M7 core loads and compute their average
        M7_LOAD=$(awk '{ total += $1; count++ } END { core_load = count ? (total / count) : "No measurement"; print core_load }' "${m7_load_file}")
}

# Display report by parsing the previously generated logs
display_report() {
        echo "Generating report..."
        tx_frames_count=$(wc -l ${tx_log} | awk '{ print $1 }')
        rx_frames_count=$(wc -l ${rx_log} | awk '{ print $1 }')
        tx_bytes=$(awk -F'[][]' '{print $2}' ${tx_log} | awk '{ sum += $1 } END { print sum }')
        if [[ ! "${tx_bytes}" =~ ${integer_regex} ]]; then
                echo "No frames have been transmitted. Please check your connections."
                tx_bytes=0
        fi

        rx_bytes=$(awk -F'[][]' '{print $2}' ${rx_log} | awk '{ sum += $1 } END { print sum }')
        if [[ ! "${rx_bytes}" =~ ${integer_regex} ]]; then
                rx_bytes=0
                echo "No frames have been received. Please check the connections or reset the board."
        fi

        echo "#############################################################"
        echo "Tx frames:                ${tx_frames_count}"
        echo "Rx frames:                ${rx_frames_count}"
        echo "Tx data transfer:         ${tx_bytes} bytes"
        echo "Rx data transfer:         ${rx_bytes} bytes"
        echo "Tx frames/s:              $((tx_frames_count * 1000 / time_gen))"
        echo "Rx frames/s:              $((rx_frames_count * 1000 / time_gen))"
        echo "Tx throughput:            $((tx_bytes * 8 / time_gen)) Kbit/s"
        echo "Rx throughput:            $((rx_bytes * 8 / time_gen)) Kbit/s"
        echo "Lost frames:              $((tx_frames_count - rx_frames_count))"
        echo "M7 core load:             ${M7_LOAD}%"
        if [[ "${tx_id}" == "e4" ]] || [[ "${tx_id}" == "e5" ]]; then
            can_to_eth_bytes=$(tail ${can_to_eth_log} | grep "Received data size" | tail -1 | grep -o -E '[0-9]+')
            echo "CAN to ETH data transfer: ${can_to_eth_bytes} Bytes" 
        fi
        echo "#############################################################"
}

set_trap
check_input "$@"
setup_can
run_perf
display_report
