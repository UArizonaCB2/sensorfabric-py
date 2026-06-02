#!/usr/bin/env python3

"""
Author : SensorFabric Contributors
Organization : University of Arizona

This package is part of the SensorFabric project.

Description :
A set of bindings to connect to ClickHouse to help run queries on sensor data.
Follows the same pattern as the Athena connector, returning results as Pandas DataFrames.
"""

import pandas
import hashlib
import os


class ClickHouse:
    """
    This class creates bindings to a ClickHouse server and allows for easy configuration,
    query execution, and result retrieval as Pandas DataFrames.

    Parameters
    ----------
    1. host : ClickHouse server hostname or IP address.
    2. port : ClickHouse server port. Default is 9000 (native protocol).
    3. database : Name of the database to connect to. Default is 'default'.
    4. user : Username for authentication. Default is 'default'.
    5. password : Password for authentication. Default is empty string.
    6. secure : Whether to use TLS/SSL for the connection. Default is False.
    7. offlineCache : (True | False) If set to True the results from queries are cached
       locally and used for future requests.
    8. settings : Optional dictionary of ClickHouse settings to apply to queries.
    """

    def __init__(self, host: str,
                 port: int = 9000,
                 database: str = 'default',
                 user: str = 'default',
                 password: str = '',
                 secure: bool = False,
                 offlineCache: bool = False,
                 settings: dict = None):

        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.secure = secure
        self.offlineCache = offlineCache
        self.settings = settings or {}

        try:
            from clickhouse_driver import Client
        except ImportError:
            raise ImportError(
                "clickhouse-driver is required for ClickHouse support. "
                "Install it with: pip install clickhouse-driver"
            )

        self.client = Client(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            secure=self.secure,
            settings=self.settings
        )

        self.cacheDir = '.cache'

        # If we have indicated offline cache then go ahead and make the
        # .cache directory.
        if self.offlineCache:
            if not os.path.isdir(self.cacheDir):
                os.mkdir(self.cacheDir)

    def execQuery(self, queryString: str, params: dict = None,
                  cached: bool = False) -> pandas.DataFrame:
        """
        Execute a query and return the result as a Pandas DataFrame.

        Parameters
        ----------
        1. queryString : SQL query to execute.
        2. params : Optional dictionary of query parameters for parameterized queries.
        3. cached : True | False (default). If set to True, previous query results
           from the local cache are returned. offlineCache=True must be passed during
           object creation, otherwise this option is ignored.

        Returns
        -------
        A Pandas DataFrame with the query results. If the query returns an empty
        dataset, an empty DataFrame is returned.
        """

        # Check if we have requested cached results and caching is enabled.
        if self.offlineCache and cached:
            filename = self._cacheFileName(queryString)
            path = os.path.join(self.cacheDir, filename + '.cache')
            if os.path.isfile(path):
                frame = pandas.read_csv(path)
                return frame

        # Execute the query using clickhouse-driver which returns
        # (data, columns) when with_column_types=True.
        result = self.client.execute(
            queryString,
            params=params,
            with_column_types=True
        )

        data = result[0]
        columns = [col[0] for col in result[1]]

        if not data:
            return pandas.DataFrame(columns=columns)

        frame = pandas.DataFrame(data, columns=columns)

        # Save to cache if offline caching is enabled.
        if self.offlineCache:
            filename = self._cacheFileName(queryString)
            path = os.path.join(self.cacheDir, filename + '.cache')
            frame.to_csv(path, index=False)

        return frame

    def execute(self, queryString: str, params: dict = None) -> int:
        """
        Execute a non-SELECT query (INSERT, CREATE, ALTER, etc.) and return
        the number of rows affected.

        Parameters
        ----------
        1. queryString : SQL statement to execute.
        2. params : Optional dictionary of query parameters.

        Returns
        -------
        Number of rows affected, or 0 for DDL statements.
        """
        result = self.client.execute(queryString, params=params)
        if isinstance(result, int):
            return result
        return 0

    def insert_dataframe(self, table: str, df: pandas.DataFrame,
                         settings: dict = None) -> int:
        """
        Insert a Pandas DataFrame into a ClickHouse table.

        Parameters
        ----------
        1. table : Target table name (can include database prefix, e.g. 'db.table').
        2. df : Pandas DataFrame to insert.
        3. settings : Optional ClickHouse settings for the insert operation.

        Returns
        -------
        Number of rows inserted.
        """
        if df.empty:
            return 0

        columns = list(df.columns)
        data = df.values.tolist()

        col_str = ', '.join(columns)
        query = f'INSERT INTO {table} ({col_str}) VALUES'

        result = self.client.execute(
            query,
            data,
            types_check=True,
            settings=settings
        )

        return result if isinstance(result, int) else len(data)

    def get_tables(self, database: str = None) -> pandas.DataFrame:
        """
        List all tables in the specified database.

        Parameters
        ----------
        1. database : Database name. Defaults to the connected database.

        Returns
        -------
        A Pandas DataFrame with table information.
        """
        db = database or self.database
        query = f"SELECT name, engine, total_rows, total_bytes FROM system.tables WHERE database = %(db)s"
        return self.execQuery(query, params={'db': db})

    def get_columns(self, table: str, database: str = None) -> pandas.DataFrame:
        """
        Get column information for a specific table.

        Parameters
        ----------
        1. table : Table name.
        2. database : Database name. Defaults to the connected database.

        Returns
        -------
        A Pandas DataFrame with column metadata.
        """
        db = database or self.database
        query = (
            "SELECT name, type, default_kind, default_expression, comment "
            "FROM system.columns WHERE database = %(db)s AND table = %(table)s"
        )
        return self.execQuery(query, params={'db': db, 'table': table})

    def _cacheFileName(self, queryString: str) -> str:
        """Calculate the hashed filename for cached query results."""
        hash_val = hashlib.md5(queryString.encode())
        return hash_val.hexdigest()
