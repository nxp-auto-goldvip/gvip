#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2020-2024 NXP

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
can_to_eth_log=/tmp/can2eth_fast_path.log

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

# Generation mode of payload. Default value is increment
payload_random_mode="r"
payload_increment_mode="i"
payload_data="${payload_increment_mode}"

readonly integer_regex="^[0-9]+$"
readonly hex_regex="^[0-9A-Fa-f]+$"
readonly can_to_eth_ids=("0e4" "0e5")
readonly can_dlc_array=("1" "2" "3" "4" "5" "6" "7" "8" "12" "16" "20" "24" "32" "48" "64")
# The variable that specifies whether the CAN RX interface is used or not
use_rx_interface="true"

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
        -D | --payload <hexvalue>        The payload of the CAN frame
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
                        ;;
                -i | --tx-id)
                        shift
                        tx_id=${1}
                        if [[ ! "${tx_id}" =~ ${integer_regex} ]]; then
                                echo "CAN ID must be a positive integer number"
                                exit 1
                        fi
                        if [[ -z "${tx_id}" ]] || [[ $((tx_id)) -lt 0 ]] || [[ $((tx_id)) -gt 2047 ]]; then
                                echo "CAN ID must be greater than or equal to 0 and less than 2048"
                                exit 1
                        fi
                        ;;
                -o | --rx-id)
                        shift
                        rx_id=${1}
                        if [[ ! "${rx_id}" =~ ${integer_regex} ]]; then
                                echo "CAN ID must be a positive integer number"
                                exit 1
                        fi
                        if [[ -z "${rx_id}" ]] || [[ $((rx_id)) -lt 0 ]] || [[ $((rx_id)) -gt 2047 ]]; then
                                echo "CAN ID must be greater than or equal to 0 and less than 2048"
                                exit 1
                        fi
                        ;;
                -t | --can-tx)
                        shift
                        can_tx_interface=${1}
                        if [[ "${can_tx_interface}" != "can0" ]] && [[ "${can_tx_interface}" != "can1" ]]; then
                                echo "Transmit interface is incorrect!"
                                exit 1
                        fi
                        ;;
                -r | --can-rx)
                        shift
                        can_rx_interface=${1}
                        if [[ "${can_rx_interface}" != "can0" ]] && [[ "${can_rx_interface}" != "can1" ]] && [[ "{$can_rx_interface}" == "${can_tx_interface}" ]]; then
                                echo "Receive interface is incorrect!"
                                exit 1
                        fi
                        ;;
                -s | --size)
                        shift
                        can_frame_data_size=${1}
                        if [[ "${can_frame_data_size}" =~ ${integer_regex} ]]; then
                                if ! [[ " ${can_dlc_array[*]} " =~ ${can_frame_data_size} ]]; then
                                        echo "Frame size must be a valid CAN FD frame size or 'i', received ${can_frame_data_size}"
                                        exit 1
                                fi
                        else
                                if [[ "${can_frame_data_size}" != "i" ]]; then
                                        echo "Frame size must be a valid CAN FD frame size or 'i', received ${can_frame_data_size}"
                                        exit 1
                                fi
                        fi
                        ;;
                -l | --length)
                        shift
                        time_gen=${1}
                        if ! [[ "${time_gen}" =~ ${integer_regex} ]]; then
                                echo "Length must be a positive integer number"
                                exit 1
                        fi
                        ;;
                -D | --payload)
                        shift
                        payload_data=${1}
                        if ! [[ "${payload_data}" =~ ${hex_regex} || "${payload_data}" == "${payload_increment_mode}" ||  "${payload_data}" == "${payload_random_mode}" ]]; then
                                echo "Payload data must be 'i' (incremental mode), 'r' (random mode) or a hex value (e.g., DE42AD37)"
                                exit 1
                        fi
                        ;;
                -h | --help) usage && exit 0 ;;
                *)
                        echo "$0: Invalid option $1"
                        usage
                        exit 1
                        ;;
                esac
                shift
        done
        # Check if CAN tx_id is set by user
        if [[ "$tx_id" == "notset" ]]; then
                echo "CAN routing message tx_id should be set by user."
                usage
                exit 1
        fi

        # Check if CAN tx_interface is set by user
        if [[ "${can_tx_interface}" == "notset" ]]; then
                echo "CAN routing tx_interface should be set by user."
                usage
                exit 1
        fi

        # Check if rx_id and can_rx_interface are not set by user
        if [[ "${rx_id}" == "notset" ]] && [[ "${can_rx_interface}" == "notset" ]]; then
                use_rx_interface="false"
        fi

        # Check if CAN rx_id is set by user
        if [[ "${rx_id}" == "notset" ]] && [[ "${can_rx_interface}" != "notset" ]]; then
                echo "CAN routing message rx_id should be set by user."
                usage
                exit 1
        fi

        # Check if CAN rx_interface is set by user
        if [[ "${rx_id}" != "notset" ]] && [[ "${can_rx_interface}" == "notset" ]]; then
                echo "CAN routing message rx_interface should be set by user."
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

        tx_id=$(printf 0x%x "${tx_id}")
        if [[ "${use_rx_interface}" == "true" ]]; then
                rx_id=$(printf 0x%x "${rx_id}")
                echo "Transmit CAN id         : ${tx_id}"
                echo "Receive CAN id          : ${rx_id}"
                echo "CAN transmit interface  : ${can_tx_interface}"
                echo "CAN receive interface   : ${can_rx_interface}"
        else
                echo "Transmit CAN id         : ${tx_id}"
                echo "CAN transmit interface  : ${can_tx_interface}"
        fi
}

