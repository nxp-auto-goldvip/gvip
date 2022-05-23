#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2022 NXP

# This script generates a multi-PDU CAN payload based on the input payloads, ID and size values received as parameters

# Enable bash strict mode (i.e. fail on any non-zero exit code)
# undefined variable reference and prevent masked pipeline errors).
set -euo pipefail
# Fail on unset variables usage.
set -o nounset
# Inherit the ERR trap.
set -E

# 3 byte hex formatted ID prepended to each contained PDU
pdu_id=()

# 1 byte hex formatted DLC  prepended to each contained DLC
pdu_dlc=()

# hex formatted payload (maximum of 60 bytes)
pdu_payload=()

readonly integer_regex="^[0-9]+$"
readonly hex_regex="^[0-9A-Fa-f]+$"

#pdu_id max value is 0xFFFFFF (16777215)
declare -ri max_id_value=0xFFFFFF

#For short identifiers the metadata for each dynamic PDU is 4 bytes
readonly metadata_size=4
#there are max 64 bytes in a can FD frame 
readonly max_can_fd_bytes=64
#the max size of a DLC for a single dynamic PDU payload is the max size of a frame - the size of the metadata
declare -ri max_dlc_value="${max_can_fd_bytes}"-"${metadata_size}"

set_trap() {
    trap 'echo "An error occurred in file $0, at line ${BASH_LINENO[0]}" ; exit 1' ERR
}

# Print usage information
usage() {
        echo -e "Usage: ./$(basename "$0") [options]
OPTIONS:
        -i | --pdu-id <decimal value>        ID value for the contained PDU (3 bytes long)
        -s | --pdu-dlc <decimal value>       DLC value for the contained PDU (1 byte long)
        -D | --payload <hex value>       Payload for the contained PDU
        -h | --help                     help
"
}

# Parse  user arguments
check_input() {
        while [[ $# -gt 0 ]]; do
                case "${1}" in
                -i | --pdu-id)
                        shift
                        pdu_id+=("${1}")
                        if ! [[ "${1}" =~ ${integer_regex} ]]; then
                                echo "Error at parameter -i ${1}: PDU ID must be an integer value (e.g. 1)"
                                exit 1
                        fi
                        if [[ "${1}" -gt "${max_id_value}" ]]; then
                                echo "Error at parameter -i ${1}: PDU ID must be 3 bytes long (value must not be greater than 16777215) "
                                exit 1
                        fi
                        ;;
                -s | --pdu-dlc)
                        shift
                        pdu_dlc+=("${1}")
                        if ! [[ "${1}" =~ ${integer_regex} ]]; then
                                echo "Error at parameter -s ${1}: PDU DLC must be an integer value (e.g. 11)"
                                exit 1
                        fi
                        if [[ "${1}" == 0 ]]; then
                                echo "Error at parameter -s ${1}: PDU DLC must be greater than 0"
                                exit 1
                        fi
                        if [[ "${1}" -gt "${max_dlc_value}" ]]; then
                                echo "Error at parameter -s ${1}: PDU DLC must be smaller than or equal to ${max_dlc_value} bytes "
                                exit 1
                        fi
                        ;;
                -D | --payload)
                        shift
                        pdu_payload+=("${1}")
                        if ! [[ "${1}" =~ ${hex_regex} ]]; then
                                echo "Payload data must be a hex value (e.g., 123456789ABC)"
                                exit 1
                        fi
                        if ! [[ "${#1}" -gt 1 ]]; then
                                echo "Error at parameter -D ${1}: PDU payload must be at least one byte long (e.g. 00)"
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

        # Check if we have an equal number of id's,dlc's and payloads
        if [[ ${#pdu_id[@]} -ne ${#pdu_dlc[@]} || ${#pdu_dlc[@]} -ne ${#pdu_payload[@]} ]]; then
                echo "User should set the same number of ID's, DLC's and payloads."
                usage
                exit 1
        fi

        # Check if there is at least one ID. DLC. payload parameter set
        if [[ ${#pdu_id[@]} == 0 ]]; then
                echo "At least one PDU ID , DLC , and payload parameter should be set by user."
                usage
                exit 1
        fi
}

# Generate a multi-pdu payload from previously read parameters
gen_multi_pdu_payload() {
        local multi_pdu_payload=""
        local total_bytes_in_message=0
        for index in "${!pdu_id[@]}"; do
                #final sanity check for parameters
                if [[ "${#pdu_payload[$index]}" -ne 2\*"${pdu_dlc[$index]}" ]]; then
                        echo "Error at parameter -s ${pdu_dlc[$index]}: "\
                             "The number of bytes in the payload must match the corresponding DLC"
                        exit 1
                fi
                ((total_bytes_in_message+=pdu_dlc[index]+metadata_size))

                if [[ "${total_bytes_in_message}" -gt "${max_can_fd_bytes}" ]]; then
                        echo "Error at parameters -s ${pdu_dlc[$index]} , -D ${pdu_payload[$index]}: "\
                             "The total number of bytes of payload + metadata "\
                             "must not exceeded the size of a frame"
                        exit 1
                fi
                #convert ID and DLC  information into hex
                hex_pdu_id="${pdu_id[$index]}";
                hex_pdu_id=$(printf %06X "${hex_pdu_id}")
                #change the endianness of the ID to little-endian 
                hex_pdu_id=$(echo -n "${hex_pdu_id}" | tac -rs ..)
                hex_pdu_dlc="${pdu_dlc[$index]}";
                hex_pdu_dlc=$(printf %02X "${hex_pdu_dlc}")
                #construct the payload
                multi_pdu_payload+="${hex_pdu_id}${hex_pdu_dlc}${pdu_payload[$index]}"
        done
        echo "${multi_pdu_payload}" 
}

set_trap
check_input "$@"
gen_multi_pdu_payload