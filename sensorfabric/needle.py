#!/usr/bin/env python3

"""
Author : Shravan Aras.
Email : shravanaras@arizona.edu
Date : 09/18/2023
Organization : University of Arizona

This package is part of the SensorFabric project.

Description :
A needle is what you loose in a haystack.
But a needle is always what builds the fabric.
"""

from sensorfabric.mdh import MDH
from sensorfabric import utils
from sensorfabric.athena import athena
import pandas
import os

supported_methods = ['aws', 'mdh']

DEFAULT_DATA_CATALOG = 'AwsDataCatalog'
DEFAULT_WORKGROUP = 'primary'

class Needle:
    def __init__(self, method=None,
                 aws_configuration=None,
                 mdh_configuration=None,
                 offlineCache=False,
                 profileName=None):
        """
        Creates a new needle (a connector into the dataset) based on the configuration provided.
        If no arguments are passed then environment variables are used.

        Parameters
        ----------
        1. method : Can be 'aws' to connect directly AWS Athena or 'mdh'
                    to connect to MyDataHelps.
        2. aws_configuration: AWS Athena connection details -
           aws_configuration = {
                                    database : '',
                                    catalog : '',
                                    workgroup : '',
                                    s3_location: ''
                               }
        3. mdh_configuration = {
                                account_secret : '',
                                account_name : '',
                                project_code : '',
                                }
        4. offlineCache : True to cache the results locally. False otherwise.
        """
        self.method = method
        if not(self.method in supported_methods):
            raise Exception('{} method is currently not supported'.format(self.method))

        self.aws_configuration = aws_configuration
        self.mdh_configuration = mdh_configuration
        self.offlineCache = offlineCache
        self.db = None
        self.mdh = None
        # Stores the data explorer credentials for MDH.
        self.mdh_explorer = None

        self.profileName = profileName
        self.aws_configuration = aws_configuration
        self.mdh_configuration = mdh_configuration
        self.mdh_org_id = None

        # Set the configuration from environment variables if they have
        # not been passed.
        if self.method == 'aws' and self.aws_configuration is None:
            self.aws_configuration = {
                'database' : os.getenv('SF_DATABASE'),
                'catalog' : os.getenv('SF_CATALOG', DEFAULT_DATA_CATALOG),
                'workgroup' : os.getenv('SF_WORKGROUP', DEFAULT_WORKGROUP),
                's3_location' : os.getenv('SF_S3LOC', None),
            }

        if self.method == 'mdh' and self.mdh_configuration is None:
            self.mdh_configuration = {
                'account_secret' : os.getenv('MDH_SECRET_KEY', None),
                'account_name' : os.getenv('MDH_ACCOUNT_NAME', None),
                'project_id' : os.getenv('MDH_PROJECT_ID', None),
                'project_name' : os.getenv('MDH_PROJECT_NAME', None),
            }

        # Create the base athena connector depending on the configuration
        # given.
        if self.method == 'aws':
            self._configureAWS()
        elif self.method == 'mdh':
            self._configureMDH()
        else:
            raise Exception('Unsupported method. Must be either "aws" or "mdh"')

        # We are all set now. Let us go ahead and create the database object.
        if self.method == 'mdh':
            database = 'mdh_export_database_rk_{}_{}_prod'.format(self.mdh_org_id.lower(), self.mdh_configuration['project_name'])
            workgroup = 'mdh_export_database_external_prod'
            s3_location = 's3://pep-mdh-export-database-prod/execution/rk_{}_{}'.format(self.mdh_org_id.lower(), self.mdh_configuration['project_name'].lower())

            # Create the AWS configuration.
            aws_configuration = {
                'aws_access_key_id': self.mdh_explorer['AccessKeyId'],
                'aws_secret_access_key': self.mdh_explorer['SecretAccessKey'],
                'aws_session_token': self.mdh_explorer['SessionToken'],
                'aws_region': 'us-east-1',
            }
            self.db = athena(database=database,
                             workgroup=workgroup,
                             offlineCache=offlineCache,
                             s3_location=s3_location,
                             aws_config=aws_configuration)

        elif self.method == 'aws':
           self.db = athena(database=self.aws_configuration['database'],
                            catalog=self.aws_configuration.get('catalog', 'AwsDataCatalog'),
                            workgroup=self.aws_configuration['workgroup'],
                            offlineCache=offlineCache,
                            profile_name=profileName)

    def _configureAWS(self):
        """
        Depreciated (Breaking change for some of our Cyverse tools)
        """
        pass

    def _configureMDH(self):
        """
        Internal method that configures sensorfabric to use MDH as the
        backend.
        """

        # Do a sanity check to make sure that none of the parameters we got are not null.
        assert(self.mdh_configuration['account_secret'] is not None)
        assert(self.mdh_configuration['account_name'] is not None)
        assert(self.mdh_configuration['project_id'] is not None)

        self.mdh = MDH(self.mdh_configuration['account_secret'],
                       self.mdh_configuration['account_name'],
                       self.mdh_configuration['project_id'])
        # Generate the servicetoken using the service secret.
        token = self.mdh.genServiceToken()

        # Extract the organization id from the account name.
        acc_name = self.mdh_configuration['account_name']
        buff = acc_name.split('.')
        if len(buff) < 3:
            raise Exception('Invalid MDH account name format')
        self.mdh_org_id = buff[1]

        # Check if the AWS credentials are already set and valid,
        # if not add / update them.
        self._testAndRequestNew()

    def _testAndRequestNew(self):
        """
        Internal method which tests to see if the AWS credentials are valid.
        If they are not then new ones are created.
        Renewed credentials are stored inside in-memory object.
        """
        if self.method == 'mdh' and (self.mdh_explorer is None or (not utils.isMDHAWSCredValid(self.mdh_explorer['Expiration']))):
            dataExplorer = self.mdh.getExplorerCreds()
            # Store these internally.
            self.mdh_explorer = dataExplorer

    def execQuery(self, queryString:str, queryParams=[],
                  defaultTimeout=60) -> pandas.DataFrame:
        """
        Description
        -----------
        This method is blocking. It executes the query and returns the result as a pandas
        data frame.

        Parameters
        ----------
        1. queryString : SQL query to execute.
        2. queryParam : A list of query parameters.
        4. defaultTimeout(unimplemented) : Query execution timeout. Default is 60 seconds.

        Returns
        -------
        Returns a pandas dataframe. If the SQL query returns an empty dataset,
        this will return an empty pandas frame.
        """
        self._testAndRequestNew()
        return self.db.execQuery(queryString, queryParams, defaultTimeout)