# Bring CAN interfaces up
setup_can() {
        ip a | grep -Eq ": ${can_tx_interface}:.*state UP" || service can restart "${can_tx_interface}"

        if [[ "${use_rx_interface}" == "true" ]]; then
                ip a | grep -Eq ": ${can_rx_interface}:.*state UP" || service can restart "${can_rx_interface}"
        fi

        if [[ " ${can_to_eth_ids[*]} " =~ ${tx_id} ]]; then
                service avtp_listener restart ${can_to_eth_log}
        fi
        sleep 1
}

# Terminate cangen processes
stop_cangen() {
        disown ${pid_cangen} 2> /dev/null || true
        kill ${pid_cangen} 2> /dev/null || true
        # wait for in-flight frames to be processed by candump
        sleep 1
}

# Terminate candump processes
stop_candump() {
        disown ${pid_candump} 2> /dev/null || true
        kill ${pid_candump} 2> /dev/null || true

        if [[ " ${can_to_eth_ids[*]} " =~ ${tx_id} ]]; then
                service avtp_listener stop
        fi
}

# Compute the core load using measurement data from a given file.
# arguments:
#       - core_load_file
#       - core name (M7_0, M7_1, M7_2)
compute_core_load() {
        local core_load_file="$1"
        local core_name=$2
        awk "/^${core_name}/ { total += \$2; count++ } END { core_load = count ? (total / count) : \"No measurement\"; print core_load}" "${core_load_file}"
}

# Compute can to ethernet data transfer
compute_can_to_eth_transfer() {
        local data_transfer
        data_transfer=0
        # Check that data has been captured
        if [ -s ${can_to_eth_log} ]; then
                data_transfer=$(tail ${can_to_eth_log} | grep "Received data size" | tail -1 | grep -o -E '[0-9]+')
        fi
        printf %d "${data_transfer}"
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
        if [[ "${use_rx_interface}" == "true" ]]; then
                candump -S "${can_rx_interface}","${rx_id}":"${id_filter}" >${rx_log} &
                pid_candump=$!
        fi

        # Compute the number of CAN frames to be sent considering the allocated time for the
        # frames generation session and the time gap between the frames. Round the result
        # up to the nearest integer (ceil function) if necessary
        if [[ ${frame_gap_ms} -gt 0 ]]; then
                gen_frames_count=$((time_gen * 1000 / frame_gap_ms + ! ! (time_gen * 1000 % frame_gap_ms)))
                gen_frames_opt="-n ${gen_frames_count}"
        else
                gen_frames_opt=""
        fi

        # Start cangen on can_tx_interface interface with requested frame size and gap
        timeout "${time_gen}" cangen "${can_tx_interface}" -g "${frame_gap_ms}" -p 10 -b -I "${tx_id}" \
                -L "${can_frame_data_size}" -D "${payload_data}" "${gen_frames_opt}" -v -v >${tx_log} &
        pid_cangen=$!

        # Compute M7 load during the canperf run
        local m7_load_file="/tmp/m7_load"

        # Clear file.
        : >"${m7_load_file}"
        # Start M7 core load measurement
        m7_core_load.py \
        --outfile "${m7_load_file}" \
        --monitored-cores "M7_0" "M7_1" \
        --time $((time_gen)) &

        echo "Running CAN generator..."
        # Wait until requested session length expires
        wait ${pid_cangen} || true
        stop_cangen

        if [[ "${use_rx_interface}" == "true" ]]; then
                stop_candump
        fi

        # Read the series of M7 core loads and compute their average
        M7_0_LOAD=$(compute_core_load "${m7_load_file}" "M7_0")
        M7_1_LOAD=$(compute_core_load "${m7_load_file}" "M7_1")
}

