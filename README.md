# SensorFabric
A Python library developed by the University of Arizona's [Center of Biomedical Informatics and Biostatistics (CB2)](https://cb2.arizona.edu) for accessing, storing, and processing sensor data from multiple sources.
> **Note:** Table names and field names used in queries throughout this documentation are for illustration purposes only. Their actual names depend on the specific database configuration being accessed.

## What is SensorFabric?
SensorFabric is designed to simplify the integration of sensor data from platforms like MyDataHelps (MDH), AWS Athena, and ClickHouse. It's ideal for researchers, data scientists, and developers working with IoT devices, health data, or environmental sensors, providing a unified interface for authentication, data retrieval, and analysis.

## Overview
SensorFabric abstracts the complexity of authentication, data retrieval, and query execution, allowing you to focus on analyzing sensor data. [Jump to Installation](#installation) to get started!

## Installation
```bash
pip install sensorfabric
```
**Requirements:** Python 3.10 or higher

## Quick Start with Needle (Recommended)
The `Needle` class provides a seamless interface for accessing sensor data. It handles authentication and query execution automatically.

### Connecting to MyDataHelps (MDH)
```python
from sensorfabric.needle import Needle
# Initialize Needle for MDH (uses environment variables for credentials)
needle = Needle(method='mdh')
# Execute a sample query; replace [tablename] with your actual table
df = needle.execQuery('SELECT * FROM [tablename] LIMIT 10')
print(df.head())  # Display the first 5 rows of the result
```
✅ *That's it! With two lines, you can query MDH data via AWS Athena.*

### Connecting to AWS Athena (Direct)
```python
from sensorfabric.needle import Needle
# Initialize with AWS configuration
needle = Needle(method='aws')
# Run a query directly on Athena
df = needle.execQuery('SELECT * FROM [tablename] LIMIT 10')
print(df.head())
```

### Connecting to ClickHouse
```python
from sensorfabric.needle import Needle
# Initialize with ClickHouse (uses environment variables for connection)
needle = Needle(method='clickhouse')
# Run a query on ClickHouse
df = needle.execQuery('SELECT * FROM [tablename] LIMIT 10')
print(df.head())
```

## Environment Variables
### Required for MyDataHelps (MDH)
To use Needle with MDH, you need to configure the following environment variables:
```bash
# MyDataHelps Authentication
export MDH_SECRET_KEY="your-mdh-service-account-secret"
export MDH_ACCOUNT_NAME="your.account.name.mydatahelps.org"
export MDH_PROJECT_ID="your-project-uuid"
export MDH_PROJECT_NAME="your-project-name"
```
**How to obtain these credentials:**
1. Log into your MyDataHelps account
2. Navigate to your project settings
3. Create or access a service account
4. Copy the account secret, account name, project ID, and project name

### Optional for AWS Athena (Direct Access)
If you're using AWS Athena directly (not through MDH), configure these variables:
```bash
# AWS Athena Configuration
export SF_DATABASE="your-athena-database"
export SF_CATALOG="AwsDataCatalog" # Optional, defaults to AwsDataCatalog
export SF_WORKGROUP="primary" # Optional, defaults to primary
export SF_S3LOC="s3://your-bucket/path/" # Optional
# AWS Credentials (or use aws configure)
export AWS_PROFILE="your-profile"
```

### Optional for ClickHouse
If you're using ClickHouse as your data backend:
```bash
# ClickHouse Configuration
export CH_HOST="localhost"          # ClickHouse server hostname
export CH_PORT="9000"              # Native protocol port (default: 9000, NOT 8123/HTTP)
export CH_DATABASE="default"       # Database name
export CH_USER="default"           # Username
export CH_PASSWORD=""              # Password
export CH_SECURE="false"           # Use TLS/SSL (true/false)
```
> **Note:** This library uses the ClickHouse native protocol (port 9000). The HTTP interface (port 8123) is not supported.

## Features
### 🔄 Automatic Credential Management
- Generates JWT tokens for MDH
- Requests temporary AWS credentials
- Refreshes expired credentials
- Manages in-memory storage
⚠️ *No manual token management required!*

### 📊 Pandas DataFrame Results
```python
from sensorfabric.needle import Needle
import pandas as pd
needle = Needle(method='mdh')
# Query with filters
df = needle.execQuery('''
    SELECT participantId, timestamp, heart_rate
    FROM [tablename]
    WHERE date >= '2024-01-01'
''')
# Analyze with pandas
print(df.describe())  # Summary statistics
print(df.groupby('participantId').mean())  # Group by participant
```

### 💾 Query Caching
```python
needle = Needle(method='mdh', offlineCache=True)
# First run queries Athena and caches
df = needle.execQuery('SELECT * FROM [tablename]')
# Subsequent runs use cache
df = needle.execQuery('SELECT * FROM [tablename]')
```
*Cached in `.cache/` using MD5-hashed queries.*

## Advanced Usage
### Custom Configuration
```python
from sensorfabric.needle import Needle
# Define MDH config
mdh_config = {
    'account_secret': 'your-secret',
    'account_name': 'your.account.name.mydatahelps.org',
    'project_id': 'your-project-id',
    'project_name': 'your-project-name'
}
needle = Needle(method='mdh', mdh_configuration=mdh_config, offlineCache=True)
df = needle.execQuery('SELECT * FROM [tablename]')
```

### Direct AWS Athena Access
```python
aws_config = {
    'database': 'my_database',
    'catalog': 'AwsDataCatalog',
    'workgroup': 'primary',
    's3_location': 's3://my-bucket/results/'
}
needle = Needle(method='aws', aws_configuration=aws_config)
df = needle.execQuery('SELECT * FROM [tablename]')
```

### Direct ClickHouse Access
```python
from sensorfabric.needle import Needle

ch_config = {
    'host': 'clickhouse.example.com',
    'port': 9000,
    'database': 'sensor_data',
    'user': 'reader',
    'password': 'secret',
    'secure': True
}
needle = Needle(method='clickhouse', clickhouse_configuration=ch_config, offlineCache=True)
df = needle.execQuery('SELECT * FROM [tablename]')
```

### Using the ClickHouse Module Directly
```python
from sensorfabric.clickhouse import ClickHouse

ch = ClickHouse(
    host='localhost',
    database='sensor_data',
    offlineCache=True
)

# Query data as a DataFrame
df = ch.execQuery('SELECT * FROM readings WHERE device_id = %(id)s', params={'id': 'sensor-01'})

# Insert a DataFrame into ClickHouse
ch.insert_dataframe('readings', df)

# Introspection
tables = ch.get_tables()
columns = ch.get_columns('readings')
```

### Using the MDH Module Directly
```python
from sensorfabric.mdh import MDH
mdh = MDH(
    account_secret='your-secret',
    account_name='your.account.name.mydatahelps.org',
    project_id='your-project-id'
)
# Fetch participants
participants = mdh.getAllParticipants()
print(f"Total participants: {participants['totalParticipants']}")
# Get survey data
surveys = mdh.getSurveyResults(queryParam={'surveyName': 'Daily Check-in', 'startDate': '2024-01-01'})
# Update participant
participants_to_update = [{"participantIdentifier": "AA-0000-0001", "customFields": {"sync_date": "2024-12-15"}}]
mdh.update_participants(participants_to_update)
```

## Module Overview
### 📌 Needle (`sensorfabric.needle`)
- Unified interface for 'aws', 'mdh', and 'clickhouse' sources. *Recommended for general use.*

### 🔐 MDH (`sensorfabric.mdh`)
- Manages MDH API, tokens, participants, surveys, and device data.

### ☁️ Athena (`sensorfabric.athena`)
- Handles AWS Athena queries with caching and pagination.

### 🏠 ClickHouse (`sensorfabric.clickhouse`)
- Connects to ClickHouse with query execution, caching, DataFrame inserts, and table introspection.

### 🔧 Utils (`sensorfabric.utils`)
- Provides AWS credential management and timestamp utilities.

### 📄 JSON (`sensorfabric.json`)
- Offers JSON flattening and processing tools.

## Requirements
- Python 3.10 or higher
- boto3 (AWS SDK)
- awswrangler (extended AWS data operations)
- pandas (data manipulation)
- numpy (numerical operations)
- pyjwt==2.10.1 (JWT handling)
- requests (HTTP client)
- cryptography (security)
- jsonschema==4.24.0 (schema validation)
- pytz (timezone handling)
- clickhouse-driver>=0.2.9 (ClickHouse native protocol client)

## Error Handling
```python
from sensorfabric.needle import Needle
import requests
try:
    needle = Needle(method='mdh')
    df = needle.execQuery('SELECT * FROM [tablename]')
except requests.exceptions.HTTPError as e:
    print(f"HTTP Error: {e}")
except Exception as e:
    print(f"Error: {e}")
```

## Security Best Practices
1. ✅ *Never commit credentials* – Use `.env` files and add to `.gitignore`
2. ⚠️ *Minimize permissions* – Restrict service account access
3. 🔄 *Rotate credentials* – Update MDH secrets regularly
4. 🔒 *Secure storage* – Use AWS Secrets Manager or similar

## Troubleshooting
### Why "Invalid MDH credentials"?
- Check `MDH_SECRET_KEY`, `MDH_ACCOUNT_NAME`, and `MDH_PROJECT_ID`
- Ensure service account access
- Verify account name format (`your.organization.projectname.mydatahelps.org`)

### Why "Query timeout"?
- Add `LIMIT` to queries
- Enable caching: `Needle(method='mdh', offlineCache=True)`

### Why "Empty DataFrame"?
- Confirm table/database exists
- Check date ranges and filters
- Verify MDH-to-Athena data export

## Version
- *Check [PyPI](https://pypi.org/project/sensorfabric/) for updates.*

## Contributing
Contributions are welcome! Please contact the CB2 team at the University of Arizona.

## License
MIT License - see LICENSE file for details

## Support
For issues, questions, or feature requests, contact:
- **Author:** Shravan Aras
- **Email:** shravanaras@arizona.edu
- **Organization:** University of Arizona, [Center of Biomedical Informatics and Biostatistics (CB2)](https://cb2.arizona.edu)

## Acknowledgments
Developed by the University of Arizona's [Center of Biomedical Informatics and Biostatistics (CB2)](https://cb2.arizona.edu).
