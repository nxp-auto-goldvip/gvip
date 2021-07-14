#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2021 NXP
#
# This script implements the host machine logic for L3 forwarding slow path scenario using IDPS.
#
# In this case, traffic containing malicious PDUs is replayed on the PFE2 interface for
# the target to detect the malicious SOME/IP messages via the IDPS 
# (intrusion detection and prevention system) solution provided 
# by Argus and report it back via a log.
#
# The malicious traffic is injected via a PCAP file, which can be replaced by
# the user if needed.

# shellcheck source=linux/eth-gw/eth-common-host.sh
source "${BASH_SOURCE[0]%/*}/eth-common-host.sh"

# Global constants
readonly target_eth_port="pfe2"
readonly idps_target_log="/tmp/idps_target_$(date +%H_%M_%S).log"
readonly idps_host_log="/tmp/idps_host_$(date +%H_%M_%S).log"
readonly tcpreplay_timeout=10
readonly pcap_packet_count=2967
# Replay the PCAP traffic 20 times, as this is the maximum rate 
# at which the IDPS demo won't miss PDUs.
# The PCAP file containts 2967 packets, thus the ETA is aprox. 10 seconds.
readonly times_to_run=20

# Default values
# Maximum IDPS target speed measured in packets/seconds.
speed=35000
pcap_file="$(dirname "${BASH_SOURCE[0]}")/someip_packets.pcapng"

_check_eth_port() {
    local ping_return=0
    local eth_port="$1"
    local ip_host="10.0.101.1"
    local ip_target="10.0.101.2"

    # Setup IP for pfe2 on board to 10.0.101.2
    echo "ip link set pfe2 up" > "${uart_dev}"
    # Sleep 2 seconds for PFE driver bring up.
    sleep 2
    echo "ip addr flush dev ${target_eth_port}" > "${uart_dev}"
    echo "ip addr add ${ip_target}/24 dev ${target_eth_port}" > "${uart_dev}"

    echo "Check port in device"
    ip addr flush dev "${eth_port}"
    ip addr add "${ip_host}"/24 dev "${eth_port}"

    ping -I "${eth_port}" -c 4 "${ip_target}" || ping_return=$?

    if [ "${ping_return}" -ne 0 ]; then
        echo "Could not detect any connection between ${eth_port} and PFE2!"
        _clean_up
        exit "${INVALID_CONFIG_ERR}"
    fi
}

_check_pcap_file() {
    if [ ! -e "$1" ]; then
        echo "Invalid input file: $1 does not exist!"
        _usage
        exit "${INVALID_USER_ARGUMENT_ERR}"
    fi
}

_usage() {
    echo -e "Usage: sudo ./$(basename "$0") [option] <eth_interface>
Play recorded network traffic containing valid and invalid/malicious SOME/IP messages to prove the IDPS running on target.\n
eth_interface: Host Ethernet interface connected to PFE2 port.

OPTIONS:
        -s <speed>              Send packets at a given packets/sec (default is 35000 packets/sec)
        -f <pcap_file>          PCAP file that contains the network traffic sent to target (default is someip_packets.pcapng)
        -u <tty_device>         UART device connected to target (default is /dev/ttyUSB0)
        -h                      help"
}

_check_input() {
    while [ $# -gt 0 ]; do
        case "$1" in
            -h)
                _usage
                exit
                ;;
            -s)
                shift
                speed=$1
                if [[ ! ${speed} =~ ${integer_regex} ]] || [[ ${speed} == 0 ]]; then
                    echo "Speed shall be a positive integer!"
                    _usage
                    exit "${INVALID_USER_ARGUMENT_ERR}"
                fi
                ;;
            -f)
                shift
                pcap_file=$1
                ;;
            -u)
                shift
                uart_dev=$1
                if ! [ -c "${uart_dev}" ]; then
                    echo "Wrong tty device!"
                    _usage
                    exit "${INVALID_USER_ARGUMENT_ERR}"
                fi
                ;;
            *)
                if [ $# -eq 1 ]; then
                    eth_idps=$1
                else
                    echo "Wrong input option!"
                    _usage
                    exit "${INVALID_USER_ARGUMENT_ERR}"
                fi
                ;;
        esac; shift;
    done

    _check_pcap_file "${pcap_file}"
    _check_eth_port "${eth_idps}"
}

_setup_target() {
    echo -e "\nRunning sar on target to get CPU load.\n"
    echo "sar -P ALL 1 > ${sar_log} &" > "${uart_dev}"
    echo "/home/root/eth-gw/eth-idps-slow-path-target.sh -n $((times_to_run*pcap_packet_count)) > ${idps_target_log}" > "${uart_dev}"
}

_setup_host() {
    # Set baudrate when write to tty device.
    stty -F "${uart_dev}" 115200
}

_run_tcpreplay() {
    echo "Running tcpreplay to inject prerecorded traffic into the PFE2 interface..."
    tcpreplay -l "${times_to_run}" -p "${speed}" -i "${eth_idps}" "${pcap_file}" > "${idps_host_log}"

    # Wait for execution to finish.
    sleep "${tcpreplay_timeout}"
    # Kill linux_some_idps process on target when timeout whether it done or not.
    echo "pkill -9 linux_someip_id" > "${uart_dev}"
    echo "pkill -2 sar" > "${uart_dev}"
}

_get_log_target() {
    local ip_host="10.0.101.1"
    local ip_target="10.0.101.2"

    ip addr flush dev "${eth_idps}"
    ip addr add "${ip_host}"/24 dev "${eth_idps}"

    scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@"${ip_target}":"${sar_log}" "${sar_log}"
    scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@"${ip_target}":"${idps_target_log}" "${idps_target_log}"
}

# Print the IDPS host/target logs and the sar log.
_print_log() {
    echo -e "\nIDPS host log:"
    cat "${idps_host_log}"
    echo -e "\nIDPS target log:"
    tail -n 4 "${idps_target_log}"
    echo -e "Target CPU load:\n"
    tail -n 6 "${sar_log}"
}

# Print the IDPS and sar logs' location.
_print_log_location() {
    echo -e "\nLog file at:"
    ls "${idps_target_log}" "${idps_host_log}" "${sar_log}"
}

# Validate the network interface received as argument.
_check_eth_args() {
    eth=$1

    if [ ! -e /sys/class/net/"${eth}" ]; then
        echo -e "Wrong interface, expected member of the list:"
        ls /sys/class/net
        _usage
        exit 1
    fi
}

_check_log_target() {
    # The lines from the log must be preceded by "Overall".
    if ! grep -q "Overall" "${idps_target_log}"; then
        echo -e "\nIDPS failed, check log: ${idps_target_log}"
        _clean_up
        exit "${GENERAL_ERR}"
    fi
}

_show_log() {
    _get_log_target
    _check_log_target
    _print_log
    _print_log_location
}

_clean_host() {
    set +Ee
    trap - ERR

    ip addr flush dev "${eth_idps}"
}

_clean_up() {
    _clean_host
    _clean_target
}

_set_trap() {
    # Set trap handler for INT signal given via the Ctrl-C combination.
    trap "clean_up ; exit 130" INT

    trap 'echo "An error occurred in file $0, at line ${BASH_LINENO[0]}" ; clean_up ; exit ${GENERAL_ERR}' ERR
}

_set_trap
_check_input "$@"
_setup_target
_setup_host
_run_tcpreplay
_show_log
_clean_up
