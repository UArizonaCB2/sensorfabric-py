"""
Author : Shravan Aras.
Email : shravanaras@arizona.edu
Date : 09/18/2023
Organization : University of Arizona

This package is part of the SensorFabric project.

Description :
A set of utilities methods for authenticating and communicating with MDH.
Check out our good friends at MDH - https://developer.mydatahelps.org/api/api_basics.html
"""

import sensorfabric.endpoints as ep
from datetime import datetime, timedelta
from uuid import uuid4
import jwt
import requests

class MDH:
    """
    Gateway into the wonderful world of MyDataHelps API's.
    This class helps maintain the states such as tokens and expiration timers.
    It also contains convinient wrappers around methods that can be used to access several different sensor
    related API functionality.
    """
    def __init__(self, account_secret : str,
                 account_name : str,
                 project_id : str):
        self.token = None
        self.tokenexp = None
        self.account_secret = account_secret
        self.account_name = account_name
        self.project_id = project_id

    def genServiceToken(self, scope='api', ttl=1) -> str :
        """
        getServiceToken(...) used MDH account service secret and account name to generate a service token.
        This token that then be used to make further requests to various MDH endpoints.

        Parameters
        ----------
        1. scope(default:api): Scope for which the service token will be used.
        2. ttl(default:1): Time To Live value for the token. Default is 1 hour.

        Returns
        --------
        Returns MDH account service token. Returns None in case of a failure.
        """

        # Set the expiration for this token.
        self.tokenexp = datetime.now() + timedelta(hours=ttl)
        payload = {
            'iss' : self.account_name,
            'sub' : self.account_name,
            'aud' : ep.MDH_TOKEN_URL,
            'exp' : self.tokenexp.timestamp(),
            'jti' : str(uuid4())
        }

        signed_assertion = jwt.encode(
            payload=payload,
            key=self.account_secret,
            algorithm='RS256'
        )

        # Create the token payload.
        token_payload = {
            'scope' : 'api',
            'grant_type' : 'client_credentials',
            'client_assertion_type' : 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer',
            'client_assertion' : signed_assertion
        }

        # Send this out to the endpoint.
        response = requests.post(url=ep.MDH_TOKEN_URL, data=token_payload)
        response.raise_for_status()  # Raise an exception if something went wrong.

        response = response.json()
        if 'access_token' in response:
            self.token = response['access_token']
            return response['access_token']

        return None

    def isTokenAlive(self) -> bool:
        """
        Method which checks if the current token is alive.

        Returns
        -------
        True if the token is still valid and false if it has expired (or about considering the default 5 minute buffer.)
        """

        if self.token is None or self.tokenexp is None:
            return False

        # A buffer time, which accounts for network delay if a request is made after this check.
        delay = 5 # in minutes
        if datetime.now() < (self.tokenexp - timedelta(minutes=delay)):
            return True

        return False

    def makeGetRequests(self, endpoint : str, params=None) -> dict[str, str]:
        """
        Helper method to make GET API requests to MDH.
        """

        if not self.isTokenAlive():
            self.genServiceToken()

        headers = {
            'Authorization' : 'Bearer '+self.token,
            'Accept' : 'application/json',
            'Content-Type' : 'application/json; charset=utf-8'
        }

        response = requests.get(url=endpoint, headers=headers)
        response.raise_for_status()

        return response.json()


    def getExplorerCreds(self, projectCode) -> dict[str, str]:
        """
        Method which returns MDH data explorer credentials.

        Parameters
        ----------
        1. projectCode : RK.[organization id].[Project Name]
        """

        if not self.isTokenAlive():
            self.genServiceToken()

        headers = {
            'Authorization' : 'Bearer '+self.token,
            'ProjectCode' : projectCode,
            'Accept' : 'application/json',
            'Content-Type' : 'application/json; charset=utf-8'
        }

        response = requests.post(url=ep.MDH_EXPLORER_URL, headers=headers)
        response.raise_for_status()

        return response.json()

    def getExports(self):
        """
        Method which gets all the export meta-data for a project.
        """

        return self.makeGetRequests(ep.MDH_BASE+ep.MDH_EXPORT_DETAILS.format(projectID=self.project_id))
