Cloud Edge Gateway
==================

Introduction
------------
The Cloud Edge Gateway use case demonstrates telemetry to the cloud using AWS IoT Greengrass.
Telemetry statistics are fetched from the device, calculated and sent to the
cloud counterpart of the application. Statistics received in the cloud are then
displayed into user-friendly graphs. The statistics include but may not be limited to:
Networking accelerator usage statistics, Real-time cores load, Domain-0 VCPU load and
Domain-0 Memory utilization statistics.

The following architecture was employed:

.. image:: cloud-gw-architecture.png

The following access policies to hardware resources are applicable for the virtual machines
(Domain-0 and v2xdomu) described in :ref:`xen_hypervisor` chapter:

- Domain-0 has access to all the hardware resources in the system.

- v2xdomu has access to limited resources which are virtualized by Xen.

Telemetry data is collected from Domain-0 and passed to v2xdomu through a
TCP client-server communication. The Domain-0 v2xbr is a virtual switch with no outbound
physical interface attached to it. This connection is used to pass telemetry data from
Domain-0 to v2xdomu and vice-versa, without outside interference or snooping possibility.
Any change in the configuration (update of the telemetry interval from the cloud) is
communicated from cloud to the Dom0 TCP Server, via the TCP client available on v2xdomu.
This ensures that the system resources are protected from outside interference.
Data is prepared for fetching in the Domain-0 at any given time via a telemetry service
(see ``/etc/init.d/telemetry``) which is started at boot time.

Prerequisites
-------------

- AWS account with SSO enabled. Follow the steps in this guide to enable SSO:
  https://docs.aws.amazon.com/singlesignon/latest/userguide/getting-started.html

  Enabling SSO will grant you access to the SSO console.
  SSO is also required to use the AWS IoT SiteWise Dashboard.
- S32G board with the GoldVIP image deployed and an internet connection.

  **Note**: AWS IoT Greengrass uses ports 8883 and 8443. As a
  security measure, restrictive environments might limit inbound and outbound
  traffic to a small range of TCP ports, which might not include these ports.
  Therefore the provisioning script (described in chapter
  :ref:`connecting-the-board-to-aws`) changes these ports to 443.
  To use the default ports (8883 and 8443) use the arguments
  --mqtt-port and --http-port from the provisioning script.

AWS IAM Permissions
-------------------

A policy for an AWS IAM user, it contains the necessary
permissions for the deployment and use of the telemetry use case::

  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "cloudformation:*",
          "cloudwatch:*",
          "iot:*",
          "lambda:*",
          "logs:*",
          "s3:*",
          "greengrass:*",
          "sns:*",
          "iotsitewise:*",
          "iam:*",
          "sso:*",
          "sso-directory:*",
          "serverlessrepo:*"
        ],
        "Resource": "*"
      }
    ]
  }

AWS IAM documentation:
https://docs.aws.amazon.com/IAM/latest/UserGuide/getting-started_create-delegated-user.html

Supported Regions
-----------------

- ``Oregon``: ``us-west-2``
- ``Ireland``: ``eu-west-1``

Select in the AWS Console the region you desired from the list of supported regions.

Deployment of the Telemetry Stack in AWS
----------------------------------------

1. Go to the AWS Serverless Application Repository (SAR) console: https://console.aws.amazon.com/serverlessrepo/
2. Go to ``Available applications`` tab; then to ``Public applications`` and
   search for ``goldvip``.
3. Check ``Show apps that create custom IAM roles or resource policies``
   to see the application.
4. Click on ``nxp-goldvip-telemetry``. You can modify the application parameters.
   ``TelemetryTopic`` should be unique. ``CoreThingName`` must be unique,
   however if the default value is used the stack name will be attached
   to the core thing name to ensure that it is unique.
5. Check ``I acknowledge that this app creates custom IAM roles.``
6. Click ``Deploy``. The deployment will take a few minutes. You will be
   redirected to another page. The name of the stack is on the top of the page,
   starting with ``serverlessrepo-``, if you changed the application name
   you will need this name in the next step.
   You can go to the ``Deployments`` tab and
   see the status of the deployment. Wait for the status to change from
   ``Create in progress`` to ``Create complete``.
   **Note**: you may need to refresh the page to see the status change.

This AWS CloudFormation stack creates on your account:

- A AWS IoT Greengrass V2 telemetry component, this is a python function which runs on v2xdomu and sends data to AWS IoT Core.
  The provisioning script described in chapter :ref:`connecting-the-board-to-aws` creates a AWS IoT Greengrass V2
  continuous deployment which will run the telemetry component on your board.
- A AWS IoT SiteWise Portal with multiple Dashboards; after the board is connected to AWS a live visual representation
  of the telemetry data received via the AWS IoT Greengrass V2 component is displayed in these.

SJA1110 Telemetry Setup
-----------------------

Steps needed to enable SJA1110 telemetry:

1. Connect the SJA1110 to the internet using the P4 ethernet port
   on the board (See Appendix A). The SJA1110 application and v2xdomu will need
   to be connected to the same local network.
2. Connect the GMAC0 port to the same network as the SJA1110.
3. Make sure that SW12 is set to ON-ON position. If not, set it to ON-ON and reboot the board.
4. Run the provisioning script (described in chapter :ref:`connecting-the-board-to-aws`)
   with the ``--setup-sja`` option.

**Notes**:
 - You can connect the GMAC0 port to P2A or P2B to access the internet through the SJA1110 switch,
   but if this type of connection is used, the SJA fast path cannot be used any longer.
 - Setting SW12 to ON-OFF will prevent the SJA1110 application to be loaded, and the
   default SJA1110 firmware will run instead.
 - To restart the SJA1110 telemetry after a reboot rerun the provisioning script
   with the ``--setup-sja`` option, as described in chapter :ref:`config-telemetry-after-reboot`.

