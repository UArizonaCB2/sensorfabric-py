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
1. Handle pagination for larger queries.
2. Implement the default timeout condition to prevent this code from going into an infinite loop.
3. Error handling for failed and cancelled queries.
4. Support query caching internally inside the library, to make use of the same execution ID.
"""

import boto3
import pandas
import hashlib
import os

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

    Note - The workgroup must have query result s3 path set.
    """
    def __init__(self, database:str,
                 catalog='AwsDataCatalog',
                 workgroup='primary',
                 offlineCache=False):
        self.database = database
        self.catalog = catalog
        self.workgroup = workgroup
        self.offlineCache = offlineCache

        self.client = boto3.client('athena')

        self.cacheDir = '.cache'

        if self.offlineCache:
            if not os.path.isdir(self.cacheDir):
                os.mkdir(self.cacheDir)

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
    def startQueryExec(self, queryString:str, queryParams=[], cached=False) -> str:
        result = self.client.start_query_execution(
            QueryString = queryString,
            QueryExecutionContext = {
                'Database' : self.database,
                'Catalog' : self.catalog
            },
            WorkGroup = self.workgroup,
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

    Returns
    -------
    Returns a pandas dataframe. If the SQL query returns an empty dataset,
    this will return an empty pandas frame.
    """
    def execQuery(self, queryString:str, queryParams=[],
                  cached=False, defaultTimeout=60) -> pandas.DataFrame:
        executionId = self.startQueryExec(queryString,
                                          queryParams,
                                          cached)

        # Check if we have requested cached results and we are setup for serving cache results (offlineCache=True)
        if self.offlineCache and cached:
            filename = self._cacheFileName(queryString)
            path = self.cacheDir+'/'+filename+'.cache'
            if os.path.isfile(path):
                # Load the data from the cache and return the results.
                frame = pandas.read_csv(open(path, 'r'))
                return frame

        state = None
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
