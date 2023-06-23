#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2021,2023 NXP
#
# This script implements the target machine logic for the 
# L3 forwarding slow path scenario with IDPS.
#
# In this case, the target machine will execute the IDPS binary provided by Argus,
# taking into account the user config (if provided) and the message count as parameter.
# The traffic is expected to arrive on the PFE2 interface.

# shellcheck source=eth-gw/eth-common-target.sh
source "${BASH_SOURCE[0]%/*}/eth-common-target.sh"

# Global constants
readonly eth_idps_rx="${PFE2_NETIF}"

# Default values
target_message_count=2967
conf_file="/etc/idps.conf"
log_file="/tmp/idps_log.json"

_usage() {
    echo -e "usage: ./$(basename "$0") [option]
Run IDPS application.
OPTIONS:
        -c <config_file>        configuration file for running idps <default is /etc/idps.conf>
        -l <log_file>           log file in json format <Eg: log.json>
        -n <message_count>      number of messages to detect <default is 2967>
        -h                      help"
}

_setup_network() {
    /usr/local/sbin/linux_someip_idps "${conf_file}" "${eth_idps_rx}" "${log_file}" "${target_message_count}" &
}

_check_input() {
    while [ $# -gt 0 ]; do
        case "$1" in
            -h)
                _usage
                exit
                ;;
            -l)
                shift
                log_file=$1
                ;;
            -n)
                shift
                target_message_count=$1
                if [[ ! ${target_message_count} =~ ${integer_regex} ]]
                then
                    echo -e " -n argument shall be a positive integer\n"
                    _usage
                    exit "${INVALID_USER_ARGUMENT_ERR}"
                fi
                ;;
            -c)
                shift
                conf_file=$1
                if [ ! -e "${conf_file}" ]
                then
                    echo "Invalid configuration file"
                    _usage
                    exit 1
                fi
                ;;
            *)
                echo -e "Wrong input options"
                _usage
                exit 1
        esac; shift;
    done
}

set_trap
_check_input "$@"
_setup_network
