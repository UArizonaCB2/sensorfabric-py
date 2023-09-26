#!/usr/bin/env python3

"""
Author : Shravan Aras.
Email : shravanaras@arizona.edu
Date : 09/18/2023
Organization : University of Arizona

This package is part of the SensorFabric project.

Description :
Just a set of utility files to help out.
"""

import configparser
import pathlib
from datetime import datetime, timedelta

def appendAWSCredentials(profilename : str,
                         aws_credentials,
                         filepath='~/.aws/credentials',
                         forceUpdate=False):
    """
    Method which appends the AWS credentials to end of the credentials file.

    Parameters
    ----------
    1. profilename : Name of the credentials profile.
    2. filepath(default:~/.aws/credentials) : Path to the AWS credentials file.
    """

    # Check to see if we already have the profile in the credentials file.
    path = pathlib.Path(filepath).expanduser()

    # Create this file if it is not present.
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    cp = configparser.ConfigParser()
    # Read all the contents of the file into a configparser.
    with path.open(mode='r') as f:
        if f is None:
            raise FileNotFoundError('Could not open or create file {}'.format(path))

        cp.read_file(f)
        if profilename in cp.sections():
            cp.remove_section(profilename)

        # Append the new profile to the configuration file.
        cp.add_section(profilename)
        cp.set(profilename, 'aws_access_key_id', aws_credentials['AccessKeyId'])
        cp.set(profilename, 'aws_secret_access_key', aws_credentials['SecretAccessKey'])
        cp.set(profilename, 'region', 'us-east-1')
        # The next 2 are optional.
        if 'aws_session_token' in aws_credentials:
            cp.set(profilename, 'aws_session_token', aws_credentials['SessionToken'])
        if 'Expiration' in aws_credentials:
            cp.set(profilename, 'expires', aws_credentials['Expiration'])

    # Write the new profile contents back to the credentials file.
    with path.open('w') as f:
        if f is None:
            raise FileNotFoundError('Could not open or create file {}'.format(path))

        cp.write(f)

def isAWSCredValid(profilename : str,
                   filepath='~/.aws/credentials') -> bool:
    """
    Method which given a profilename checks to see if that profile is still valid or has
    expired. Returns true is the profile is valid, false otherwise.
    """
    profile = readAWSCredentials(profilename, filepath=filepath)
    if profile is None:
        return False

    if not ('expires' in profile):
        return False

    # The profile is already there. Lets go ahead and read the expire
    # date from the section.
    expires = datetime.strptime(profile['expires'], "%Y-%m-%dT%H:%M:%S.%fZ")
    # If we have more than 1 hour left for the key to expire then we are good
    # We can go ahead and use the same.
    if datetime.utcnow() < expires:
        return True

    return False

def readAWSCredentials(profilename : str,
                       filepath='~/.aws/credentials') -> dict[str, str]:
    """
    Method which tries to read from the credentials file.
    If the profile section is not found then we return a null.

    Parameters
    ----------
    1. profilename : Name of the credentials profile.
    2. filepath(default:~/.aws/credentials) : Path to the AWS credentials file

    Returns
    -------
    A dictionary of the AWS profile.
    """

    path = pathlib.Path(filepath).expanduser()

    if not path.exists():
        return None

    cp = configparser.ConfigParser()

    with path.open(mode='r') as f:
        if f is None:
            raise FileNotFoundError('Could not open or create file {}'.format(path))

        cp.read_file(f)

        if profilename in cp.sections():
            profile = cp[profilename]
            return dict(profile)

    return None
