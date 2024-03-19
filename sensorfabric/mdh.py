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

        print(headers)

        response = requests.post(url=ep.MDH_EXPLORER_URL, headers=headers)
        print(response.content)
        response.raise_for_status()

        return response.json()

    def getExports(self, pageNumber, pageSize):
        """
        Method which gets all the export meta-data for a project.
        """

        return self.makeGetRequests(ep.MDH_BASE + 
                                    ep.MDH_EXPORT_DETAILS.format(projectID=self.project_id) +
                                    '?pageNumber={pageNumber}&pageSize={pageSize}'.format(pageNumber=pageNumber,
                                                                                          pageSize=pageSize))
    
    def getExportData(self, date_range=None , base_path=None):
        """
        Parameters
        ----------
        1. date_range: [start_date, end_date) --> tuple
        start_date is inclusive and end_date is not inclusive
        This parameter needs a 2 entries. A start date and an end_date.
        Enter them as a string in the format "YYYY-MM-DD"
        The function will download all available exports between these dates.
        
         
        2. base_path: Pass a path where you want to save the exports. If nothing is passed,
        the function saves the exports to the current working directory of the file.
        So as a suggestion, one should always pass a path to save the exports zip file.
        
        Returns 
        -------
        No return for this function. It just saves all the files
        
        REFERENCES: https://developer.mydatahelps.org/api/projects.html#toc-get-exports
        """
        
        # if the token is not alive, get the service token 
        if not self.isTokenAlive():
            self.genServiceToken()
        
        # Defining headers to ocnfigure the API requests
        headers = {
            'Authorization' : 'Bearer '+self.token,
            'Accept' : 'application/json',
            'Content-Type' : 'application/json; charset=utf-8'
        }
        
        # Let's start by gathering a list of all the exports
        pageNumber = 0
        exports_info = self.getExports(pageNumber=pageNumber, pageSize=100)
        exports = exports_info['exports']
        total_exports = exports_info['totalExports']
        
        while len(exports) < total_exports:
            pageNumber += 1
            exports += self.getExports(pageNumber=pageNumber, pageSize=100)['exports']
        
        # Now we check if we need to get the latest export or exports between range of dates
        if date_range is None:
            
            # Get export_id of the latest export
            latest_export_id = exports[0]['id']
            
            # Frame the url using endopoints
            export_data_url = ep.MDH_BASE + ep.MDH_EXPORT_DATA.format(projectID=self.project_id, exportID=latest_export_id)
            
            # Generate name of the file
            start_date = datetime.fromisoformat(exports[0]['dataStartDate']).date()
            day = int(start_date.strftime("%d"))
            file_name = start_date.strftime("%Y") + ' ' + start_date.strftime("%B") + ' ' + str(day) + '-' + str(day+1)
            
            # Ping the url and get its response
            response = requests.get(export_data_url, headers=headers)
            
            if response.status_code == 200:

                # Generate the path in which we have to save the exports
                if base_path:
                    save_path = base_path+  f'/{file_name}.zip'
                else:
                    save_path = f'/{file_name}.zip'
                
                # Save the export data to a file    
                with open(save_path, 'wb') as file:
                    file.write(response.content)
                        
                print(f'Export for "{file_name}" saved successfully.')
                
            else:
                print(f'Error {response.status_code} while downloading {file_name} export')
        
        # Now, if we have the date range
        elif len(date_range) == 2:
            
            # Get dates from date range tuple
            current_date = datetime.strptime(date_range[0], '%Y-%m-%d').date()
            end_date = datetime.strptime(date_range[1], '%Y-%m-%d').date()
            
            # Start a loop to get the exports
            while current_date < end_date:
                
                # Check if we found a match for the current date
                match_found = False
                
                for export in exports:
                    
                    # Check if the current_date matches with the export date
                    if current_date == datetime.fromisoformat(export['dataStartDate']).date():
                        match_found = True
                        
                        # Get export id once we have a match with the date
                        export_id = export['id']
                        
                        # Generate name of the file
                        start_date = datetime.fromisoformat(export['dataStartDate']).date()
                        day = int(start_date.strftime("%d"))
                        file_name = start_date.strftime("%Y") + ' ' + start_date.strftime("%B") + ' ' + str(day) + '-' + str(day+1)
                        
                        # Generate url and get the response after pinging the endpoint
                        export_data_url = ep.MDH_BASE + ep.MDH_EXPORT_DATA.format(projectID=self.project_id, exportID=export_id)
                        response = requests.get(export_data_url, headers=headers)                
                
                        # Checking the response of the request
                        if response.status_code == 200:
                            
                            # Generate path to save the file
                            if base_path:
                                save_path = base_path + f'/{file_name}.zip'
                            else:
                                save_path = f'/{file_name}.zip'
                            
                            # Save the export data to a file
                            with open(save_path, 'wb') as file:
                                file.write(response.content)
                                    
                            print(f'Export for "{file_name}" saved successfully.')
                            
                        else:
                            print(f'Error {response.status_code} while downloading {file_name} export')
                    
                        break
                
                # Check if we found the data in the exports list
                if match_found == False:
                    print(f'No data found for {current_date}')
                
                else:
                    match_found = False
                    
                # Go to the next date
                current_date += timedelta(days=1)
                
        else:
            print('Invalid date range format. Please provide a 2-entry tuple (start_date, end_date).')

