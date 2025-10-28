# SensorFabric

A Python library developed by the University of Arizona's [Center of Biomedical Informatics and Biostatistics (CB2)](https://cb2.arizona.edu) for accessing, storing, and processing sensor data from multiple sources.

## Overview

SensorFabric provides a unified interface for working with sensor data from various sources including MyDataHelps (MDH) and AWS Athena. The library abstracts the complexity of authentication, data retrieval, and query execution, allowing you to focus on analyzing your sensor data.

## Installation

```bash
pip install sensorfabric
```

## Quick Start with Needle (Recommended)

The `Needle` class provides a seamless, unified interface for accessing sensor data from multiple sources. It automatically handles authentication, credential refresh, and query execution.

### Connecting to MyDataHelps (MDH)

```python
from sensorfabric.needle import Needle

# Create a Needle instance for MDH
needle = Needle(method='mdh')

# Execute queries - Needle handles all authentication automatically
df = needle.execQuery('SELECT * FROM device_data LIMIT 10')
print(df.head())
```

That's it! With just two lines of code, you can access your MDH data through AWS Athena.

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
export SF_CATALOG="AwsDataCatalog"  # Optional, defaults to AwsDataCatalog
export SF_WORKGROUP="primary"       # Optional, defaults to primary
export SF_S3LOC="s3://your-bucket/path/"  # Optional

# AWS Credentials (or use aws configure)
export AWS_PROFILE="your-profile"
```

## Features

### 🔄 Automatic Credential Management

Needle automatically:
- Generates JWT tokens for MDH authentication
- Requests temporary AWS credentials from MDH
- Refreshes expired credentials before queries
- Manages in-memory credential storage

No need to worry about token expiration or credential refresh!

### 📊 Pandas DataFrame Results

All queries return results as pandas DataFrames for easy data manipulation:

```python
from sensorfabric.needle import Needle
import pandas as pd

needle = Needle(method='mdh')

# Query returns a DataFrame
df = needle.execQuery('''
    SELECT participantId, timestamp, heart_rate
    FROM device_data
    WHERE date >= '2024-01-01'
''')

# Use pandas methods directly
print(df.describe())
print(df.groupby('participantId').mean())
```

### 💾 Query Caching

Enable offline caching to avoid re-running expensive queries:

```python
needle = Needle(method='mdh', offlineCache=True)

# First run hits Athena and caches results
df = needle.execQuery('SELECT * FROM large_table')

# Subsequent runs use cached results
df = needle.execQuery('SELECT * FROM large_table')
```

Cached results are stored in a `.cache/` directory using MD5-hashed query strings.

## Advanced Usage

### Custom Configuration

You can provide configuration programmatically instead of using environment variables:

```python
from sensorfabric.needle import Needle

# MDH configuration
mdh_config = {
    'account_secret': 'your-secret',
    'account_name': 'your.account.name.mydatahelps.org',
    'project_id': 'your-project-id',
    'project_name': 'your-project-name'
}

needle = Needle(
    method='mdh',
    mdh_configuration=mdh_config,
    offlineCache=True
)

df = needle.execQuery('SELECT * FROM device_data')
```

### Direct AWS Athena Access

```python
# AWS configuration
aws_config = {
    'database': 'my_database',
    'catalog': 'AwsDataCatalog',
    'workgroup': 'primary',
    's3_location': 's3://my-bucket/results/'
}

needle = Needle(
    method='aws',
    aws_configuration=aws_config
)

df = needle.execQuery('SELECT * FROM my_table')
```

### Using the MDH Module Directly

For more control over MDH operations, you can use the MDH class directly:

```python
from sensorfabric.mdh import MDH

# Initialize MDH client
mdh = MDH(
    account_secret='your-secret',
    account_name='your.account.name.mydatahelps.org',
    project_id='your-project-id'
)

# Get all participants
participants = mdh.getAllParticipants()
print(f"Total participants: {participants['totalParticipants']}")

# Get survey results
surveys = mdh.getSurveyResults(queryParam={
    'surveyName': 'Daily Check-in',
    'startDate': '2024-01-01'
})

# Get device data
device_data = mdh.getDeviceDataPoints(
    namespace='AppleHealth',
    types=['HeartRate', 'Steps'],
    queryParam={'startDate': '2024-01-01'}
)