# Display report by parsing the previously generated logs
display_report() {
        echo "Generating report..."
        tx_frames_count=$(wc -l ${tx_log} | awk '{ print $1 }')
        tx_bytes=$(awk -F'[][]' '{print $2}' ${tx_log} | awk '{ sum += $1 } END { print sum }')
        if [[ ! "${tx_bytes}" =~ ${integer_regex} ]]; then
                echo "No frames have been transmitted. Please check your connections."
                tx_bytes=0
        fi

        if [[ "${use_rx_interface}" == "true" ]]; then
                rx_frames_count=$(wc -l ${rx_log} | awk '{ print $1 }')
                rx_bytes=$(awk -F'[][]' '{print $2}' ${rx_log} | awk '{ sum += $1 } END { print sum }')
                if [[ ! "${rx_bytes}" =~ ${integer_regex} ]]; then
                        rx_bytes=0
                        echo "No frames have been received. Please check the connections or reset the board."
                fi
                frames_lost=$((tx_frames_count - rx_frames_count))

                echo "#############################################################"
                echo "Tx frames:                ${tx_frames_count}"
                echo "Rx frames:                ${rx_frames_count}"
                echo "Tx data transfer:         ${tx_bytes} bytes"
                echo "Rx data transfer:         ${rx_bytes} bytes"
                echo "Tx frames/s:              $((tx_frames_count / time_gen))"
                echo "Rx frames/s:              $((rx_frames_count / time_gen))"
                echo "Tx throughput:            $((tx_bytes * 8 / time_gen / 1000)) Kbit/s"
                echo "Rx throughput:            $((rx_bytes * 8 / time_gen / 1000)) Kbit/s"
                echo "Lost frames:              ${frames_lost}"
                echo "Lost frames (%):          $((frames_lost * 100 / tx_frames_count)).$(((frames_lost * 100 - (frames_lost * 100 / tx_frames_count) * tx_frames_count) * 100 / tx_frames_count))%"
                echo "M7_0 core load:           ${M7_0_LOAD}%"
                echo "M7_1 core load:           ${M7_1_LOAD}%"

                if [[ " ${can_to_eth_ids[*]} " =~ ${tx_id} ]]; then
                    can_to_eth_bytes=$(compute_can_to_eth_transfer)
                    echo "CAN to ETH data transfer: ${can_to_eth_bytes} Bytes"
                fi
                echo "#############################################################"
        else
                echo "#############################################################"
                echo "Tx frames:                ${tx_frames_count}"
                echo "Tx data transfer:         ${tx_bytes} bytes"
                echo "Tx frames/s:              $((tx_frames_count / time_gen))"
                echo "Tx throughput:            $((tx_bytes * 8 / time_gen / 1000)) Kbit/s"
                echo "M7_0 core load:           ${M7_0_LOAD}%"
                echo "M7_1 core load:           ${M7_1_LOAD}%"
                echo "#############################################################"
        fi


}

set_trap
check_input "$@"
setup_can
run_perf
display_report