Chapter :ref:`sja1110-telemetry-application` contains more details about the SJA1110 application.

.. _connecting-the-board-to-aws:

Connecting the board to AWS
---------------------------

1. Log into the v2xdomu virtual machine using the command: ``xl console v2xdomu``

2. Configure environment variables for AWS IoT Greengrass provisioning script:

  From the v2xdomu console, set the AWS credentials as environment variables::

     $ export AWS_ACCESS_KEY_ID=<access key id>
     $ export AWS_SECRET_ACCESS_KEY=<secret access key>

  One way of obtaining your AWS credentials is the following:

   From the AWS SSO console select your account and retrieve the environment variables
   by clicking on ``Command line or programmatic access``. From section ``macOS and Linux``
   copy the variables and paste them on your board. Use Option 1: set the AWS
   credentials as environment variables.

  Please check the AWS documentation for additional information: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html

  **Notes**:
    - IAM credentials should never be used on a device in production scenario.
    - These variables are temporary and are erased at reboot.

3. Run the AWS IoT Greengrass provisioning script on your board:

   ``$ python3 ~/cloud-gw/greengrass_provision.py --stack-name <stack-name> --region-name <region-name> --setup-sja``

   Where ``<stack-name>`` is the name of the deployed stack. If you did not
   change the application name you do not need to specify this parameter.
   In ``<region-name>`` put the region you have selected from the supported ones:
   ``us-west-2`` or ``eu-west-1``.
   ``--setup-sja`` starts the sja provisioning script.

   This will setup the network interface, start the AWS IoT Greengrass V2 Nucleus,
   and create a AWS IoT Greengrass V2 continuous deployment, which will run the telemetry
   component created by the Telemetry Stack.

   **Note**: the provisioning script will try to setup the internet connection using the
   ``eth0`` network interface by default.

   To get more details about the script parameters use:

   ``$ python3 ~/cloud-gw/greengrass_provision.py -h``

The board is now connected to your AWS account and it will begin to send
telemetry data.

In some cases, DHCP client is running for each of the PFE interfaces (PFE0 and PFE2),
hence 2.5 Mbps spikes can be observed in the AWS IoT SiteWise dashboard. To close the DHCP
client, it is necessary to run the command ``killall udhcpc``  in the Dom0 console. This
will close the DHCP client and the spikes will no longer be observed in the dashboard.

**Note**: The AWS IoT Greengrass V2 Nucleus does not start automatically after a reboot. The network configuration
and time are not persistent between reboots. Please check :ref:`config-telemetry-after-reboot`
for further information.

**Note**: Rerunning the AWS IoT Greengrass provisioning script after having already setup the SJA1110
will break the SJA1110 telemetry, you will need to reboot the board and set it up again.

Accessing the AWS IoT SiteWise dashboard
----------------------------------------

1. Go to the AWS IoT SiteWise console: https://console.aws.amazon.com/iotsitewise/
2. Click on ``Portals`` from the list on the left.
3. Click on the name of your portal,
   it starts with ``SitewisePortal_serverlessrepo``.
4. Click on ``Assign administrators``
5. Add your account and any other you want to have access to the
   AWS IoT SiteWise Dashboard.
6. Click ``Assign administrators``.
7. Click on the Portal's Url (or Link).
8. Close the ``Getting started`` pop up window.
9. Click on one of the dashboards to visualize the telemetry.

You will now see the live telemetry data from your board.

Testing the Telemetry Application
---------------------------------

1. Log into the Domain-0 virtual machine using ``CTRL+]``.

2. Simulate core load:

   - Execute a computationally intensive task to generate CPU load:

     ``dd if=/dev/zero of=/dev/null &``

     This process will be assigned to one of the available cores and will run in the background. An increase
     of 25% on the core load shall be observed in the AWS console, per each of the started processes.

   - Kill all cpu loading processes:

     ``killall dd``

Deleting the Telemetry Application
----------------------------------

1. Go to AWS Cloudformation: https://console.aws.amazon.com/cloudformation/
2. Select your stack and delete it.

.. _config-telemetry-after-reboot:

Configure AWS IoT Greengrass after reboot
-----------------------------------------

The AWS IoT Greengrass V2 Nucleus does not start automatically between reboots. The network configuration
is not persistent between reboots, so it must be recreated for internet connection. To restart
the AWS IoT Greengrass V2 Nucleus and configure the network:

- Log into the v2xdomu virtual machine using the command: ``xl console v2xdomu``.

- The provision script can be used again to configure the network interface that will be used by
  AWS IoT Greengrass:

  ``$ python3 ~/cloud-gw/greengrass_provision.py --no-deploy --netif <net-dev> --setup-sja``

  Where ``<net-dev>`` is the network interface that shall be configured.
  When the flag ``--no-deploy`` is set, the script will not create a AWS IoT Greengrass deployment,
  it will just start the AWS IoT Greengrass V2 Nucleus. Adding the ``--setup-sja`` parameter will
  start the provisioning of the SJA1110 telemetry application.

- Alternatively, other commands could be used:

  Acquire an IP address, by running the DHCP client:

    ``$ udhcpc -i <net-dev>``

  Synchronise date and time (restart ntpd):

    ``$ killall ntpd && ntpd -gq``

  Restart the AWS IoT Greengrass V2 Nucleus:

    ``$ /greengrass/v2/alts/current/distro/bin/loader &``
