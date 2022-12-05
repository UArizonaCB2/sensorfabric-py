# Python Package for Sensor Fabric

Welcome to the python package for SensorFabric. 

## What is SensorFabric?

SensorFabric is an initiative by University of Arizona's Center of Bioinformatics and Biostatistics (CB2)
to create homogenous layer for accessing, storing and processing sensor data.

## How to install it?

You can install the sensorfabric python library using `pip` as follows
```
pip install sensorfabric
```

## Getting Started

SensorFabric has several different modules. We try to give a basic overview here.

### Athena Module
The Athena module abstracts query execution and caching, by returning results from AWS Athena
as Pandas dataframes. </br>
**To run this locally you must have aws credentials configured using `aws configure`**

Example
```
from sensorfabric.athena import athena
import pandas as pd

# Create an object.
db = athena(database='MyExampleDatabase')

# Execute a query by performing a blocking operation.
frame = db.execQuery('SELECT "participantId" FROM "fitbit_hr" LIMIT 5')
# Print out the pandas frame.
print(frame.head())

# Queries can also be run async (callbacks are currently not supported)
executionId = db.startQueryExec('SELECT "participantId" FROM "fitbit_hr" LIMIT 5')
# Returns immidately, with the query execution ID. 

# Do some important work here

frame = db.queryResults(executionId)
# Returns the query result as a dataframe
print(frame.head()) 
```

**Enabling offline caching**
In order to enable offline caching for queries pass `offlineCache=True` to `Athena()`.
When caching is enabled a `.cache` folder is creating in the calling directory, and query
results are stored in it. Files are named using the md5 hash of the query string. 
Pass `cached=True` to `execQuery()` in order to use cached results. The following important
points need to be noted when using caching -
* Only exact query strings will cache to the same files.
* Both `offlineCache` and `cached` must be set true for this to work.
* There is currently no time limit on the cached results (This might change). 
* If you want to reset the cache you can delete the `.cache directory`.

Example
```
db = athena(database='MyBigDatabase', offlineCache=True)

# The first query will hit Athena but cache the local results in the .cache directory.
frame = db.execQuery('SELECT DISTINCT(pid) FROM temperature', cached=True)
print(frame.head())
# The second exact query will return results from the local cache.
frame = db.execQuery('SELECT DISTINCT(pid) FROM temperature', cached=True)
```
