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
