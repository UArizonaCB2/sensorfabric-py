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

    Note - The workgroup must have query result s3 path set.
    """
    def __init__(self, database:str,
                 catalog='AwsDataCatalog',
                 workgroup='primary'):
        self.database = database
        self.catalog = catalog
        self.workgroup = workgroup

        self.client = boto3.client('athena')

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
    """
    def queryResults(self, executionId):
        result = self.client.get_query_results(
            QueryExecutionId = executionId
        )

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
        columnNames = []  # So we can maintain the order.
        # The first element in the data list will be the column names.
        cols = data[0]['Data']
        for c in cols:
            k = list(c.keys())[0]
            columnNames += [c[k]]
            map[c[k]] = []

        print(columnNames)

        for i in range(2, len(data)):
            row = data[i]['Data']
            for idx, r in enumerate(row):
                temp = map[columnNames[idx]]
                if len(r.keys()) > 0:
                    k = list(r.keys())[0]
                    temp += [r[k]]
                else:   # There is no data for this column
                    temp += [None]  # pandas will conver this later to NaN

                map[columnNames[idx]] = temp

        # Convert the result into a pandas
        return pandas.DataFrame(map)

    """
    Description
    -----------
    This method is blocking. It executes the query and returns the result as a pandas
    data frame.

    Parameters
    ----------
    1. queryString : SQL query to execute.
    2. queryParam : A list of query parameters.
    3. cached : True | False (default). If set to True, previous query results
    from within the last 60 mins are returned.
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

        # Query execution has finished we can now get the query results.
        frame = self.queryResults(executionId)

        return frame
