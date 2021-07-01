Cloud Edge Gateway
==================

Prerequisites
-------------

 - AWS account with SSO enabled. Follow the steps in this guide to enable SSO:
   https://docs.aws.amazon.com/singlesignon/latest/userguide/getting-started.html
   
   Enabling SSO will grant you access to the SSO console.
   SSO is also required to use the SiteWise Dashboard.
 - S32G board with the GoldVIP image deployed and an internet connection.

   Note: Greengrass uses ports 8883 and 8443. As a
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
          "sso-directory:*"
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

Currently the telemetry application is private. To obtain access to it contact
the GoldVIP team. Please provide your AWS account id in the request.
Contact information can be found in the ``Support`` chapter: :ref:`support`.

Deployment of the Telemetry Stack in AWS
----------------------------------------

1. Go to the AWS SAR console: https://console.aws.amazon.com/serverlessrepo/
2. Go to ``Available applications`` tab; then to ``Private applications``.
   Currently the Application is private. When it will be public anyone
   will be able to search for it in the ``Public applications`` tab by name
   and/or tags.
3. Check ``Show apps that create custom IAM roles or resource policies``
   to see the application.
4. Click on ``nxp-goldvip-telemetry``. You can modify the application parameters.
   Note: if you change ``TelemetryTopic`` you will also need to update it in
   the Telemetry lambda code configuration file.
5. Check ``I acknowledge that this app creates custom IAM roles.``
6. Click ``Deploy``. The deployment will take a few minutes. You will be
   redirected to another page. The name of the stack is on the top of the page,
   starting with ``serverlessrepo-``, if you changed the application name
   you will need this name in the next step.
   You can go to the ``Deployments`` tab and
   see the status of the deployment. Wait for the status to change from 
   ``Create in progress`` to ``Create complete``.
   Note: you may need to refresh the page to see the status change.

This CloudFormation stack creates on your account:
 - A Greengrass Group; this manages the connection between the board
   and the AWS cloud.
 - A SiteWise Portal with a Dashboard; after the board is connected to AWS,
   a live visual representation of the telemetry data received via
   Greengrass is displayed.

.. _connecting-the-board-to-aws:

Connecting the board to AWS
---------------------------

1. Obtain programmatic access to your account on your board.
   From the AWS SSO console select your account and retrieve the environment variables
   by clicking on ``Command line or programmatic access``. From section ``macOS and Linux``
   copy the variables and paste them on your board. Use Option 1: set the AWS
   credentials as environment variables. Note: these are temporary
   and are erased at reboot.
2. Run the greengrass provisioning script on your board:
   
   ``$ python3 ~/cloud-gw/greengrass_provision.py --stack-name <stack-name> --region-name <region-name>``

   Where ``<stack-name>`` is the name of the deployed stack. If you did not
   change the application name you do not need to specify this parameter.
   In ``<region-name>`` put the region you have selected from the supported ones:
   ``us-west-2`` or ``eu-west-1``.

   This will setup the network interface and deploy the Greengrass group created by
   the telemetry application.

   Note: the provisioning script will try to setup the internet connection using the
   ``xenbr0`` network interface by default. To connect Greengrass with the Cloud Services
   using a WiFi network, or to use another network interface, please check
   :ref:`config-greengrass-using-wifi` section for further information.

   To get more details about the script parameters use:

   ``$ python3 ~/cloud-gw/greengrass_provision.py -h``

The board is now connected to your AWS account and it will begin to send
telemetry data.

Note: The deployment of the Greengrass group has to be done only once. The network configuration
is not persistent between reboots. Please check :ref:`config-telemetry-after-reboot`
for further information.

Accessing the SiteWise dashboard
--------------------------------

1. Go to the SiteWise console: https://console.aws.amazon.com/iotsitewise/
2. Click on ``Portals`` from the list on the left.
3. Click on the name of your portal,
   it starts with ``SitewisePortal_serverlessrepo``.
4. Click on ``Assign administrators``
5. Add your account and any other you want to have access to the
   SiteWise Dashboard.
6. Click ``Assign administrators``.
7. Click on the Portal's Url (or Link).
8. Close the ``Getting started`` pop up window.
9. Click on ``Dashboard``.

You will now see the live telemetry data from your board.

Deleting the Telemetry Application
----------------------------------

1. Go to the SiteWise console: https://console.aws.amazon.com/iotsitewise/
2. Click on ``Portals`` from the list on the left.
3. Click on the name of your portal,
   it starts with ``SitewisePortal_serverlessrepo``
4. Remove all administrators and users from the portal.
5. Go to Cloudformation: https://console.aws.amazon.com/cloudformation/
6. Select your stack and delete it.

.. _config-greengrass-using-wifi:

Connecting Greengrass with Cloud Services using WiFi
----------------------------------------------------

Greengrass can connect to the Cloud Services using a WiFi connection established via
a compatible USB WiFi Adapter (any adapter based on a Realtek chipset). Connecting the WiFi
dongle to the USB port using an On The Go (OTG) adapter should result in a new network interface
available for usage. The provisioning script can be used to set up the network interface and
the Greengrass service to use it:

  ``$ python3 ~/cloud-gw/greengrass_provision.py --no-deploy --netif <wlan-dev> --ssid <ssid> --psk <passphrase>``

  Where ``<wlan-dev>`` is the name of the network interface created by the USB WiFi Adapter. To
  connect to a specific WPA/WPA2 protected network, use ``<ssid>`` and ``<passphrase>`` to specify
  the name of the wireless network (SSID), and the password used to connect to the specified
  network respectively. The authentification details to a wireless network will be saved for
  further use. If ``--no-deploy`` option is omitted the Greengrass group will be also deployed
  beside the network setup.

Now the board will use the wireless network to send telemetry data.

Note: The network configuration is not persistent between reboots. Please check
:ref:`config-telemetry-after-reboot` section for further information.

.. _config-telemetry-after-reboot:

Configure Greengrass after reboot
---------------------------------

Greengrass will start after every following board reboot if the telemetry application was
successfully deployed on the board.

The network configuration is not persistent between reboots, so it must be recreated for internet
connection. Some of the options to reconfigure the network are:

- The provision script can be used again to configure the network interface that will be used by
  Greengrass:

  ``$ python3 ~/cloud-gw/greengrass_provision.py --no-deploy --netif <net-dev>``

  Where ``<net-dev>`` is the network interface that will be configured. If ``<net-dev>`` is a
  wireless device, the network configuration saved in previous provisionings will be used to
  establish an internet connection.

- Use other command line commands:

  To connect to the internet using a wireless network interface, ``wpa_supplicant`` service must
  be started first:

    ``$ wpa_supplicant -i<wlan-dev> -Dnl80211,wext -c/etc/wpa_supplicant.conf -B``

  To acquire an IP address, run DHCP client:

    ``$ udhcpc -i <net-dev>``