# Update participant custom fields
participants_to_update = [
    {
        "participantIdentifier": "AA-0000-0001",
        "customFields": {
            "sync_date": "2024-12-15"
        }
    }
]
result = mdh.update_participants(participants_to_update)
```

## Module Overview

### 📌 Needle (`sensorfabric.needle`)
Unified interface supporting multiple data sources ('aws', 'mdh'). **Recommended for most use cases.**

### 🔐 MDH (`sensorfabric.mdh`)
MyDataHelps API gateway with token management, participant management, survey results, and device data access.

### ☁️ Athena (`sensorfabric.athena`)
AWS Athena query execution with caching and pagination support.

### 🔧 Utils (`sensorfabric.utils`)
Shared utilities including AWS credentials management and timestamp conversion.

### 📄 JSON (`sensorfabric.json`)
JSON processing utilities with nested JSON flattening capabilities.

## Requirements

- Python >= 3.6
- boto3 (AWS SDK)
- pandas (data manipulation)
- pyjwt==2.10.1 (JWT token handling)
- requests (HTTP client)
- cryptography (security)
- jsonschema==4.24.0 (schema validation)

## Common Use Cases

### Example 1: Analyze Heart Rate Data from MDH

```python
from sensorfabric.needle import Needle
import pandas as pd

# Connect to MDH
needle = Needle(method='mdh')

# Query heart rate data
df = needle.execQuery('''
    SELECT
        participantId,
        timestamp,
        heart_rate,
        date
    FROM device_data
    WHERE type = 'HeartRate'
    AND date >= '2024-01-01'
    ORDER BY timestamp
''')

# Calculate average heart rate per participant
avg_hr = df.groupby('participantId')['heart_rate'].mean()
print(avg_hr)
```

### Example 2: Export Participant Data

```python
from sensorfabric.mdh import MDH

mdh = MDH()

# Get all participants with custom fields
participants = mdh.getAllParticipants()

# Extract participant identifiers and email addresses
for p in participants['participants']:
    pid = p['participantIdentifier']
    email = p['demographics'].get('email', 'N/A')
    print(f"{pid}: {email}")
```

### Example 3: Sync Device Data with Custom Timestamps

```python
from sensorfabric.mdh import MDH
from datetime import datetime

mdh = MDH()

# Get device data
device_data = mdh.getDeviceDataPoints(
    namespace='AppleHealth',
    types=['Steps', 'HeartRate'],
    queryParam={
        'startDate': '2024-01-01',
        'endDate': '2024-01-31'
    }
)

# Update sync timestamp for participants
sync_time = datetime.utcnow().isoformat()
participants_to_update = [
    {
        "participantIdentifier": "AA-0000-0001",
        "customFields": {"last_sync": sync_time}
    }
]

result = mdh.update_participants(participants_to_update)
print(f"Updated {result['totalUpdated']} participants")
```

## Error Handling

```python
from sensorfabric.needle import Needle
import requests

try:
    needle = Needle(method='mdh')
    df = needle.execQuery('SELECT * FROM device_data')
except requests.exceptions.HTTPError as e:
    print(f"HTTP Error: {e}")
except Exception as e:
    print(f"Error: {e}")
```

## Security Best Practices

1. **Never commit credentials to version control**
   - Use environment variables or secret management services
   - Add `.env` files to `.gitignore`

2. **Use service accounts with minimal permissions**
   - Only grant access to required projects and data

3. **Rotate credentials regularly**
   - Update MDH service account secrets periodically
   - Monitor for unauthorized access

4. **Secure credential storage**
   - Use AWS Secrets Manager, Azure Key Vault, or similar
   - Encrypt credentials at rest

## Troubleshooting

### "Invalid MDH credentials"
- Verify `MDH_SECRET_KEY`, `MDH_ACCOUNT_NAME`, and `MDH_PROJECT_ID` are set correctly
- Check that your service account has access to the project
- Ensure the account name follows the format: `your.organization.projectname.mydatahelps.org`

### "AWS credentials expired"
- Needle automatically refreshes credentials, but check your internet connection
- Verify MDH service account has permission to generate data explorer credentials

### "Query timeout"
- Large queries may take time; consider adding `LIMIT` clauses
- Enable caching for repeated queries: `Needle(method='mdh', offlineCache=True)`

### "Empty DataFrame returned"
- Verify the table/database exists in Athena
- Check date ranges and filter conditions
- Ensure data has been exported from MDH to Athena

## Contributing

Contributions are welcome! Please contact the CB2 team at the University of Arizona.

## License

MIT License - see LICENSE file for details

## Support

For issues, questions, or feature requests, please contact:
- **Author:** Shravan Aras
- **Email:** shravanaras@arizona.edu
- **Organization:** University of Arizona, [Center of Biomedical Informatics and Biostatistics (CB2)](https://cb2.arizona.edu)

## Acknowledgments

Developed by the University of Arizona's [Center of Biomedical Informatics and Biostatistics (CB2)](https://cb2.arizona.edu).
