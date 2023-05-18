#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
A custom function that creates a custom CloudFormation resource.
Implements the 'create' and 'delete' events.
When create is invoked it generates a certificate for the sja thing,
one for the greengrass thing, and packs them in a tar archive and stores it in a S3 bucket.
When delete is invoked it empties the bucket and deletes the certificate from the account.

Copyright 2021-2023 NXP
"""

import json
import tempfile
import tarfile
import urllib.request

import boto3
import cfnresponse

from cfn_utils import Utils, LOGGER


class CertificateHandler:
    """
    Handles the create and delete events for the certificates.
    """

    CA_CERT_URL = "https://www.amazontrust.com/repository/AmazonRootCA1.pem"

    DEVICE_CERTIFICATE = "Device_Certificate.tar.gz"

    CA_CERT = "root.ca.pem"
    CERT_PEM = "certificate.pem"
    CERT_PRIVATE_KEY = "certificate.private.key"
    CERT_PUBLIC_KEY = "certificate.public.key"

    IOT_CLIENT = boto3.client('iot')
    S3_CLIENT = boto3.client('s3')

    @staticmethod
    def __write_to_archive(file_content, archive, filename, path='certs'):
        """
        :param file_content: Content of the file to be added to the archive
        :param archive: The archive.
        :param filename: Name of the file to be added to the archive.
        :param path: Directory path for the certificates.
        """
        with tempfile.NamedTemporaryFile() as file:
            file.write(str.encode(file_content))
            file.seek(0)
            archive.add(file.name, arcname=f'{path}/{filename}')

    @staticmethod
    def create(event, response_data, archive_name, things):
        """
        Creates a certificate and associates it to a thing and a policy.
        :param event: The MQTT message in json format.
        :param response_data: Dictionary of resource ids to be returned.
        :param archive_name: Name of the archive in which the certificates will be stored.
        :param things: Name of the things to attach to this certificate.
        """
        LOGGER.info("Creating certificate for things %s", things)

        response = CertificateHandler.IOT_CLIENT.create_keys_and_certificate(setAsActive=True)

        response_data['certificateArn'] = response.get('certificateArn')
        response_data['certificateId'] = response.get('certificateId')

        # pylint: disable=consider-using-with
        certificates = {
            CertificateHandler.CERT_PEM: response.get('certificatePem'),
            CertificateHandler.CERT_PUBLIC_KEY: response.get('keyPair').get('PublicKey'),
            CertificateHandler.CERT_PRIVATE_KEY: response.get('keyPair').get('PrivateKey'),
            CertificateHandler.CA_CERT: urllib.request.urlopen(
                CertificateHandler.CA_CERT_URL).read().decode('utf-8')
        }

        # Attach thing
        for thing in things:
            CertificateHandler.IOT_CLIENT.attach_thing_principal(
                thingName=thing,
                principal=response.get('certificateArn')
            )

        # Attach policy
        CertificateHandler.IOT_CLIENT.attach_principal_policy(
            policyName=event['ResourceProperties']['PolicyName'],
            principal=response.get('certificateArn')
        )

        with tarfile.open(f'/tmp/{archive_name}', 'w:gz') as archive:
            for key, value in certificates.items():
                CertificateHandler.__write_to_archive(
                    value, archive, key)

        CertificateHandler.S3_CLIENT = boto3.client('s3')
        CertificateHandler.S3_CLIENT.upload_file(
            f'/tmp/{archive_name}',
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
        core_thing_name = event['ResourceProperties']['GGv2CoreName']
        policy_name = event['ResourceProperties']['PolicyName']

        LOGGER.info("Initiated certificate deletion")

        Utils.set_cloudwatch_retention(
            event['ResourceProperties']['StackName'],
            event['ResourceProperties']['Region'])

        CertificateHandler.S3_CLIENT.delete_objects(
            Bucket=bucket_name,
            Delete={
                'Objects': [
                    {'Key': cert} for cert in [
                        CertificateHandler.DEVICE_CERTIFICATE]
                ]
            }
        )

        CertificateHandler.S3_CLIENT.delete_bucket(Bucket=bucket_name)

        # Detach all certificates from the greengrass thing.
        certificates = CertificateHandler.IOT_CLIENT.list_thing_principals(
            thingName=core_thing_name
        )['principals']
        for certificate in certificates:
            CertificateHandler.IOT_CLIENT.detach_thing_principal(
                thingName=core_thing_name,
                principal=certificate
            )

        certificate_arn = event['PhysicalResourceId']

        # Detach all of the things from the certificate
        things = CertificateHandler.IOT_CLIENT.list_principal_things(
            principal=certificate_arn
        )['things']
        for thing in things:
            CertificateHandler.IOT_CLIENT.detach_thing_principal(
                thingName=thing,
                principal=certificate_arn
            )

        certificates = CertificateHandler.IOT_CLIENT.list_targets_for_policy(
            policyName=policy_name
        )['targets']
        # Detach all of the certificates from the policy
        for certificate in certificates:
            CertificateHandler.IOT_CLIENT.detach_principal_policy(
                policyName=policy_name,
                principal=certificate
            )

        certificate_id = certificate_arn.split('/')[1]
        # Delete the certificate.
        CertificateHandler.IOT_CLIENT.update_certificate(
            certificateId=certificate_id, newStatus='INACTIVE')
        CertificateHandler.IOT_CLIENT.delete_certificate(certificateId=certificate_id)


def lambda_handler(event, context):
    """
    Handler function for the custom resource function.
    :param event: The MQTT message in json format.
    :param context: A Lambda context object, it provides information.
    """
    LOGGER.info('Certificate custom function handler got event %s', json.dumps(event))

    try:
        response_data = {}

        if event['RequestType'] == 'Create':
            CertificateHandler.create(
                event,
                response_data,
                CertificateHandler.DEVICE_CERTIFICATE,
                [event['ResourceProperties']['SjaThingName']])
            cfnresponse.send(
                event, context, cfnresponse.SUCCESS, response_data,
                physical_resource_id=response_data['certificateArn'])
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

    # pylint: disable=broad-except
    except Exception as err:
        LOGGER.error("Certificate custom function handler error: %s", err)
        response_data = {"Data": str(err)}
        cfnresponse.send(event, context, cfnresponse.FAILED, response_data)
