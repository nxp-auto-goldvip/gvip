#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
A custom function that creates a custom CloudFormation resource.
Implements the 'create' and 'delete' events.
When create is invoked it generates certificates for Greengrass, a config file,
then packs them in a tar archive and stores it in a S3 bucket.
When delete is invoked it empties the bucket and deletes the certificate from
the account.

Copyright 2021 NXP
"""

import json
import logging
import tempfile
import tarfile
import urllib.request

import boto3
import cfnresponse

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)


class CertificateHandler:
    """
    Handles the create and delete events for the certificate.
    """

    CA_CERT_URL = "https://www.amazontrust.com/repository/AmazonRootCA1.pem"

    GOLDVIP_SETUP_ARCHIVE = "GoldVIP_setup.tar.gz"
    SJA_CERTIFICATE = "Sja_Certificate.tar.gz"

    CA_CERT = "root.ca.pem"
    CERT_PEM = "certificate.pem"
    CERT_PRIVATE_KEY = "certificate.private.key"
    CERT_PUBLIC_KEY = "certificate.public.key"

    IOT_CLIENT = boto3.client('iot')
    S3_CLIENT = boto3.client('s3')

    @staticmethod
    def _write_to_archive(file_content, archive, filename, path='certs'):
        """
        :param file_content: Content of the file to be added to the archive
        :param archive: The archive.
        :param filename: Name of the file to be added to the archive.
        """
        with tempfile.NamedTemporaryFile() as file:
            file.write(str.encode(file_content))
            file.seek(0)
            archive.add(file.name, arcname='{1}/{0}'.format(filename, path))

    @staticmethod
    def create(event, response_data, archive_name, thing, prefix=""):
        """
        Creates the certificate and associates it to a Greengrass Group.
        :param event: The MQTT message in json format.
        :param response_data: Dictionary of resource ids to be returned.
        :param archive_name: Name of the archive in which the certificates will be stored.
        :param thing: Name of the thing for which the certificate is created.
        :param prefix: Prefix to distinguish response data keys.
        """
        LOGGER.info("Creating certificate for thing %s", thing)

        response = CertificateHandler.IOT_CLIENT.create_keys_and_certificate(setAsActive=True)

        response_data[prefix + 'certificateArn'] = response.get('certificateArn')
        response_data[prefix + 'certificateId'] = response.get('certificateId')

        # pylint: disable=consider-using-with
        certificates = {
            CertificateHandler.CERT_PEM: response.get('certificatePem'),
            CertificateHandler.CERT_PUBLIC_KEY: response.get('keyPair').get('PublicKey'),
            CertificateHandler.CERT_PRIVATE_KEY: response.get('keyPair').get('PrivateKey'),
            CertificateHandler.CA_CERT: urllib.request.urlopen(
                CertificateHandler.CA_CERT_URL).read().decode('utf-8')
        }

        # Attach thing
        CertificateHandler.IOT_CLIENT.attach_thing_principal(
            thingName=thing,
            principal=response.get('certificateArn')
        )

        # Attach policy
        CertificateHandler.IOT_CLIENT.attach_principal_policy(
            policyName=event['ResourceProperties']['PolicyName'],
            principal=response.get('certificateArn')
        )

        with tarfile.open(
                '/tmp/{0}'.format(archive_name), 'w:gz') as archive:

            for key, value in certificates.items():
                CertificateHandler._write_to_archive(
                    value, archive, key)

            with open("./config-template.json", 'r', encoding="utf-8") as template_file:
                config = template_file.read()

                replacements = [
                    ('CERT_PEM', CertificateHandler.CERT_PEM),
                    ('CERT_PRIVATE_KEY', CertificateHandler.CERT_PRIVATE_KEY),
                    ('THING_ARN', event['ResourceProperties']['ThingArn']),
                    ('IOT_HOST', CertificateHandler.IOT_CLIENT.describe_endpoint(
                        endpointType='iot:Data-ATS')['endpointAddress']),
                    ('REGION', event['ResourceProperties']['Region']),
                    ('CA_CERT', CertificateHandler.CA_CERT)
                ]

                for first, second in replacements:
                    config = config.replace(first, second)

                CertificateHandler._write_to_archive(
                    config, archive, 'config.json', path="config")

        CertificateHandler.S3_CLIENT = boto3.client('s3')
        CertificateHandler.S3_CLIENT.upload_file(
            '/tmp/{0}'.format(archive_name),
            event['ResourceProperties']['BucketName'],
            archive_name)

        LOGGER.info("Certificate Created.")

        return response_data

    @staticmethod
    def delete(event):
        """
        Empties and deletes the certificate bucket.
        Detaches Greengrass thing and policy from certificate.
        Then deactivates and deletes the certificate.
        :param event: The MQTT message in json format.
        """
        bucket_name = event['ResourceProperties']['BucketName']
        core_thing_name = event['ResourceProperties']['GGCoreName']
        sja_thing_name = event['ResourceProperties']['SjaThingName']
        policy_name = event['ResourceProperties']['PolicyName']

        LOGGER.info("Initiated certificate deletion")

        certificates = event['PhysicalResourceId'].split('|')

        CertificateHandler.S3_CLIENT.delete_objects(
            Bucket=bucket_name,
            Delete={
                'Objects': [
                    {'Key': cert} for cert in [
                        CertificateHandler.GOLDVIP_SETUP_ARCHIVE,
                        CertificateHandler.SJA_CERTIFICATE]
                ]
            }
        )

        CertificateHandler.S3_CLIENT.delete_bucket(Bucket=bucket_name)

        # detatch core and policy from certificate
        things = [core_thing_name, sja_thing_name]

        for i, gg_certificate_arn in enumerate(certificates):
            gg_certificate_id = gg_certificate_arn.split('/')[1]

            CertificateHandler.IOT_CLIENT.detach_principal_policy(
                policyName=policy_name,
                principal=gg_certificate_arn
            )
            CertificateHandler.IOT_CLIENT.detach_thing_principal(
                thingName=things[i],
                principal=gg_certificate_arn
            )

            CertificateHandler.IOT_CLIENT.update_certificate(
                certificateId=gg_certificate_id, newStatus='INACTIVE')
            CertificateHandler.IOT_CLIENT.delete_certificate(certificateId=gg_certificate_id)


def lambda_handler(event, context):
    """
    Handler function for the custom resource function.
    :param event: The MQTT message in json format.
    :param context: A Lambda context object, it provides information.
    """
    LOGGER.info('Handler got event %s', json.dumps(event))

    try:
        response_data = {}

        if event['RequestType'] == 'Create':
            CertificateHandler.create(
                event,
                response_data,
                CertificateHandler.GOLDVIP_SETUP_ARCHIVE,
                event['ResourceProperties']['GGCoreName'],
                "gg_")
            CertificateHandler.create(
                event,
                response_data,
                CertificateHandler.SJA_CERTIFICATE,
                event['ResourceProperties']['SjaThingName'],
                "sja_")
            cfnresponse.send(
                event, context, cfnresponse.SUCCESS, response_data,
                physical_resource_id=response_data['gg_certificateArn']\
                    + "|" + response_data['sja_certificateArn'])
        elif event['RequestType'] == 'Update':
            cfnresponse.send(
                event, context, cfnresponse.SUCCESS, response_data)
        elif event['RequestType'] == 'Delete':
            CertificateHandler.delete(event)
            cfnresponse.send(
                event, context, cfnresponse.SUCCESS, response_data)
        else:
            LOGGER.info('Unexpected RequestType!')
            cfnresponse.send(
                event, context, cfnresponse.SUCCESS, response_data)
    except Exception as err:  # pylint: disable=broad-except
        LOGGER.error(err)
        response_data = {"Data": str(err)}
        cfnresponse.send(event, context, cfnresponse.FAILED, response_data)
