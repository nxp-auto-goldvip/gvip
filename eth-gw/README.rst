================
Ethernet Gateway
================

The Ethernet gateway currently supports the following use cases:

 - Layer 2 (bridge/switch) ETH forwarding
 - Layer 3 (router) IP forwarding

Both use cases can be run either in slow-path mode with Cortex-A53 cores
handling the forwarding or in fast path mode on SJA1110A switch without any
load on A53 cores.

GoldVIP provides scripts that can be used to measure performance in slow-path and
fast-path mode for both UDP and TCP traffic generated with iperf3 from host PC.
Slow-path means the traffic is routed by Linux running on A53 cores. Fast-path
means the data-path traffic is routed by PFE (Packet Forwarding Engine) or
SJA1110 companion switch from the board.

Prerequisites
-------------

 - S32G-VNP-RDB2 board running GoldVIP images.
 - PC with 2 Ethernet ports, running Ubuntu 18.04 (with iperf3, minicom,
   iproute2) or a built GoldVIP Docker image that already contains all the necessary tools.

Running the slow-path use cases
-------------------------------

1. Connect one host PC ETH port to the board's SJA1110A switch Port 2.

2. Connect another PC ETH port to the board's PFE-MAC2 ETH port.
   An USB-to-ETH adaptor can be used as the second PC ETH card but make sure it
   supports Gigabit ETH and is plugged into an USB3.0 port.

3. Start GoldVIP Docker container on PC (see :ref:`building_goldvip_docker_image` chapter)

4. Run on host PC eth-slow-path-host.sh script to measure performance for L2/L3
   forwarding between pfe0 and pfe2, with UDP or TCP traffic, with various
   payload sizes, e.g.::

    sudo ./eth-slow-path-host.sh -L 3 -d full -t UDP <eth0> <eth1>

   The above command is measuring throughput between PC eth0 and eth1 that are
   connected to the board pfe0 and pfe2, in full duplex mode (-d full), with UDP
   traffic (-t UDP) with default packet size (ETH MTU). Use -h option to
   list all available options.

   Note: run ``ip a`` command on your host PC to find out the exact names of the
   interfaces <eth0> and <eth1> connected to the board.

   Note: The script is connecting to target console via /dev/ttyUSB0. In case
   tty port is different on your PC, specify it explicitly with -u argument,
   e.g., -u /dev/ttyUSB1

Running the PFE fast-path use cases
-----------------------------------

1. Follow steps 1-3 from previous section

2. Run on host PC eth-pfe-fast-path-host.sh script to measure the same performance
   scenarios as above but this time offloaded in PFE without involving A53 core::

    sudo ./eth-pfe-fast-path-host.sh -L 3 -d full -t UDP <eth0> <eth1>

   Same notes apply as in previous section.

Running the SJA1110A fast-path use cases
----------------------------------------

1. Connect both host PC ETH ports to the board's SJA1110A Port 2 and Port 3.

2. Run on host PC eth-sja-fast-path-host.sh script to measure the same performance
   scenarios but this time going through SJA1110A switch Port 2 and Port 3::

    sudo ./eth-sja-fast-path-host.sh -L 3 -d full -t UDP <eth0> <eth1>

   Same notes apply as in previous sections.

Running the IDPS slow-path use cases
------------------------------------------------------------------------

This usecase plays prerecorded network traffic from PC, containing valid and invalid/malicious SOME/IP messages to prove the IDPS (Intrusion Detection and Prevention System) running on target. The IDPS is provided by Argus Cyber Security (https://argus-sec.com/) and it is only a trial of the full product. For the full feature set of this IDPS please contact Argus.

1. Connect one host PC ETH port to the board's PFE-MAC2

2. Run on host PC eth-idps-slow-path-host.sh script to send packets from PC ETH port
   to the board's PFE-MAC2. The IDPS will catch invalid messages and send the log back
   to the PC.
   On host PC, run the following command::

     sudo ./eth-idps-slow-path-host.sh <eth-interface>

   Note: Use -h option to see all available arguments.

Connecting to a Wi-Fi network
-------------------------------

1. Insert the Wireless Adapter into the board's USB port.

2. Modify configuration file at /etc/wifi_nxp.conf to choose the Wi-Fi interface to run on

3. Add ssid and passphrase to /etc/wpa_supplicant.conf:

   - If your Wi-Fi network uses a password::

      wpa_passphrase SSID PASSPHRASE >> /etc/wpa_supplicant.conf

   - If you are using a public network::

      echo -e "network={\n\tssid="SSID"\n\tkey_mgmt=NONE\n}" >> /etc/wpa_supplicant.conf

4. Restart Wi-Fi service::

      /etc/init.d/wifi_setup restart
