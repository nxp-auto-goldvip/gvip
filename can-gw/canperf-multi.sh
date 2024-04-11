#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2022-2024 NXP
# This script is used to simulate a virtual CAN network so that the user can test the CAN-GW and get some performance overview.
# It generates pre-defined CAN traffic on a configured interface and logs the received frames on a configured interface from Linux.
# It is also measuring the throughput and the core load during the run and generates the performance report afterwards.

set -Ee

# ID of the CAN message received on Linux(routing dest)
rx_id=notset
# List of IDs of CAN messages received by Linux(routing dest)
rx_id_list=()
# ID of the CAN message transmitted from Linux(routing src)
tx_id=notset
# List of IDs of CAN messages transmitted from Linux(routing src)
tx_id_list=()

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

# CAN frame data size in bytes
can_frame_data_size=notset
# Time period in ms of generating CAN frames
time_gen=notset

# Linux candump job identifier
pid_candump=0
# Linux cangen job identifier
generation_tool_pid=0

# Number of CAN frame sent from Linux
tx_frames_count=0
# Number of CAN frame received in Linux
rx_frames_count=0

# Generation mode of payload. Default value is increment
payload_data=0
# List of transmitted can payloads
payload_data_list=()

# Flag that specifies whether the multi pdu mode is active.
multi_pdu_mode="off"

# Variable used to control the log file used in generating the IPDU report
log_file=""
# Variable used to control the log type used in generating the IPDU report
log_type=""

# Gap between frames that have to be sent clustered together in the frame replay use case
readonly inter_frame_gap_usec=100

# associative array for storing the number of received bytes for each pdu id
declare -A rx_pdu_bytes=()
# associative array for storing the number of received pdu's
declare -A rx_pdu_count=()
# associative array for storing the number of transmitted bytes for each pdu id
declare -A tx_pdu_bytes=()
# associative array for storing the number of transmitted pdu's
declare -A tx_pdu_count=()

readonly integer_regex="^[0-9]+$"
readonly hex_regex="^[0-9A-Fa-f]+$"
readonly can_dlc_array=("1" "2" "3" "4" "5" "6" "7" "8" "12" "16" "20" "24" "32" "48" "64")

# The variable that specifies whether the CAN RX interface is used or not
use_rx_interface="true"

# Set trap handler for Ctrl-C and ERR signal
set_trap() {
        trap 'stop_canplayer ; stop_candump ; exit 1' INT
        trap 'echo "An error occurred in file $0, at line ${BASH_LINENO[0]}" && stop_canplayer ; stop_candump ; exit 1' ERR
}

