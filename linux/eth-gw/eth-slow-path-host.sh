#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2020-2021 NXP
#
# This script implements the host machine logic for the L2/L3 forward slow path scenario.
#
# The slow path scenario demonstrates that the traffic can flow between the two configured
# host interfaces using the Linux network stack running on the remote A53 core. 
#
# The host is implied to have 2 network adapters available in order to handle TCP/UDP segments 
# injected via iperf3 by the target machine. The test metrics are available under a report generated
# by the "sar" Linux utility. This script will take care of setting up the L3 route between the
# two interfaces belonging to separate network namespaces.

# shellcheck source=linux/eth-gw/eth-common-host.sh
source "${BASH_SOURCE[0]%/*}/eth-common-host.sh"

# Global constants
readonly target_script="eth-slow-path-target.sh"

_set_route() {
    local ns=$1
    local intf=$2
    local ip=$3

    if [ "${ip}" = "10.0.1.1" ]; then
            ip netns exec "${ns}" ip route add "192.168.100.0/24" via "10.0.1.2" dev "${intf}"
    else
            ip netns exec "${ns}" ip route add "10.0.1.0/24" via "192.168.100.2" dev "${intf}"
    fi
}

# Enable routing between the two host interfaces.
setup_l3_router() {
    ping_return="${GENERAL_ERR}"

    _set_ip_for_netns "nw_ns0" "${eth_interface0}" "${ip_eth0}"
    ip netns exec nw_ns0 ping -c 4 "10.0.1.2" && ping_return=$?
    if [ "${ping_return}" -ne 0 ]; then
        ip_eth0="192.168.100.1"
        ip_eth1="10.0.1.1"
    else
        ip_eth0="10.0.1.1"
        ip_eth1="192.168.100.1"
    fi

    echo "Setting IP ${ip_eth0} to ${eth_interface0} in nw_ns0..."
    _set_ip_for_netns "nw_ns0" "${eth_interface0}" "${ip_eth0}"
    echo "Setting IP ${ip_eth1} to ${eth_interface1} in nw_ns1..."
    _set_ip_for_netns "nw_ns1" "${eth_interface1}" "${ip_eth1}"

    _set_route "nw_ns0" "${eth_interface0}" "${ip_eth0}"
    _set_route "nw_ns1" "${eth_interface1}" "${ip_eth1}"
}

_setup_target() {
    echo "/home/root/eth-gw/${target_script} -L ${layer_number}" > "${uart_dev}"
}

set_trap
check_input "$@"
_setup_target
setup_host
run_test
show_log
clean_up
