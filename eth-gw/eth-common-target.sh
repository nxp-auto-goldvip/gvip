#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2020-2021,2023 NXP
#
# This script contains base functions and variables for all scenarios that
# will run on the target machine.

# shellcheck source=eth-gw/eth-common.sh
source "${BASH_SOURCE[0]%/*}/eth-common.sh"

# Global constants
readonly network_bridge_name="br0"

# Default values
layer_number=3
host_mac_pfe0="00:00:00:00:00:00"
host_mac_pfe2="00:00:00:00:00:00"
vlan_id=1

_set_ip() {
    intf=$1
    ip=$2
    ip addr flush dev "${intf}"
    ip addr add "${ip}"/24 dev "${intf}"
}

_bring_up_interface() {
    ip link set "${PFE0_NETIF}" up
    ip link set "${PFE2_NETIF}" up
}

flush_ip() {
    _set_ip "${PFE0_NETIF}" "0.0.0.0"
    _set_ip "${PFE2_NETIF}" "0.0.0.0"
}

set_trap() {
    trap 'echo "An error occurred in file $0, at line ${BASH_LINENO[0]}" ; exit ${GENERAL_ERR}' ERR
}

# Create a standalone bridge if it doesn't exist in the first place.
create_bridge() {
    if [ ! -e /sys/class/net/"${network_bridge_name}" ]; then
        ip link add "${network_bridge_name}" type bridge
        ip link set dev "${network_bridge_name}" up
    fi
}

setup_bridge() {
    _bring_up_interface

    # Set the IP for the network bridge.
    _set_ip "${network_bridge_name}" "10.0.1.100"

    # Set both PFE interfaces in bridge configuration.
    ip link set dev "${PFE0_NETIF}" master "${network_bridge_name}"
    ip link set dev "${PFE2_NETIF}" master "${network_bridge_name}"
}

delete_bridge() {
    if [ -e /sys/class/net/"${network_bridge_name}" ]; then
        ip link set dev "${network_bridge_name}" down
        ip link delete "${network_bridge_name}"
    fi
}

delete_pfe_fast_path() {
    libfci_cli route-and-cntk-reset --all
    libfci_cli phyif-update --i emac0 --mode "${EMAC0_DEFAULT_MODE}" --enable --promisc OFF
    libfci_cli phyif-update --i emac2 --mode "${EMAC2_DEFAULT_MODE}" --enable --promisc OFF
}

check_input() {
    while [ $# -gt 0 ]; do
        case "$1" in
            -h|--help)
                usage
                exit
                ;;
            -L)
                shift
                layer_number=$1
                if [ "${layer_number}" -ne 2 ] && [ "${layer_number}" -ne 3 ]; then
                    echo "Invalid forwarding level!"
                    usage
                    exit "${INVALID_USER_ARGUMENT_ERR}"
                fi
                ;;
            -m0)
                shift
                host_mac_pfe0=$1
                if [ "${host_mac_pfe0}" = "00:00:00:00:00:00" ]; then
                    echo "Invalid MAC address!"
                    usage
                    exit "${INVALID_USER_ARGUMENT_ERR}"
                fi
                ;;
            -m1)
                shift
                host_mac_pfe2=$1
                if [ "${host_mac_pfe2}" = "00:00:00:00:00:00" ]; then
                    echo "Invalid MAC address!"
                    usage
                    exit "${INVALID_USER_ARGUMENT_ERR}"
                fi
                ;;
            -V)
                shift
                vlan_id=$1
                if [ "${vlan_id}" -ne 1 ]; then
                    echo "Using non default VLAN ID!"
                fi
                ;;
            *)
                echo "Invalid option!"
                usage
                exit "${INVALID_USER_ARGUMENT_ERR}"
                ;;
        esac; shift;
    done
}

delete_log() {
    rm -rf /tmp/sar_data*
}
