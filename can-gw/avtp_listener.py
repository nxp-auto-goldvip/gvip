#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-
"""
This program is used to sniff AVTP (IEEE1722) traffic from a given interface
and log it to a file. By default, the program listens on aux0 interface

Example usage: python3 avtp_listener.py -i <interface>

Copyright 2021, 2023 NXP
"""
import argparse
import socket
import struct

# Maximum input buffer size
MAX_SOCK_BUFF_SIZE_BYTES = 1500

# AVTP traffic identificator
AVTP_ETHER_TYPE = 0x22F0

# ETH traffic identificator masks
ETH_MESSAGE_TYPE_MASK = 0xFE00
ETH_MESSAGE_LENGTH_MASK = 0x01FF
# header size containing information about sender and receiver
L2_HEADER_LEN_BYTES = 14

# AVTP-CAN parameters
CAN_FD_MESSAGE_ID_REL_OFFSET_BYTES = 4
CAN_FD_MESSAGE_ID_LEN_BYTES = 4
CAN_DATA_OFFSET_BYTES = CAN_FD_MESSAGE_ID_REL_OFFSET_BYTES \
    + CAN_FD_MESSAGE_ID_LEN_BYTES
CAN_BRIEF_MESSAGE_TYPE = 0x02
AVTP_COMMON_STREAM_HEADER_LEN_BYTES = 12
ACF_HEADER_LEN_BYTES = 2

# Number of received bytes received by the raw socket
SIZE = 0

def coalesce_messages_from_avtp_by_id(raw_data):
    """ Skip the L2 and AVTP header and coalesce the CAN message
        payloads from the ACF messages by the CAN identifier.
        :param raw_data: raw packet data received via socket
        :return can_messages: dictionary contaning the message ids
        as keys and data as values, per each of the messages.
    """
    # pylint: disable=global-statement
    global SIZE
    # Skip L2 Header and AVTP Stream Header
    idx = L2_HEADER_LEN_BYTES + AVTP_COMMON_STREAM_HEADER_LEN_BYTES
    can_messages = {}

    # Iterate over each message and gather the CAN data for each identifier.
    while idx < len(raw_data):
        raw_header = struct.unpack('!H', raw_data[idx:idx + ACF_HEADER_LEN_BYTES])[0]
        # xxxx xxx- ---- ----
        message_type = int(raw_header & ETH_MESSAGE_TYPE_MASK) >> 9
        # ---- ---x xxxx xxxx (given in quadlets)
        message_len_bytes = int(raw_header & ETH_MESSAGE_LENGTH_MASK) * 4

        # calculate how much data has been received by the socket
        SIZE = SIZE + message_len_bytes - CAN_DATA_OFFSET_BYTES
        if CAN_BRIEF_MESSAGE_TYPE == message_type:
            message_id = struct\
                .unpack('!L',
                        raw_data[idx + CAN_FD_MESSAGE_ID_REL_OFFSET_BYTES:
                                 idx + CAN_FD_MESSAGE_ID_REL_OFFSET_BYTES +
                                 CAN_FD_MESSAGE_ID_LEN_BYTES])[0]
            if message_id in can_messages:
                can_messages[message_id].extend(raw_data[
                                                   idx + CAN_DATA_OFFSET_BYTES:
                                                   idx + message_len_bytes])
            else:
                can_messages[message_id] = bytearray()

        idx += message_len_bytes

    # save to stdout
    print(f"Received data size: {SIZE}")
    return can_messages


def main():
    """
    Runnable
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--interface", dest="interface", type=str, default='aux0sl')
    args = parser.parse_args()

    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(AVTP_ETHER_TYPE)) \
            as raw_socket:
        raw_socket.bind((args.interface, 0))
        while True:
            raw_packet = raw_socket.recv(MAX_SOCK_BUFF_SIZE_BYTES)
            print(coalesce_messages_from_avtp_by_id(raw_packet))

if __name__ == "__main__":
    main()
