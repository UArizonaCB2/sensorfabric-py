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
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Union, Optional
import pytz

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
        if 'SessionToken' in aws_credentials:
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


def flatten_json_to_columns(json_data: Dict[str, Any], fill: bool = False, separator: str = "_") -> Dict[str, List[Any]]:
    """
    Flatten a JSON structure from row-oriented to column-oriented format.
    
    This function takes a JSON object and converts it to a columnar format where:
    - Scalar values become single-element lists (or repeated if fill=True)
    - Arrays become columns with their values
    - Nested objects get flattened with separator-joined keys
    
    Parameters
    ----------
    json_data : dict
        The input JSON object to flatten
    fill : bool, default False
        If True, scalar values are repeated to match the length of the longest array
        If False, scalar values become single-element lists
    separator : str, default "_"
        Separator used to join nested object keys
        
    Returns
    -------
    dict
        Column-oriented dictionary where each key maps to a list of values
        
    Examples
    --------
    >>> input_data = {
    ...     "device_name": "AppleWatch",
    ...     "data_type": "hr", 
    ...     "values": [{"timestamp": 1000.0, "value": 84}, {"timestamp": 1600.0, "value": 85}]
    ... }
    >>> flatten_json_to_columns(input_data, fill=False)
    {'device_name': ['AppleWatch'], 'data_type': ['hr'], 'values_timestamp': [1000.0, 1600.0], 'values_value': [84, 85]}
    
    >>> flatten_json_to_columns(input_data, fill=True)  
    {'device_name': ['AppleWatch', 'AppleWatch'], 'data_type': ['hr', 'hr'], 'values_timestamp': [1000.0, 1600.0], 'values_value': [84, 85]}
    """
    result = {}
    
    # First pass: flatten all values and identify the maximum length
    max_length = 1
    
    def _flatten_recursive(obj: Any, prefix: str = "") -> Dict[str, List[Any]]:
        """Recursively flatten nested structures."""
        flattened = {}
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_key = f"{prefix}{separator}{key}" if prefix else key
                flattened.update(_flatten_recursive(value, new_key))
        elif isinstance(obj, list):
            if not obj:
                # Empty list
                flattened[prefix] = []
            elif all(isinstance(item, dict) for item in obj):
                # List of dictionaries - flatten each dict and combine
                all_keys = set()
                for item in obj:
                    all_keys.update(item.keys())
                
                for key in all_keys:
                    new_key = f"{prefix}{separator}{key}" if prefix else key
                    values = []
                    for item in obj:
                        values.append(item.get(key))
                    flattened[new_key] = values
            else:
                # List of scalars or mixed types
                flattened[prefix] = obj
        else:
            # Scalar value
            flattened[prefix] = [obj]
            
        return flattened
    
    # Flatten the JSON structure
    flattened_data = _flatten_recursive(json_data)
    
    # Find the maximum length among all arrays
    if fill:
        for values in flattened_data.values():
            if isinstance(values, list) and len(values) > max_length:
                max_length = len(values)
    
    # Second pass: apply fill logic if needed
    for key, values in flattened_data.items():
        if fill and isinstance(values, list) and len(values) == 1 and max_length > 1:
            # Replicate single values to match max_length
            result[key] = values * max_length
        else:
            result[key] = values
    
    return result