# Print usage information
usage() {
        echo -e "Usage: ./$(basename "$0") [options]
OPTIONS:
        -t | --can-tx <can i/f name>     CAN transmit interface, e.g., can0 or can1
        -r | --can-rx <can i/f name>     CAN receive interface, e.g., can0 or can1
        -i | --tx-id <hexvalue>          Transmitted CAN message ID.
        -o | --rx-id <hexvalue>          Received CAN message ID.
        -g | --gap <ms>                  Frame gap in milliseconds between two consecutive generated CAN frames
        -s | --size <bytes>              CAN frame data size in bytes. For CAN frames with variable size, use 'i'
        -l | --length <seconds>          The length of the CAN traffic generation session
        -D | --payload <hexvalue>        The payload of the CAN frame
        -m | --multi                     Enable multi pdu mode
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
                                echo "Frame gap must be a positive integer number!"
                                exit 1
                        fi                        
                        ;;
                -i | --tx-id)
                        shift
                        tx_id=${1}
                        if [[ ! "${tx_id}" =~ ${integer_regex} ]]; then
                                echo "CAN ID must be a positive integer number!"
                                exit 1
                        fi
                        if [[ -z "${tx_id}" ]] || [[ $((tx_id)) -lt 0 ]] || [[ $((tx_id)) -gt 2047 ]]; then
                                echo "CAN ID must be greater than or equal to 0 and less than 2048!"
                                exit 1
                        fi
                        tx_id_list+=("${tx_id}")
                        ;;
                -o | --rx-id)
                        shift
                        rx_id=${1}
                        if [[ ! "${rx_id}" =~ ${integer_regex} ]]; then
                                echo "CAN ID must be a positive integer number!"
                                exit 1
                        fi
                        if [[ -z "${rx_id}" ]] || [[ $((rx_id)) -lt 0 ]] || [[ $((rx_id)) -gt 2047 ]]; then
                                echo "CAN ID must be greater than or equal to 0 and less than 2048!"
                                exit 1
                        fi
                        rx_id_list+=("${rx_id}")
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
                                        echo "Frame size must be a valid CAN FD frame size or 'i', received ${can_frame_data_size}"
                                exit 1
                        fi                        
                        ;;
                -l | --length)
                        shift
                        time_gen=${1}
                        if ! [[ "${time_gen}" =~ ${integer_regex} ]]; then
                                echo "Length must be a positive integer number!"
                                exit 1
                        fi
                        ((time_gen *= 1000))                        
                        ;;
                -D | --payload)
                        shift
                        payload_data=${1}
                        if ! [[ "${payload_data}" =~ ${hex_regex} ]]; then
                                echo "Payload data must be a hex value (e.g., DE42AD37)!"
                                exit 1
                        fi
                        payload_data_list+=("${payload_data}")                        
                        ;;
                -m | --multi)
                        multi_pdu_mode="on"
                        ;;

                -h | --help) usage && exit 0 ;;
                *)
                        echo "$0: Invalid option $1!"
                        usage
                        exit 1
                        ;;
                esac
                shift
        done
        # Check if CAN tx_id is set by user
        if [[ "${#tx_id_list[@]}" -eq 0 ]]; then
                echo "CAN routing message tx_id should be set by user!"
                usage
                exit 1
        fi

        # Check if CAN tx_interface is set by user
        if [[ ${can_tx_interface} == "notset" ]]; then
                echo "CAN routing tx_interface should be set by user!"
                usage
                exit 1
        fi
        # Check if rx_id and can_rx_interface are not set by user
        if [[ "${rx_id}" == "notset" ]] && [[ "${can_rx_interface}" == "notset" ]]; then
                use_rx_interface="false" 
        fi
        # Check if CAN rx_id is set by user
        if [[ ${#rx_id_list[@]} -eq 0 ]] && [[ "${can_rx_interface}" != "notset" ]]; then
                echo "CAN routing message rx_id should be set by user!"
                usage
                exit 1
        fi
        # Check if CAN rx_interface is set by user
        if [[ ${#rx_id_list[@]} -gt 0 ]] && [[ "${can_rx_interface}" == "notset" ]]; then
                echo "CAN routing message rx_interface should be set by user!"
                usage
                exit 1
        fi
        # Check if CAN data frame size is set by user
        if [[ "$can_frame_data_size" == "notset" ]]; then
                echo "CAN data frame size should be set by user!"
                usage
                exit 1
        fi
        # Check if time period for generating CAN traffic is set by user
        if [[ "$time_gen" == "notset" ]]; then
                echo "Time period for generating CAN traffic should be set by user!"
                usage
                exit 1
        fi
        # Check if time gap between consecutive CAN frames is set by user
        if [[ "$frame_gap_ms" == "notset" ]]; then
                echo "Period between two consecutive generated CAN frames should be set by user!"
                usage
                exit 1
        fi
        # Check if the number of payloads matches the number of id's
        if [[ ${#payload_data_list[@]} -ne ${#tx_id_list[@]} ]]; then
                echo "User should set the same number of ID's and payloads!"
                usage
                exit 1
        fi

        tx_id=""
        for id in "${tx_id_list[@]}"; do
                hex_id=$(printf 0x%x "${id}")
                tx_id="${tx_id}${hex_id} "
        done
        
        if [[ "${use_rx_interface}" == "true" ]]; then
                rx_id=""
                for id in "${rx_id_list[@]}"; do
                        hex_id=$(printf 0x%x "${id}")
                        rx_id="${rx_id}${hex_id} "
                done

                echo "Transmit CAN IDs        : ${tx_id}"
                echo "Receive CAN IDs         : ${rx_id}"
                echo "CAN transmit interface  : ${can_tx_interface}"
                echo "CAN receive interface   : ${can_rx_interface}"
        else
                echo "Transmit CAN IDs        : ${tx_id}"
                echo "CAN transmit interface  : ${can_tx_interface}"
        fi
}


# Terminate canplayer process
stop_canplayer() {

        #if process exists
        if [[ $generation_tool_pid -ne 0 ]] && [[ -n "$(ps -p $generation_tool_pid -o pid=)" ]]; then
                disown ${generation_tool_pid}
                kill ${generation_tool_pid} 2>/dev/null
        fi
        # wait for in-flight frames to be processed by candump
        sleep 1
}

# Terminate candump process
stop_candump() {
        #if process exists
        if [[ $pid_candump -ne 0 ]] && [[ -n "$(ps -p $pid_candump -o pid=)" ]]; then
                disown ${pid_candump}
                kill ${pid_candump} 2>/dev/null
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

# Generates a transmit log using an id list , a gap size and a total log time.
generate_tx_log() {
        sec=0
        msec=0
        usec=0
        while [[ $sec -lt 1 ]]; do
                for index in "${!tx_id_list[@]}"; do
                        printf "(%d.%03d%03d) %s %03x##1%s\n" "${sec}" "${msec}" "${usec}" "${can_tx_interface}" "${tx_id_list[$index]}" "${payload_data_list[$index]}" >> "${tx_log}" 
                        ((usec+=inter_frame_gap_usec))
                        if [[ "${usec}" -ge 1000 ]]; then
                                (( msec+=1 ))
                                if [ "${usec}" -gt 1000 ]; then
                                        (( usec-=1000 ))
                                else
                                        # Manually assign 0 in order to avoid triggering an underflow trap
                                        usec=0 
                                fi
                        fi
                done
                # If frame gap is greater than 0 then we do not keep the inter frame gap offset between frame groups  
                if [[ "${frame_gap_ms}" -gt 0 ]]; then
                        usec=0
                        ((msec+=frame_gap_ms))
                        
                fi  
                
                if [[ "${msec}" -ge 1000 ]]; then
                        (( sec+=1 ))
                        if [ "${msec}" -gt 1000 ]; then
                                (( msec-=1000 ))
                        else
                                # Manually assign 0 in order to avoid triggering an underflow trap
                                msec=0
                        fi
                fi
        done
}

# Run performance measurements by running the candump listener on the RX interface and
# by generating can traffic on the TX interface using canplayer.
run_perf() {
        # Clean up any previous logs
        rm -f "${tx_log}" "${rx_log}"
        generate_tx_log  

        # Run candump on can_rx_interface interface expecting CAN id rx_id. Swap byte
        # order argument (-S) is used to facilitate incremental payload checking
        if [[ "${use_rx_interface}" == "true" ]]; then
                rx_id_and=$(IFS='&'; echo "$((${rx_id_list[*]}))")
                rx_id_or=$(IFS='|'; echo "$((${rx_id_list[*]}))")
                # Mask used to match all of the desired CAN ID's
                ((id_filter=rx_id_and^rx_id_or))
                ((id_filter=16#FFFFFFFF-id_filter))
                id_filter=$(printf "%x" "${id_filter}")
                hex_id=$(printf "%x" "${rx_id_list[0]}")
                # Do not use -S parameter in case of canplayer usage since it makes interpreting the output more difficult 
                candump "${can_rx_interface}","${hex_id}":"${id_filter}" >${rx_log} &
                pid_candump=$!
        fi

        # Get time base
        start_time_ms=$(date +%s%3N)
        current_time_ms=${start_time_ms}

        # Start canplayer on the tx log file
        canplayer -l "$((time_gen / 1000))" -g 0 -I "${tx_log}" &
        generation_tool_pid=$!

        # Compute M7 load during the canperf run
        local m7_load_file="/tmp/m7_load"
        # Clear file.
        : >"${m7_load_file}"
        # Start M7 core load measurement
        m7_core_load.py \
        --outfile "${m7_load_file}" \
        --monitored-cores "M7_0" "M7_1" \
        --time $((time_gen / 1000)) &

        echo "Running CAN generator..."
        # Wait until requested session length expires
        while [[ $((current_time_ms - start_time_ms)) -lt ${time_gen} ]]; do
                current_time_ms=$(date +%s%3N)
        done
        stop_canplayer
        if [[ "${use_rx_interface}" == "true" ]]; then
                stop_candump
        fi

        # Read the series of M7 core loads and compute their average
        M7_0_LOAD=$(compute_core_load "${m7_load_file}" "M7_0")
        M7_1_LOAD=$(compute_core_load "${m7_load_file}" "M7_1")
}

# Generates ipdu report data ( number of ipdu's and number of bytes) from a log file 
get_ipdu_data_from_log() {
        # Associative array for storing the number of bytes for each id
        local -n pdu_bytes=${1}
        # Associative array for storing the number of received pdu's for each id
        local -n pdu_count=${2}
        log_type=${3}
        log_file=${4}
        number_of_replays=${5}

        # Extract only the payload information from the log files
        if [[ ${log_type} == "ascii" ]] ; then
                # Human readable "ascii format" log files use ] as a separator between the dlc and payload and have spaces between bytes
                processed_log="$(awk -F']' '{gsub(/ /, "");print $2}' "${log_file}")"
        else
                # Non human readable "log format" log files use ## as a separator between the id and payload and do not have spaces between bytes
                processed_log="$( awk -F'##' '{print substr($2,2)}' "${log_file}")"
        fi
        # Get each unique line from the log together with the line count
        processed_log=$(echo "${processed_log}" | sort | uniq -c)

        # The first row contains the line count
        line_occurrences=$(awk '{print $1}' <<< "$processed_log")
        # Split number of lines into array
        readarray -t line_occurrences <<<"$line_occurrences"
        # The second row contains the unique lines
        processed_log=$(awk '{print $2}' <<< "$processed_log")
        # Split unique lines into array
        readarray -t processed_log <<<"$processed_log"
        
        # Iterate over unique lines
        for index in "${!processed_log[@]}"; do
                # Associative array for storing the number of transmitted bytes for each pdu id
                local  -A line_pdu_bytes=()
                # Associative array for storing the number of transmitted pdu's
                local -A line_pdu_count=()
                # Get first line from processed log
                working_line="${processed_log[$index]}"

                # Shorten the working line after reading a complete pdu
                # If the working line is shorter then the size of a pdu id + dlc then stop
                while [[ "${#working_line}" -gt 8 ]]; do
                        # The id is the first 3 bytes of the pdu contents
                        id=${working_line:0:6}
                        # The dlc is the fourth byte
                        dlc=${working_line:6:2}
                        # Convert dlc to decimal
                        dlc=$(("16#${dlc}"))
                        # The associative arrays contain an entry for each id
                        # A valid id is greater than 0 
                        if [[ "${id}" != "000000" ]] ; then
                                # If the id key is not part of the dictionary yet then we need to add an new element for each array
                                if ! [[ ${line_pdu_bytes["${id}"]+-} ]]; then
                                        line_pdu_bytes+=(["${id}"]="${dlc}")
                                        line_pdu_count+=(["${id}"]=1)
                                else
                                        # We already have the key inside the dictionary so we just need to increase the stored value
                                        ((line_pdu_bytes["${id}"]+=dlc))
                                        ((line_pdu_count["${id}"]+=1))
                                fi
                                # The start of the next pdu = length of id,dlc + payload (4 bytes + dlc bytes) , each byte is 2 characters
                                start=$((2*(4+dlc)))
                                # If we have where to jump to
                                if [[ "${#working_line}" -gt "${start}" ]]; then
                                        # Jump to the next pdu in the working line
                                        working_line="${working_line:${start}}"
                                else
                                        # The received pdu does not have the correct format -> stop the extraction process for the current line 
                                        working_line=""
                                fi
                        else
                                # Reading 0 means reaching the padding section -> stop the extraction process for the current line
                                working_line=""
                        fi
                done
                
                line_occurrence="${line_occurrences[$index]}"

                for id in "${!line_pdu_bytes[@]}"; do
                        # Compute total number of received/transmitted bytes for that frame
                        ((bytes=${line_pdu_bytes["${id}"]}*line_occurrence*number_of_replays))
                         # Compute total number of received/transmitted PDU's for that frame
                        ((count=${line_pdu_count["${id}"]}*line_occurrence*number_of_replays))
                        # If the id key is not part of the dictionary yet then we need to add an new element for each array
                        if ! [[ ${pdu_bytes["${id}"]+-} ]]; then
                                # Store the frame statistics to the permanent associative array
                                pdu_bytes+=(["${id}"]="${bytes}")
                                pdu_count+=(["${id}"]="${count}")
                        else
                                # We already have the key inside the dictionary so we just need to increase the stored value
                                # Store the frame statistics to the permanent associative array
                                ((pdu_bytes["${id}"]+="${bytes}"))
                                ((pdu_count["${id}"]+="${count}"))
                        fi
                done
        done
}

# Displays the transmit and receive report for one IPDU
display_individual_ipdu_report() {
        if [[  "${decimal_id}" =~ ${integer_regex} ]]; then
                # Print statistics for just one IPDU
                echo "Statistics for IPDU ${decimal_id} :"
        else
                # Print overall statistics
                echo "${decimal_id} statistics for IPDUs :"
        fi
        echo "Tx IPDUs:                 ${ipdu_tx_count}"
        if [[ "${use_rx_interface}" == "true" ]]; then
                echo "Rx IPDUs:                 ${ipdu_rx_count}"
        fi
        echo "Tx IPDU data transfer:    ${ipdu_tx_bytes} bytes"
        if [[ "${use_rx_interface}" == "true" ]]; then
                echo "Rx IPDU data transfer:    ${ipdu_rx_bytes} bytes"
        fi
        echo "Tx IPDUs/s:               $((ipdu_tx_count * 1000 / time_gen))"
        if [[ "${use_rx_interface}" == "true" ]]; then
                echo "Rx IPDUs/s:               $((ipdu_rx_count * 1000 / time_gen))"
        fi
        echo "Tx IPDU throughput:       $((ipdu_tx_bytes * 8 / time_gen)) Kbit/s"
        if [[ "${use_rx_interface}" == "true" ]]; then
                echo "Rx IPDU throughput:       $((ipdu_rx_bytes * 8 / time_gen)) Kbit/s"
                echo "Lost IPDUs:               $((ipdu_tx_count-ipdu_rx_count))"
        fi
}

# Displays the transmit and receive report for all received and transmitted ipdus
display_entire_ipdu_report() {
        ipdu_rx_count_total=0
        ipdu_rx_bytes_total=0
        ipdu_tx_count_total=0
        ipdu_tx_bytes_total=0

        # Iterate over tx array
        for key in "${!tx_pdu_bytes[@]}"; do
                # Convert IPDU id to decimal
                decimal_id=$(echo -n "${key}" | tac -rs ..)
                decimal_id=$(("16#${decimal_id}"))

                ipdu_tx_count=${tx_pdu_count[$key]}
                ((ipdu_tx_count_total+=ipdu_tx_count))
                ipdu_tx_bytes=${tx_pdu_bytes[$key]}
                ((ipdu_tx_bytes_total+=ipdu_tx_bytes))
                ipdu_rx_count=0
                ipdu_rx_bytes=0

                # If the ID is also present in the rx array then get the rx data
                if [[ "${use_rx_interface}" == "true" ]] && [[ ${rx_pdu_bytes["${key}"]+-} ]]; then
                        ipdu_rx_count=${rx_pdu_count[$key]}
                        ((ipdu_rx_count_total+=ipdu_rx_count))
                        ipdu_rx_bytes=${rx_pdu_bytes[$key]}
                        ((ipdu_rx_bytes_total+=ipdu_rx_bytes))
                fi
                display_individual_ipdu_report
        done
        if [[ "${use_rx_interface}" == "true" ]]; then
                # Iterate over rx array
                for key in "${!rx_pdu_bytes[@]}"; do
                        # If an ID is present in the rx array but not in the tx array then it was not displayed before
                        if ! [[ ${tx_pdu_bytes["${key}"]+-} ]]; then
                                # Convert ipdu id to decimal
                                decimal_id=$(echo -n "${key}" | tac -rs ..)
                                decimal_id=$(("16#${decimal_id}"))

                                ipdu_tx_count=0
                                ipdu_tx_bytes=0
                                ipdu_rx_count=${rx_pdu_count[$key]}
                                ipdu_rx_bytes=${rx_pdu_bytes[$key]}
                                display_individual_ipdu_report
                        fi
                done
        fi
        # Display overall statistics
        decimal_id="Overall"
        ipdu_tx_count="${ipdu_tx_count_total}"
        ipdu_tx_bytes="${ipdu_tx_bytes_total}"
        ipdu_rx_count="${ipdu_rx_count_total}"
        ipdu_rx_bytes="${ipdu_rx_bytes_total}"

        display_individual_ipdu_report
}

# Display report by parsing the previously generated logs
display_report() {
        echo "Generating report..."

        if [[ "${multi_pdu_mode}" == "on" ]]; then
                get_ipdu_data_from_log tx_pdu_bytes tx_pdu_count "log" "${tx_log}" $((time_gen / 1000)) 
                if [[ "${use_rx_interface}" == "true" ]]; then
                        get_ipdu_data_from_log rx_pdu_bytes rx_pdu_count "ascii" "${rx_log}" 1
                fi
        fi

        tx_frames_count=$(wc -l ${tx_log} | awk '{ print $1 }')
        ((tx_frames_count*=time_gen / 1000)) 

        # canplayer uses the "log format" with the ## separator for the transmit log
        tx_bytes=$(awk -F'##' '{print $2}' ${tx_log} | awk '{ sum += length } END { print sum/2 }')
        
        if [[ ! "${tx_bytes}" =~ ${integer_regex} ]]; then
                echo "No frames have been transmitted. Please check your connections!"
                tx_bytes=0
        fi
        ((tx_bytes*=time_gen / 1000))

        if [[ "${use_rx_interface}" == "true" ]]; then
                rx_frames_count=$(wc -l ${rx_log} | awk '{ print $1 }')
                rx_bytes=$(awk -F'[][]' '{print $2}' ${rx_log} | awk '{ sum += $1 } END { print sum }')
                if [[ ! "${rx_bytes}" =~ ${integer_regex} ]]; then
                        rx_bytes=0
                        echo "No frames have been received. Please check the connections or reset the board!"
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
        else
                echo "#############################################################"
                echo "Tx frames:                ${tx_frames_count}"
                echo "Tx data transfer:         ${tx_bytes} bytes"
                echo "Tx frames/s:              $((tx_frames_count * 1000 / time_gen))"
                echo "Tx throughput:            $((tx_bytes * 8 / time_gen)) Kbit/s"
        fi

        if [[ "${multi_pdu_mode}" == "on" ]]; then
                display_entire_ipdu_report
        fi
        echo "M7_0 core load:           ${M7_0_LOAD}%"
        echo "M7_1 core load:           ${M7_1_LOAD}%"
        echo "#############################################################"

}

set_trap
check_input "$@"
run_perf
display_report
