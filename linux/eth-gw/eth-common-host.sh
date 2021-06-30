#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2020-2021 NXP
#
# This script contains base functions and variables for all scenarios that
# will run on the host machine. 

# shellcheck source=linux/eth-gw/eth-common.sh
source "${BASH_SOURCE[0]%/*}/eth-common.sh"

# Global constants
readonly nw0_log=/tmp/nw0_$(date +%H_%M_%S).log
readonly nw1_log=/tmp/nw1_$(date +%H_%M_%S).log
readonly sar_log=/tmp/sar_data_$(date +%H_%M_%S).log

# Default values
layer_number=3
duplex="full"
stream_type="UDP"
duration=30
payload_size=0
uart_dev="/dev/ttyUSB0"
ip_eth0="10.0.1.1"
ip_eth1="10.0.1.2"

# Validate the network interfaces received as arguments.
_check_eth_args() {
    local eth0=$1
    local eth1=$2

    if [ "${eth0}" = "${eth1}" ]; then
        echo "Interfaces must be different!"
        exit "${INVALID_USER_ARGUMENT_ERR}"
    fi

    if [ ! -e /sys/class/net/"${eth0}" ] || [ ! -e /sys/class/net/"${eth1}" ]; then
        echo -e "Wrong interface, expected member of the list:"
        ls /sys/class/net
        usage
        exit "${INVALID_USER_ARGUMENT_ERR}"
    fi
}

_set_ip_for_netns() {
    local ns=$1
    local intf=$2
    local ip=$3
    
    ip netns exec "${ns}" ip addr flush dev "${intf}"
    ip netns exec "${ns}" ip addr add "$ip/24" dev "${intf}"
}

_setup_l2_switch() {
    echo "Set IP ${ip_eth0} to ${eth_interface0} in nw_ns0"
    _set_ip_for_netns "nw_ns0" "${eth_interface0}" "${ip_eth0}"
    echo "Set IP ${ip_eth1} to ${eth_interface1} in nw_ns1"
    _set_ip_for_netns "nw_ns1" "${eth_interface1}" "${ip_eth1}"
}

_create_network_namespace() {
    echo "Creating nw_ns0 and nw_ns1 network namespaces..."
    for i in 0 1; do
        if [ -e /var/run/netns/nw_ns"${i}" ]; then
            echo "nw_ns${i} network space already created!"
        else
            ip netns add nw_ns"${i}"
        fi
    done
}

_setup_network_namespace() {
    # Add physical interfaces to the corresponding network namespace.
    echo "Adding ${eth_interface0} interface to nw_ns0..."
    ip link set "${eth_interface0}" netns nw_ns0
    echo "Adding ${eth_interface1} interface to nw_ns1..."
    ip link set "${eth_interface1}" netns nw_ns1

    # Bring interfaces up.
    ip netns exec nw_ns0 ip link set dev "${eth_interface0}" up
    ip netns exec nw_ns1 ip link set dev "${eth_interface1}" up

    if [ "${layer_number}" -eq 2 ]; then
        _setup_l2_switch
    else
        setup_l3_router
    fi
}

_run_iperf3_server() {
    echo "Turning on iperf3 server for both network namespaces..."
    ip netns exec nw_ns0 iperf3 -s -D -1 -B "${ip_eth0}" -p 5678 &
    ip netns exec nw_ns1 iperf3 -s -D -1 -B "${ip_eth1}" -p 5678 &
}

_ping_check_ns() {
    echo -e "\nChecking network between the network namespaces"
    ip netns exec nw_ns1 ping -c 4 "${ip_eth0}" &> /dev/null && \
    ip netns exec nw_ns0 ping -c 4 "${ip_eth1}" &> /dev/null && \
    ping_return=0
}

_check_network_ns() {
    local ping_return=1
    local retries=3

    _ping_check_ns || true

    while ((ping_return != 0 && retries > 0)); do
        ((retries--))
        echo "Failed to connect to the network!"
        echo "Retrying..."
        _clean_host
        setup_host
        _ping_check_ns || true
    done

    if ((ping_return == 0)); then
        echo -e "Network connected!\n"
    else
        echo -e "Failed to connect to the network!\n"
        clean_up
        exit ${NET_ERR}
    fi
}

