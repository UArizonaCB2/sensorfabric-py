"""
Author : Shravan Aras.
Email : shravanaras@arizona.edu
Date : 11/29/2022
Organization : University of Arizona

This package is part of the SensorFabric project.

Description :
A set of bindings to connect to AWS Athena to help run queries on sensor data.
For security, this library currently only supports read operations on the database.

TODO:
1. Handle pagination for larger queries [done].
2. Implement the default timeout condition to prevent this code from going into an infinite loop.
3. Error handling for failed and cancelled queries.
4. Support query caching internally inside the library, to make use of the same execution ID [done].
5. Allow users to define their own cachine path.
"""

import boto3
import pandas
import hashlib
import os
import re

class athena:
    """
    This class creates bindings to AWS Athena and allows for easy configuration,
    query execution, and query results retrival.
    If running this from outside AWS services, the calling enviroment must have AWS
    credentials correctly set. If using aws cli, use `aws configure`.
    If using a non-default AWS profile, make sure to set the evironment variable
    AWS_EXPORT=[profile] to the correct profile.

    Parameters
    ----------
    1. database : Name of the database to connect to.
    2. catalog : The data catalog to use. Default value is `AwsDataCatalog`.
    3. workgroup : The workgroup inside which all the queries are executed. Default set to `primary`
    4. offlineCache : (true | false) If set to true the results from queries are cached locally and used for future requests
    5. s3_location : Explicitly specificy the s3 location where query results will be stored. If None, then the default
                        location from the workgroup will be used.
    6. profile_name : Explicitly set the profile to use from aws credentials file. If None, then the value from AWS_PROFILE environment
                        variable will be used.

    Note - The workgroup must have query result s3 path set.
    """
    def __init__(self, database:str,
                 catalog='AwsDataCatalog',
                 workgroup='primary',
                 offlineCache=False,
                 s3_location=None,
                 profile_name=None):

        self.database = database
        self.catalog = catalog
        self.workgroup = workgroup
        self.offlineCache = offlineCache
        self.s3_location = s3_location

        session = boto3

        if profile_name is None:
            if not ('AWS_PROFILE' in os.environ):
                raise Exception('Could not find aws profile to use. Either set it in AWS_PROFILE or pass it explicitly using the parameter profile_name')
        else:
            # We need to use the profile name that was provided in this call.
            session = boto3.Session(profile_name=profile_name)

        self.client = session.client('athena')
        self.s3 = session.client('s3')

        self.cacheDir = '.cache'
        self.csvDir = '.csv'

        if self.offlineCache:
            if not os.path.isdir(self.cacheDir):
                os.mkdir(self.cacheDir)

        # Let's go ahead and also make the CSV directory.
        if not os.path.isdir(self.csvDir):
            os.mkdir(self.csvDir)

    """
    Description
    -----------
    Method which starts the query execution and returns the execution ID.

    Parameters
    ----------
    1. queryString : SQL query to execute.
    2. queryParams : A list of query parameters.
    3. cached : True | False (default). If set to True, previous query results
       from within the last 60 mins are returned.

    Returns
    -------
    1. QueryExecutionId : A string with query execution id.
    """
    def startQueryExec(self, queryString:str, queryParams=[],
                       cached=False) -> str:

        # Selectively add the resultconfiguration.
        ResultConfiguration = {}
        if not (self.s3_location is None):
            ResultConfiguration['OutputLocation'] = self.s3_location

        result = self.client.start_query_execution(
            QueryString = queryString,
            QueryExecutionContext = {
                'Database' : self.database,
                'Catalog' : self.catalog
            },
            WorkGroup = self.workgroup,
            ResultConfiguration = ResultConfiguration,
        )

        return result['QueryExecutionId']

    """
    Description
    -----------
    This method returns the results of query execution.

    Parameters
    ----------
    1. executionId : The query executionId returned by startQueryExec()
    2. nextToken : Used for query pagination.
    3. columnNames : Used to keep track of fields returned by a query during pagination.

    Returns
    -------
    1. frame : The data inside a pandas frame. Result can truncated in case of pagination.
    2. nextToken : Set to a stirng if the current output was truncated. Holds the pagination id.
    """
    def queryResults(self, executionId, nextToken=None, columnNames=[]):
        result = None
        if nextToken:
            result = self.client.get_query_results(
                QueryExecutionId = executionId,
                NextToken = nextToken
            )
        else:
            result = self.client.get_query_results(
                QueryExecutionId = executionId,
            )

        if result is None:
            raise Exception('Failed to fetch query results')

        data = result['ResultSet']['Rows']
        if len(data) <= 0:
            return pandas.DataFrame()   # Return an empty dataframe.

        """
        If anyone has to modify the code below, I feel bad. But I will try to explain what is going on.
        Athena returns each row as a {'DataType' : 'Value'} object. Including the 0th row, of column names.
        This data array is store inside ``ResultSet.Rows`.
        Each element in Row is of the form {Data:[{{'DataType': 'Value'}}, {'DataType':'Value'}, {}]}.
        Empty elements mean there is no data for that column. Have fun!
        """

        map = {}
        # The first element in the data list will be the column names.
        # If this is being called from pagination, then we used the columns pased.
        dataStart = 0
        if len(columnNames) <= 0:
            cols = data[0]['Data']
            dataStart = dataStart + 1  # The first row will be the columns in this case.
            for c in cols:
                k = list(c.keys())[0]
                columnNames += [c[k]]

        for c in columnNames:
            map[c] = []

        for i in range(dataStart, len(data)):
            row = data[i]['Data']
            for idx, r in enumerate(row):
                temp = map[columnNames[idx]]
                if len(r.keys()) > 0:
                    k = list(r.keys())[0]
                    temp += [r[k]]
                else:   # There is no data for this column
                    temp += [None]  # pandas will convert this later to NaN

                map[columnNames[idx]] = temp

        # Convert the result into a panda
        frame = pandas.DataFrame(map)
        # Check to see if this response was truncated.
        if 'NextToken' in result:
            nextToken = result['NextToken']
        else:
            nextToken = None

        return (frame, nextToken)

    """
    Description
    -----------
    This method is blocking. It executes the query and returns the result as a pandas
    data frame.

    Parameters
    ----------
    1. queryString : SQL query to execute.
    2. queryParam : A list of query parameters.
    3. cached : True | False (default). If set to True, previous query results are returned.
                offlineCache=True must be passed during object creation. Else this option is
                ignored.
    4. defaultTimeout : Query execution timeout. Default is 60 seconds.
    5. s3Transfer : True | False (default) Enable for large queries.
        When enabled (True) large query results
        are downloaded locally directly via S3 file transfers into .csv/ folder.

    Returns
    -------
    Returns a pandas dataframe. If the SQL query returns an empty dataset,
    this will return an empty pandas frame.
    """
    def execQuery(self, queryString:str, queryParams=[],
                  cached=False, defaultTimeout=60,
                  s3Transfer=False) -> pandas.DataFrame:

        # Check if we have requested cached results and we are setup for serving cache results (offlineCache=True)
        if self.offlineCache and cached:
            filename = self._cacheFileName(queryString)
            path = self.cacheDir+'/'+filename+'.cache'
            if os.path.isfile(path):
                # Load the data from the cache and return the results.
                frame = pandas.read_csv(open(path, 'r'))
                return frame

        # Results were not cached / cache disabled so we go ahead and run this query.
        executionId = self.startQueryExec(queryString,
                                        queryParams,
                                        cached)

        state = None
        # A busy loop that waits for the query execution to finish either with success,
        # failure or cancelation.
        while True:
            response = self.client.get_query_execution(QueryExecutionId=executionId)
            state = response['QueryExecution']['Status']['State']
            if state == 'SUCCEEDED' or state == 'FAILED' or state == 'CANCELLED' :
                break

        if state == 'FAILED':
            # Return query failed execution.
            pass
        if state == 'CANCELLED':
            # Return query cancelled execution.
            pass

        # If we have s3Transfer enabled then let's go ahead and directly transfer the s3
        # file locally and read data from it.
        if s3Transfer:
            match = re.search(r's3://([^/]+)/(.+)', self.s3_location)
            bucketName = None
            objPath = None
            if match:
               bucketName = match.group(1)
               objPath = match.group(2)

            if bucketName and objPath:
                # Because we use .csv as the extension, the S3 file is a .txt which can happen
                # for table meta-data (example: show table) queries this will not work.
                # But those are small queries and we can fall through to the classical method below.
                localPath = f'{self.csvDir}/{executionId}.csv'
                self.s3.download_file(bucketName,
                                      f'{objPath}/{executionId}.csv',
                                      localPath)

                if os.path.isfile(localPath):
                    # Load it into a dataframe and ship it out to the user
                    with open(localPath, 'r') as f:
                       frame = pandas.read_csv(f)
                       if frame.shape[0] > 0:
                           return frame

        # TODO: Give users the option to stop pagination, or alert them that this is a big
        #       query and can lead to pagination / memory hog.
        # Query execution has finished we can now get the query results.
        frame, nextToken = self.queryResults(executionId,
                                             nextToken=None,
                                             columnNames=[])
        # If this request was paginated, we go ahead and get all the remaining pages.
        while nextToken:
            framepage, nextToken = self.queryResults(executionId,
                                                     nextToken=nextToken,
                                                     columnNames=frame.columns)
            frame = pandas.concat([frame, framepage])

        # Save this query to the local .cache directory if the offline caching is set to true.
        if self.offlineCache:
            filename = self._cacheFileName(queryString)
            frame.to_csv(self.cacheDir+'/'+filename+'.cache', index=False)

        return frame

    """
    Method which calculates the hashed filename for cached query results.

    """
    def _cacheFileName(self, queryString:str) -> str:
        hash = hashlib.md5(queryString.encode())
        filename = hash.hexdigest()

        return filename
