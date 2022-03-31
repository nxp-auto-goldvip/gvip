#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2022 NXP

# This script generates a secured can payload  based on the input (authentic) payload , and data id values received as parameters
# Currently the secured payload = authentic payload + MAC ( message authentication code)
# The MAC is generated as a HMAC SHA-256 over the data id + authentic payload

# Enable bash strict mode (i.e. fail on any non-zero exit code)
# undefined variable reference and prevent masked pipeline errors).
set -euo pipefail
# Fail on unset variables usage.
set -o nounset
# Inherit the ERR trap.
set -E

# 2 byte hex formatted data id prepended to the payload before generating the mac key
data_id=notset

# 32 byte hex formatted secret key used by MAC algorithm
mac_key=notset

# 32 byte hex formatted payload
authentic_payload=notset

readonly hex_regex="^[0-9A-Fa-f]+$"

set_trap() {
    trap 'echo "An error occurred in file $0, at line ${BASH_LINENO[0]}" ; exit 1' ERR
}

# Print usage information
usage() {
        echo -e "Usage: ./$(basename "$0") [options]
OPTIONS:
        -i | --data-id <hexvalue>        Data ID for the PDU
        -k | --key <hexvalue>            Key used by MAC algorithm
        -D | --payload <hexvalue>        Payload that needs to be secured
        -h | --help                      help
"
}

# Parse  user arguments
check_input() {
        while [[ $# -gt 0 ]]; do
                case "${1}" in
                -i | --data-id)
                        shift
                        data_id=${1}
                        if ! [[ "${data_id}" =~ ${hex_regex} ]]; then
                                echo "Data ID must be a hex value (e.g., 0044)"
                                exit 1
                        fi
                        ;;
                -k | --key)
                        shift
                        mac_key=${1}
                        if ! [[ "${mac_key}" =~ ${hex_regex} ]]; then
                                echo "Key must be a hex value (e.g., 4e5850494e5850494e5850494e5850494e5850494e5850494e5850494e585049)"
                                exit 1
                        fi
                        ;;
                -D | --payload)
                        shift
                        authentic_payload=${1}
                        if ! [[ "${authentic_payload}" =~ ${hex_regex} ]]; then
                                echo "Payload data must be a hex value (e.g., 234D73672073656375726564207573696E6720484D4143205348412D32353623)"
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
        # Check if data_id is set by user
        if [[ "$data_id" == "notset" ]]; then
                echo "Data ID should be set by user."
                usage
                exit 1
        fi

        # Check if mac_key is set by user
        if [[ "${mac_key}" == "notset" ]]; then
                echo "Mac key should be set by user."
                usage
                exit 1
        fi

        # Check if payload is set by user
        if [[ "${authentic_payload}" == "notset" ]]; then
                echo "Payload should be set by user."
                usage
                exit 1
        fi

}

# Generate a secured payload from previously read parameters
gen_secure_payload() {
        #The openssl command line executable does not accept inputs in a hex format so we need to first convert the input values in a binary format

        #The command splits the string into groups of two and prepends a \x to each group
        processed_data_id="$(awk '{gsub(/.{2}/,"\\x&")}1' <<< "${data_id}")"
        #The command splits the string into groups of two and prepends a \x to each group
        processed_payload="$(awk '{gsub(/.{2}/,"\\x&")}1' <<< "${authentic_payload}")"
        #Constructing the input payload for the mac (data id + authentic payload)
        echo_payload="${processed_data_id}${processed_payload}"

        #The result from the echo command needs to be piped directly to  openssl without using additional variables
        #Bash does not properly handle strings containing \0 characters in the middle of the string(the hex value of \0 is 0x00)
        #Resulting MAC code is outputted by the openssl command
        #The awk command extracts the second word out of the openssl output (the mac is the second word)
        mac=$(echo -e -n "${echo_payload}" | openssl sha256 -hex -mac HMAC -macopt hexkey:"${mac_key}" | awk '{print $2}')
        #return secure payload (authentic payload + mac)
        echo "${authentic_payload}${mac}"
}

set_trap
check_input "$@"
gen_secure_payload