# Measure throughput from network namespace 0 to network namespace 1 and vice-versa.
_run_performance_test() {
    echo -e "\nRunning sar on target to get CPU load.\n"
    echo "sar -P ALL 1 > ${sar_log} &" > "${uart_dev}"
    echo "Running iperf3 for ${duration} seconds to measure network performance..."

    if [ "${stream_type}" = "UDP" ]; then
        echo "Starting UDP stream"
        iperf_stream="-u"
    else
        echo "Starting TCP stream"
        iperf_stream=""
    fi

    if [ "${duplex}" = "full" ]; then
        ip netns exec nw_ns1 iperf3 -A 0,1 -4 "${iperf_stream}" -b 0 -l "${payload_size}" -t \
        "${duration}" -B "${ip_eth1}" --cport 5001 -c "${ip_eth0}" -p 5678 > "${nw1_log}" &
        ip netns exec nw_ns0 iperf3 -A 2,3 -4 "${iperf_stream}" -b 0 -l "${payload_size}" -t \
        "${duration}" -B "${ip_eth0}" --cport 5001 -c "${ip_eth1}" -p 5678 > "${nw0_log}" &
        wait
    else
        ip netns exec nw_ns1 iperf3 -A 0,1 -4 "${iperf_stream}" -b 0 -l "${payload_size}" -t \
        "${duration}" -B "${ip_eth1}" --cport 5001 -c "${ip_eth0}" -p 5678 > "${nw1_log}"
        ip netns exec nw_ns0 iperf3 -A 2,3 -4 "${iperf_stream}" -b 0 -l "${payload_size}" -t \
        "${duration}" -B "${ip_eth0}" --cport 5001 -c "${ip_eth1}" -p 5678 > "${nw0_log}"
    fi
    echo -e "Kill sar process on target.\n"
    echo "pkill -2 sar" > "${uart_dev}"

    # Wait until pkill gets executed on target.
    sleep 1
}

_get_target_load_log() {
    local host_ip="10.0.1.101"

    _set_ip_for_netns "nw_ns0" "${eth_interface0}" "${host_ip}"

    # Create a bridge on target on both PFE interfaces so that we can 
    # execute the scp below.
    echo "/home/root/eth-gw/eth-bridge-target.sh" > "${uart_dev}"
    # Use scp in nw_ns0 to copy sar log from target to host.
    echo -e "Copy ${sar_log} from target to host via nw_ns0:"
    ip netns exec nw_ns0 scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    root@10.0.1.100:"${sar_log}" "${sar_log}"
}

# Log the network performance logs for both namespaces and the target CPU load.
_print_logs() {
    echo -e "\nNetwork performance from nw_ns1 to nw_ns0 network space:"
    cat "${nw1_log}"
    echo -e "\nNetwork performance from nw_ns0 to nw_ns1 network space:"
    cat "${nw0_log}"

    echo -e "\nTarget CPU load:"
    tail -n 6 "${sar_log}"

    echo -e "\nLog file at:"
    ls "${nw0_log}" "${nw1_log}" "${sar_log}"
}

_delete_network_ns() {
    echo -e "\nDeleting network namespaces..."
    ip netns exec nw_ns0 ip link set "${eth_interface0}" netns 1
    ip netns exec nw_ns1 ip link set "${eth_interface1}" netns 1
    ip netns delete nw_ns0
    ip netns delete nw_ns1
}

_kill_iperf3() {
    echo "Killing iperf3 process..."
    pkill iperf3 || true
}

_clean_host() {
    # Clear the trap handler to avoid infinite loops.
    set +Ee
    trap - ERR

    _delete_network_ns
    _kill_iperf3
}

_clean_target() {
    echo "/home/root/eth-gw/eth-cleanup-target.sh" > "${uart_dev}"
}

