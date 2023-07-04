#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
A custom function that creates a custom CloudFormation resource and implements the 'create'
and 'delete' events. When create is invoked, it generates a certificate for each client thing,
and packs them in separate tar archives that are stored in an S3 bucket.
When delete is invoked, it empties the S3 bucket, it detaches the policies from every certificate
used for Greengrass Core thing, then it deletes the certificate used for client devices.

Copyright 2021-2023 NXP
"""

import json
import tempfile
import tarfile
import urllib.request

from string import Template

import boto3
import cfnresponse

from cfn_utils import Utils, LOGGER


class CertificateHandler:
    """
    Handles the create and delete events for the certificates.
    """

    CA_CERT_URL = "https://www.amazontrust.com/repository/AmazonRootCA1.pem"

    CA_CERT = "root.ca.pem"
    CERT_PEM = "certificate.pem"
    CERT_PRIVATE_KEY = "certificate.private.key"
    CERT_PUBLIC_KEY = "certificate.public.key"

    CERTS_ARCHIVE_TEMPLATE = Template("${thing}_certificates.tar.gz")

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
    def create(event):
        """
        Creates a set of certificates and associates them to a specific thing and a common policy.
        :param event: The MQTT message in JSON format.
        """
        things = [event['ResourceProperties'][prop]
                  for prop in event['ResourceProperties'] if "ThingName" in prop]
        response_data = {}

        for thing in things:
            LOGGER.info("Creating certificate for thing %s.", thing)

            archive_name = CertificateHandler.CERTS_ARCHIVE_TEMPLATE.substitute(thing=thing)
            response = CertificateHandler.IOT_CLIENT.create_keys_and_certificate(setAsActive=True)

            response_data[thing] = {}
            response_data[thing]['certificateArn'] = response.get('certificateArn')
            response_data[thing]['certificateId'] = response.get('certificateId')

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

            with tarfile.open(f'/tmp/{archive_name}', 'w:gz') as archive:
                for key, value in certificates.items():
                    CertificateHandler.__write_to_archive(
                        value, archive, key)

            CertificateHandler.S3_CLIENT = boto3.client('s3')
            CertificateHandler.S3_CLIENT.upload_file(
                f'/tmp/{archive_name}',
                event['ResourceProperties']['BucketName'],
                archive_name)

            LOGGER.info("Certificate %s created for thing %s.", response_data[thing], thing)

        return response_data

    @staticmethod
    def delete(event):
        """
        Remove the certificates and other artifacts related to them:
         - empties and deletes the certificate bucket
         - detaches the Greengrass Core thing and policy from its certificates
         - deactivates and deletes the certificates used by client devices
        :param event: The MQTT message in JSON format.
        """
        bucket_name = event['ResourceProperties']['BucketName']
        core_thing_name = event['ResourceProperties']['GGv2CoreName']
        policy_name = event['ResourceProperties']['PolicyName']
        things = [event['ResourceProperties'][prop]
                  for prop in event['ResourceProperties'] if "ThingName" in prop]

        LOGGER.info("Initiated certificate deletion")

        Utils.set_cloudwatch_retention(
            event['ResourceProperties']['StackName'],
            event['ResourceProperties']['Region'])

        CertificateHandler.S3_CLIENT.delete_objects(
            Bucket=bucket_name,
            Delete={
                'Objects': [
                    {'Key': CertificateHandler.CERTS_ARCHIVE_TEMPLATE.substitute(thing=thing)}
                     for thing in things
                ]
            }
        )

        CertificateHandler.S3_CLIENT.delete_bucket(Bucket=bucket_name)

        # Detach all the certificates from the Greengrass Core thing.
        certificates = CertificateHandler.IOT_CLIENT.list_thing_principals(
            thingName=core_thing_name
        )['principals']
        for certificate in certificates:
            CertificateHandler.IOT_CLIENT.detach_thing_principal(
                thingName=core_thing_name,
                principal=certificate
            )

        # Detach all of the certificates from the common policy.
        certificates = CertificateHandler.IOT_CLIENT.list_targets_for_policy(
            policyName=policy_name
        )['targets']

        for certificate in certificates:
            CertificateHandler.IOT_CLIENT.detach_principal_policy(
                policyName=policy_name,
                principal=certificate
            )

        # Detach all of the things from the certificates associated with client things.
        for certificate_arn in Utils.decode_ids(event['PhysicalResourceId']).values():
            things = CertificateHandler.IOT_CLIENT.list_principal_things(
                principal=certificate_arn
            )['things']
            for thing in things:
                CertificateHandler.IOT_CLIENT.detach_thing_principal(
                    thingName=thing,
                    principal=certificate_arn
                )

            certificate_id = certificate_arn.split('/')[1]
            # Delete the certificate.
            CertificateHandler.IOT_CLIENT.update_certificate(
                certificateId=certificate_id, newStatus='INACTIVE')
            CertificateHandler.IOT_CLIENT.delete_certificate(certificateId=certificate_id)


def lambda_handler(event, context):
    """
    Handler function for the custom resource function.
    :param event: The MQTT message in JSON format.
    :param context: A Lambda context object, it provides information.
    """
    LOGGER.info('Certificate custom function handler got event %s', json.dumps(event))

    try:
        response_data = {}

        if event['RequestType'] == 'Create':
            response_data = CertificateHandler.create(event)
            cfnresponse.send(
                event, context, cfnresponse.SUCCESS, response_data,
                physical_resource_id=Utils.encode_ids({thing: thing_data['certificateArn']
                                                       for thing, thing_data in response_data.items()}))
        elif event['RequestType'] == 'Update':
            cfnresponse.send(
                event, context, cfnresponse.SUCCESS, response_data)
        elif event['RequestType'] == 'Delete':
            response_data = CertificateHandler.delete(event)
            cfnresponse.send(
                event, context, cfnresponse.SUCCESS, response_data)
        else:
            LOGGER.info('Unexpected RequestType!')
            cfnresponse.send(
                event, context, cfnresponse.SUCCESS, response_data)
    # pylint: disable=broad-exception-caught
    except Exception as err:
        LOGGER.error("Certificate custom function handler error: %s", err)
        response_data = {"Data": str(err)}
        cfnresponse.send(event, context, cfnresponse.FAILED, response_data)
