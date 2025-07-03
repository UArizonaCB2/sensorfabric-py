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
import os
from typing import Optional, List, Dict, Any


class MDH:
    """
    Gateway into the wonderful world of MyDataHelps API's.
    This class helps maintain the states such as tokens and expiration timers.
    It also contains convinient wrappers around methods that can be used to access several different sensor
    related API functionality.
    """
    def __init__(self, account_secret : Optional[str] = None,
                 account_name : Optional[str] = None,
                 project_id : Optional[str] = None):
        self.token = None
        self.tokenexp = None
        self.account_secret = os.getenv('MDH_SECRET_KEY', account_secret)
        self.account_name = os.getenv('MDH_ACCOUNT_NAME', account_name)
        self.project_id = os.getenv('MDH_PROJECT_ID', project_id)

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

        response = requests.get(url=endpoint, headers=headers, params=params)
        response.raise_for_status()

        return response.json()

    def makePostRequests(self, endpoint: str, data: dict, params=None) -> dict:
        """
        Helper method to make POST API requests to MDH.
        
        Parameters
        ----------
        endpoint : str
            The API endpoint URL
        data : dict
            JSON data to send in the request body
        params : dict, optional
            Query parameters for the request
            
        Returns
        -------
        dict
            JSON response from the API
        """
        if not self.isTokenAlive():
            self.genServiceToken()

        headers = {
            'Authorization': 'Bearer ' + self.token,
            'Accept': 'application/json',
            'Content-Type': 'application/json; charset=utf-8'
        }

        response = requests.post(url=endpoint, headers=headers, json=data, params=params)
        response.raise_for_status()

        return response.json()

    def getAllParticipants(self, queryParam=None):
        """
        Method which returns all participant information.
        Automatically handles pagination to fetch all participants across multiple pages.
        
        Parameters
        ----------
        queryParam : dict, optional
            Additional query parameters for the API request
            

        Participant Object Structure:
        {
            "accountEmail": "email_address@domain.com",
            "accountMobilePhone": null,
            "customFields": {
                "Coments": "",
                "Contacted": "",
                "DeclinedReason": "",
                "DeliverySite": "",
                "PrenatalCareSite": "",
                "RecruitmentDate": "",
                "WithdrawalDate": "",
                "compensation_choice": "",
                "compensation_initials": "",
                "conception_date": "",
                "cuffSize": "",
                "daily_symptom_count": "",
                "delivery_date": "",
                "ema_enabled": "",
                "ema_evening_close": "",
                "ema_evening_completed": "",
                "ema_evening_time": "",
                "ema_metadata1": "",
                "ema_metadata2": "",
                "ema_metadata3": "",
                "ema_metadata4": "",
                "ema_morning_close": "",
                "ema_morning_completed": "",
                "ema_morning_time": "",
                "ema_random1": "",
                "ema_random2": "",
                "ema_random3": "",
                "ema_random4": "",
                "ema_reminder_time": "",
                "ema_status": "",
                "future_use_initials": "",
                "ga_20_sent": "",
                "ga_28_sent": "",
                "ga_36_sent": "",
                "icf_version_date": "",
                "interview_initials": "",
                "oura": "",
                "postpartum_sent": "",
                "pregnancy_proof": "",
                "sgAvatar": "",
                "total_symptom_count": "",
                "uh_email": "",
                "ultrahuman": "",
                "weekly_survey_active": "",
                "weekly_symptom_count": ""
            },
            "demographics": {
                "email": "email_address@domain.com",
                "firstName": "First Name",
                "lastName": "Last Name",
                "timeZone": "America/Phoenix",
                "unsubscribedFromEmails": "false",
                "unsubscribedFromSms": "false",
                "utcOffset": "-07:00:00"
            },
            "enrolled": true,
            "enrollmentDate": "2025-06-24T17:51:07.651+00:00",
            "excludeFromExport": false,
            "id": "uuid4",
            "insertedDate": "2025-06-24T17:50:20.25+00:00",
            "institutionCode": "",
            "invitationStatus": null,
            "linkIdentifier": "uuid4",
            "participantIdentifier": "AA-0000-0000",
            "viewParticipantRecordLink": null,
            "withdrawDate": null
        }

        Returns
        -------
        dict
            Dictionary containing all participants with the following structure:
            {
                "totalParticipants": int,
                "participants": [list of all participant objects]
            }
        """
        if not self.isTokenAlive():
            self.genServiceToken()

        url = ep.MDH_BASE + ep.MDH_PROJ + 'participants'
        
        # Initialize pagination parameters
        page_number = 0
        page_size = 100  # Use a reasonable page size
        all_participants = []
        total_participants = None
        
        # Build query parameters
        if queryParam is None:
            queryParam = {}
        
        while True:
            # Add pagination parameters to query
            current_params = queryParam.copy()
            current_params['pageNumber'] = page_number
            current_params['pageSize'] = page_size
            
            # Make the API request
            response = self.makeGetRequests(url.format(projectID=self.project_id),
                                          params=current_params)
            
            # Extract participants from current page
            page_participants = response.get('participants', [])
            all_participants.extend(page_participants)
            
            # Set total count on first page
            if total_participants is None:
                total_participants = response.get('totalParticipants', 0)
            
            # Check if we've retrieved all participants
            if len(all_participants) >= total_participants or len(page_participants) == 0:
                break
                
            # Move to next page
            page_number += 1
        
        return {
            'totalParticipants': total_participants,
            'participants': all_participants
        }


    def getExplorerCreds(self) -> dict[str, str]:
        """
        Method which returns MDH data explorer credentials.
        """

        if not self.isTokenAlive():
            self.genServiceToken()

        headers = {
            'Authorization' : self.token,
            'Accept' : 'application/json',
            'Content-Type' : 'application/json; charset=utf-8'
        }

        response = requests.post(url=ep.MDH_EXPLORER_URL.format(projectID=self.project_id), headers=headers)
        response.raise_for_status()

        return response.json()

    def getExports(self, pageNumber, pageSize):
        """Method which gets all the export meta-data for a project."""
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

    def update_participants(self, participants: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Update participants using the MDH Bulk Add/Update API.
        
        This method allows bulk updating of participant custom fields, particularly
        useful for updating sync dates or other metadata.
        
        Parameters
        ----------
        participants : List[Dict[str, Any]]
            List of participant objects with the following structure:
            [
                {
                    "participantIdentifier": "AA-0000-0001",
                    "customFields": {
                        "uh_sync_date": "2023-12-15T10:30:00Z"
                    }
                }
            ]
            
        Returns
        -------
        Dict[str, Any]
            Response from the API with the following structure:
            {
                "success": bool,
                "totalAdded": int,
                "totalUpdated": int,
                "results": [
                    {
                        "participantIdentifier": "AA-0000-0001",
                        "action": "updated",
                        "error": str (if applicable)
                    }
                ],
                "errors": [str] (if any validation errors)
            }
            
        Raises
        ------
        ValueError
            If participants list is empty or contains invalid data
        requests.exceptions.HTTPError
            If the API request fails
            
        Examples
        --------
        >>> participants = [
        ...     {
        ...         "participantIdentifier": "AA-0000-0001",
        ...         "customFields": {"uh_sync_date": "2023-12-15"}
        ...     }
        ... ]
        >>> result = mdh.update_participants(participants)
        >>> print(f"Updated {result['totalUpdated']} participants")
        """
        # Input validation
        if not participants:
            raise ValueError("Participants list cannot be empty")
        
        # Validate each participant has required fields
        validation_errors = []
        for i, participant in enumerate(participants):
            if not isinstance(participant, dict):
                validation_errors.append(f"Participant {i}: Must be a dictionary")
                continue
                
            if "participantIdentifier" not in participant:
                validation_errors.append(f"Participant {i}: Missing 'participantIdentifier' field")
                
            if "customFields" not in participant:
                validation_errors.append(f"Participant {i}: Missing 'customFields' field")
            elif not isinstance(participant["customFields"], dict):
                validation_errors.append(f"Participant {i}: 'customFields' must be a dictionary")
        
        if validation_errors:
            return {
                "success": False,
                "totalAdded": 0,
                "totalUpdated": 0,
                "totalErrors": len(validation_errors),
                "results": [],
                "errors": validation_errors
            }
        
        # Prepare request payload
        request_data = {
            "participants": participants,
            "sendDefaultInvitationNotifications": False
        }
        
        # Prepare query parameters
        query_params = {
            "allowUpdate": "true"
        }
        
        try:
            # Make API request
            url = ep.MDH_BASE + ep.MDH_PROJ + 'participants'
            response = self.makePostRequests(
                url.format(projectID=self.project_id),
                data=request_data,
                params=query_params
            )
            
            # Process response
            total_added = response.get('totalAdded', 0)
            total_updated = response.get('totalUpdated', 0)
            results = response.get('results', [])
            result_details = []
            
            for result in results:
                resObj = result.get('result', {})
                participant_id = resObj.get('participantIdentifier')
                action = result.get('actionTaken')
                
                result_detail = {
                    "participantIdentifier": participant_id,
                    "action": action,
                }
                
                result_details.append(result_detail)
            
            return {
                "success": True,
                "totalAdded": total_added,
                "totalUpdated": total_updated,
                "results": result_details,
                "errors": []
            }
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP error during participant update: {str(e)}"
            if hasattr(e.response, 'json'):
                try:
                    error_details = e.response.json()
                    error_msg += f" - {error_details}"
                except:
                    pass
            
            return {
                "success": False,
                "totalAdded": 0,
                "totalUpdated": 0,
                "results": [],
                "errors": [error_msg]
            }
        
        except Exception as e:
            return {
                "success": False,
                "totalAdded": 0,
                "totalUpdated": 0,
                "results": [],
                "errors": [f"Unexpected error during participant update: {str(e)}"]
            }