usage() {
    echo -e "Usage: sudo ./$(basename "$0") [option] <eth_interface0> <eth_interface1>
Create namespace for each interface and run netperf to measure throughput between them in L2-switch or L3-router usecase.\n
OPTIONS:
        -L <layer_number>       specify network layer to set up
                                layer_number=2 for L2-Switch
                                             3 for L3-Router (default)
        -d <duplex>             select duplex option
                                duplex=half for half-duplex
                                       full for full-duplex (default)
        -t <stream_type>        specify the test to perform
                                stream_type=TCP
                                           =UDP (default)
        -l <seconds>            specify the duration of the test (default is 30 seconds)
        -s <bytes>              TCP or UDP payload size (default is 1448/128k bytes)
        -u <tty_device>         UART device connected to target (default is /dev/ttyUSB0)
        -h                      help"
}

set_trap() {
    # Set trap handler for INT signal given via the Ctrl-C combination.
    trap "clean_up ; exit 130" INT

    trap 'echo "An error occurred in file $0, at line ${BASH_LINENO[0]}" ; clean_up ; exit ${GENERAL_ERR}' ERR
}

check_input() {
    # Check root privileges.
    if [ "${EUID}" -ne 0 ]; then
        echo "Please run as root!"
        usage
        exit "${PRIVILEGE_ERR}"
    fi

    if [ $# -eq 0 ]; then
        echo -e "Please input parameters!\n"
        usage
        exit "${INVALID_USER_ARGUMENT_ERR}"
    fi

    while [ $# -gt 0 ]; do
        case "$1" in
            -h)
                usage
                exit
                ;;
            -L)
                shift
                layer_number=$1
                if [ ! "${layer_number}" -eq 2 ] && [ ! "${layer_number}" -eq 3 ]; then
                    echo "Wrong layer number!"
                    usage
                    exit ${INVALID_USER_ARGUMENT_ERR}
                fi
                ;;
            -d)
                shift
                duplex=$1
                if [ "${duplex}" != "half" ] && [ "${duplex}" != "full" ]; then
                    echo "Wrong duplex number!"
                    usage
                    exit ${INVALID_USER_ARGUMENT_ERR}
                fi
                ;;
            -t)
                shift
                stream_type=$1
                if [ "${stream_type}" != "UDP" ] && [ "${stream_type}" != "TCP" ]; then
                    echo "Wrong stream type!"
                    usage
                    exit ${INVALID_USER_ARGUMENT_ERR}
                fi
                ;;
            -l)
                shift
                duration=$1
                if [[ ! ${duration} =~ ${integer_regex} ]]; then
                    echo "Invalid test duration! -l argument must be a positive integer."
                    usage
                    exit ${INVALID_USER_ARGUMENT_ERR}
                fi
                ;;
            -s)
                shift
                payload_size=$1
                if [[ ! ${payload_size} =~ ${payload_size_regex} ]]; then
                    echo "Invalid payload size type!"
                    usage
                    exit ${INVALID_USER_ARGUMENT_ERR}
                fi
                ;;
            -u)
                shift
                uart_dev=$1
                if [ ! -c "${uart_dev}" ]; then
                    echo "Wrong tty device!"
                    usage
                    exit ${INVALID_USER_ARGUMENT_ERR}
                fi
                ;;
            *)
                if [ $# -eq 2 ]; then
                    eth_interface0=$1
                    eth_interface1=$2
                    _check_eth_args "${eth_interface0}" "${eth_interface1}"
                    shift 1
                else
                    echo "Wrong input option!"
                    usage
                    exit ${INVALID_USER_ARGUMENT_ERR}
                fi
                ;;
        esac; shift;
    done

    # Assign iperf3 payload size default value if it remained unset.
    if [ "${payload_size}" -eq "0" ]; then
        [ "${stream_type}" == "UDP" ] && payload_size=1472 || payload_size="32k"
    fi
}

setup_host() {
    # Set TTY device baudrate.
    stty -F "${uart_dev}" 115200

    _create_network_namespace
    _setup_network_namespace
}

show_log() {
    _get_target_load_log
    _print_logs
}

clean_up() {
    _clean_host
    _clean_target
}

run_test() {
    _check_network_ns
    _run_iperf3_server
    _run_performance_test
}
