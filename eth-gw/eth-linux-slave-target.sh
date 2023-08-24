#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2023 NXP
#
# This script can be used after the boot to configure the PFE so that the network
# traffic is routed by default to the Linux network interfaces.

# shellcheck source=eth-gw/eth-common-target.sh
source "${BASH_SOURCE[0]%/*}/eth-common-target.sh"

# The PFE Linux network interfaces.
readonly PFE_NETIFS=("${PFE0_NETIF}" "${PFE2_NETIF}")
# The MAC addresses assigned to the PFE instance running on the Cortex-M7 core.
readonly M7_MAC_ADDRS=("77:55:44:33:22:11" "66:55:44:33:22:11")
# File used to store the initial FCI configuration.
readonly FCI_DUMP_FILE="/var/log/fci_dump"

#######################################
# Print a help message to the stdout.
# Globals:
#   INVALID_USER_ARGUMENT_ERR
# Arguments:
#   N/A
# Outputs:
#   Help message
#######################################
usage() {
    echo -e "Usage: ./$(basename "$0") [option]
Configures the PFE to route the traffic received on EMAC0 and EMAC2 to the
Linux PFE slave driver instance by default.\n
OPTIONS:
        -h|--help                      help"
}

#######################################
# Helper function to check the list of parameters.
# Globals:
#   INVALID_USER_ARGUMENT_ERR
# Arguments:
#   N/A
# Outputs:
#   N/A
#######################################
check_input() {
    while [ $# -gt 0 ]; do
        case "$1" in
            -h|--help)
                usage
                exit
                ;;
            *)
                echo "Invalid option!"
                usage
                exit "${INVALID_USER_ARGUMENT_ERR}"
                ;;
        esac; shift;
    done
}

#######################################
# Dump the initial physical & logical interfaces configuration.
# Globals:
#   FCI_DUMP_FILE
# Arguments:
#   N/A
# Outputs:
#   N/A
#######################################
dump_fci_config() {
    libfci_cli phyif-print --verbose &> "${FCI_DUMP_FILE}"
}

#######################################
# Configure the PFE physical and logical interfaces to allow RX/TX traffic
# on the PFE Linux interfaces by default.
# Globals:
#   A53_ASSIGNED_HIF, M7_ASSIGNED_HIF, M7_MAC_ADDRS, PFE_NETIFS, PFE_PHYIFS
# Arguments:
#   N/A
# Outputs:
#   N/A
#######################################
configure_pfe() {
    for i in "${!PFE_NETIFS[@]}"; do
        local logif_name="${PFE_NETIFS[$i]%sl}M7"

        # Re-configure the egress HIF in order to send the ethernet packets to the Linux
        # instance by default.
        libfci_cli logif-update --interface "${PFE_NETIFS[$i]%sl}" --enable \
            --promisc ON --egress "${A53_ASSIGNED_HIF}"

        # Delete the logical interface added by the Linux slave driver, if it exists.
        libfci_cli logif-del --interface "s9.${PFE_NETIFS[$i]}" || true

        # Add a new logical interface that shall forward the traffic to the PFE instance
        # running on the Cortex-M7.
        if ! libfci_cli logif-print --interface "${logif_name}" &> /dev/null; then
            libfci_cli logif-add --interface "${logif_name}" --parent "${PFE_PHYIFS[$i]}"
        fi

        libfci_cli logif-update --interface "${logif_name}" --egress ${M7_ASSIGNED_HIF} --enable \
            --promisc OFF --match-mode OR --dmac "${M7_MAC_ADDRS[$i]}" --match-rules TYPE_BCAST,DMAC
    done
}

set_trap
check_input "$@"
dump_fci_config
configure_pfe
