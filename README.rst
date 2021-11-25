===================
GoldVIP Quick Start
===================

This guide contains the steps to quickly deploy GoldVIP images, setup the board
connectivity and try out some vehicle gateway use cases.

Setup cable connections
=======================

To locate the connectors and ports from the board check the figures from the
appendix or check S32G-VNP-RDB2 Quick Start Guide from the board's box.

1. Connect the power cable

2. Connect the board's UART0 serial port to PC using the USB cable from the box.

Deploy GoldVIP images
=====================

Download GoldVIP binary images from `here <https://are.nxp.com/FlexNetCatalog.aspx>`_.

Deploy GoldVIP SD-card image
----------------------------

1. Check the device name under which your SD-card is installed on PC so that you
   won't overwrite another disk. Use `cat /proc/partitions` command before and 
   after inserting SD-card, see which new sd* disk appears (e.g., /dev/sdb) and
   use it's name in the next step command.

2. Write fsl-image-goldvip on SD-card plugged into the Linux host PC, e.g.::

    sudo dd if=fsl-image-goldvip-s32g274ardb2.sdcard of=/dev/sdb bs=1M status=progress && sync

At this point you can plug in the SD-card power on the board and it will boot
u-boot + Linux from SD-card. For trying out Ethernet and cloud telemetry
use cases you can skip the boot-loader deployment from next section. However,
for CAN use cases you need to follow the steps from next section too.

.. _deploying_realtime_bootloader:

Deploy Real Time Bootloader
----------------------------

The real time bootloader runs on Cortex-M7-0 and is loaded from QSPI NOR flash.
It's main function is to load u-boot on Cortex-A53 cores and the real-time
applications on Cortex-M7 cores.

To write boot-loader in NOR flash, first boot from SD-card using the above
SD-card image, stop in u-boot console when prompted, and run the following command,
which writes all the images in flash::

    run write_goldvip_images

This operation shall take at most 20 seconds. It is also possible to update images in flash 
individually:

1. Update boot-loader image::

    run write_bootloader

2. Update U-Boot image::

    run write_uboot

3. Update CAN-GW binary::

    run write_cangw

After all the binaries are written, power off the board, configure the DIP switches
for NOR Flash Boot mode (set SW4.7 to OFF) and then power on the board.
