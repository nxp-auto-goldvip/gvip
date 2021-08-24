===========
CAN Gateway
===========

The CAN gateway currently supports the following use-case:
 - CAN to CAN 1:1 frame routing on Cortex-M7 core (slow-path)
 - CAN to CAN 1:1 frame routing on LLCE (fast-path)

The CAN gateway is based on EB Tresos AutoCore Platforms 8.8.1 for S32G27X.
It is distributed in binary format.
It is loaded from an SD card FAT partition, then booted to Cortex-M7 core 0 of S32G27X platform, by the bootloader

The default LLCE CAN routing configuration included in GoldVIP package is:

VIP provides the canperf tool to generate CAN traffic from Linux/A53 on Flex-CAN
and measure CAN forwarding performance between two LLCE-CAN ports connected to
two Flex-CAN ports, e.g.::

       +---------------------+                   +---------------------+
       |  canperf/Linux/A53  |                   |    CAN-GW/M7        |
       |               +-----+-----+      +------+-----+               |
       | CAN-GEN  ---> | Flex-CAN0 |<====>| LLCE-CAN0  |<---+          |
       |               +-----+-----+      +--/\--+-----+    |          |
       |                     |         FAST  ||  |          |SLOW      |
       |                     |         ROUTE ||  |          |ROUTE     |
       |               +-----+-----+      +--\/--+-----+    |          |
       | CAN-DUMP <--- | Flex-CAN1 |<====>| LLCE-CAN1  |<---+          |
       |               +-----+-----+      +-----+------+               |
       |                     |                   |                     |
       +---------------------+                   +---------------------+

Prerequisites
-------------
 - S32G-VNP-RDB2 board running GoldVIP images

Running the measurements
------------------------
1. About:

   These commands will measure throughput of CAN frames routing between the configured CAN ports (``-t can0 -r can1``).
   The used CAN frames are 8(``-s 8``) to 64-bytes in size. A configured ms gap(``-g 10``) is used between consecutive frames.

2. HW setup:

   Connect Flex-CAN0 to LLCE-CAN0 and Flex-CAN1 to LLCE-CAN1. To locate the CAN
   connector and pins check the figures from the appendix. The CAN wires should
   be directly connected High to High and Low to Low.

3. Run CAN perf script:

   a) Parameter description:

    - | ``-t`` CAN transmit interface -use the values as per CAN-GW configuration. For the default CAN-GW configuration provided in GoldVIP, use the values as indicated for each flow(e.g. slow path, fast path, ...) in below sub-chapters
    - | ``-r`` CAN receive interface -use the values as per CAN-GW configuration. For the default CAN-GW configuration provided in GoldVIP, use the values as indicated for each flow(e.g. slow path, fast path, ...) in below sub-chapters
    - | ``-i`` id of transmit CAN frame -use the values as per CAN-GW configuration. For the default CAN-GW configuration provided in GoldVIP, use the values as indicated for each flow(e.g. slow path, fast path, ...) in below sub-chapters
    - | ``-o`` id of receive CAN frame -use the values as per CAN-GW configuration. For the default CAN-GW configuration provided in GoldVIP, use the values as indicated for each flow(e.g. slow path, fast path, ...) in below sub-chapters
    - | ``-s`` CAN frame data size in bytes
    - | ``-g`` frame gap in milliseconds between two consecutive generated CAN frames, use any integer >= 0
    - | ``-l`` the length of the CAN frames generation session in seconds, use any integer > 1

   b) For slow path:

    - Use the following arguments combinations which match the GoldVIP default configuration for CAN-GW

      | -t can0 -r can1 -i 0 -o 4
      | -t can1 -r can0 -i 2 -o 3

    ex: ``./canperf.sh -t can0 -r can1 -i 0 -o 4 -s 8 -g 10 -l 10``

  c) For fast path:

     - Use the following arguments combinations which match the GoldVIP default configuration for CAN-GW

      | -t can0 -r can1 -i 245 -o 245
      | -t can1 -r can0 -i 246 -o 246

   ex: ``./canperf.sh -s 8 -g 10 -i 245 -o 245 -t can0 -r can1 -l 10``

  Note: Please run ``./canperf.sh -h`` to see all the available options.

Patching the EB AutoCore OS
---------------------------

The distributed CAN-GW binary is compiled from an EB Tresos AutoCore Platform 8.8.1 that uses some patches for the OS plugin.
Before building the CAN-GW application, one has to patch the EB AutoCore OS to get the same functionality present in the distributed image.
These patches can be found under `<GoldVIP_binaries_path>/configuration/can-gw/patches` and they shall be applied on the OS plugin that can be found under `<EB_Tresos_install_path>/plugins/Os_TS_T40D33M6I0R0`.

There are various ways of applying these patches, such as using the UNIX `patch` tool (i.e., ``patch -p0 < <file.patch>``) or a git-specific command like `git-apply` (i.e., ``git apply -p0 <file.patch>``).
For example, one can use the following commands to apply all the existing patches::

  cd <EB_Tresos_install_path>/plugins/Os_TS_T40D33M6I0R0
  git apply -p0 <GoldVIP_binaries_path>/configuration/can-gw/patches/*.patch
