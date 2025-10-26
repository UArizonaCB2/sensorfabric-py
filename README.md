# SensorFabric Python Package

Welcome to the `sensorfabric` Python package, developed by the University of Arizona's Center of Bioinformatics and Biostatistics (CB2). This package provides a unified interface for accessing, storing, and processing sensor data through a convenient Python library.

## Table of Contents
- [What is SensorFabric?](#what-is-sensorfabric)
- [Installation](#installation)
- [Getting Started](#getting-started)
  - [Needle: Unified Connector](#needle-unified-connector)
  - [Quick Start (AWS Mode)](#quick-start-aws-mode)
  - [Quick Start (MDH Mode)](#quick-start-mdh-mode)
- [Needle API](#needle-api)
- [Security & Secrets](#security--secrets)
- [Requirements](#requirements)
- [License](#license)

## What is SensorFabric?

SensorFabric is an initiative by the University of Arizona's CB2 to create a homogenous layer for accessing, storing, and processing sensor data. The `sensorfabric` Python package simplifies interactions with sensor data stored in AWS Athena or MyDataHelps (MDH) environments, providing a unified interface for querying and managing data.

## Installation

To install the `sensorfabric` Python package, use `pip`. The package requires Python 3.10 or higher.

```bash
pip install sensorfabric
```

## Getting Started

### Needle: Unified Connector

The `Needle` class is a convenience wrapper that provides a unified interface to:
- Connect directly to AWS Athena (`method='aws'`), or
- Connect to MyDataHelps (MDH) (`method='mdh'`), automatically fetching short-lived AWS explorer credentials and querying the MDH Athena export.

### Quick Start (AWS Mode)

In AWS mode, `Needle` connects directly to an AWS Athena instance. You can configure it using environment variables or a configuration dictionary. Environment variables take precedence when no configuration dictionary is provided.

#### Environment Variables (Optional)
- `SF_DATABASE`: Athena database name
- `SF_CATALOG`: Data catalog (default: `AwsDataCatalog`)
- `SF_WORKGROUP`: Workgroup (default: `primary`)
- `SF_S3LOC`: S3 output location for query results
- `AWS_PROFILE`: Optional local AWS profile (alternatively, pass `profileName` to `Needle`)

#### Example

```python
from sensorfabric.needle import Needle

# Initialize Needle in AWS mode
needle = Needle(
    method='aws',
    aws_configuration={
        'database': 'my_db',
        'catalog': 'AwsDataCatalog',
        'workgroup': 'primary',
        's3_location': 's3://my-athena-results/'
    },
    offlineCache=True,
    profileName='my-aws-profile'  # Optional: relies on default AWS credentials chain if omitted
)

# Execute a query
df = needle.execQuery("SELECT * FROM my_table LIMIT 10", queryParams=[], defaultTimeout=60)
print(df.head())
```

If `aws_configuration` is omitted, `Needle` will read `SF_DATABASE`, `SF_CATALOG`, `SF_WORKGROUP`, and `SF_S3LOC` from environment variables.

### Quick Start (MDH Mode)

In MDH mode, `Needle` uses MyDataHelps service credentials to obtain temporary AWS explorer credentials, automatically configuring the Athena database, workgroup, and S3 location for the MDH export project. It also transparently refreshes credentials when they expire.

#### Required Environment Variables (if no configuration dictionary is provided)
- `MDH_SECRET_KEY`: MDH service secret
- `MDH_ACCOUNT_NAME`: MDH account name
- `MDH_PROJECT_ID`: MDH project ID
- `MDH_PROJECT_NAME`: MDH project name

#### Example

```python
from sensorfabric.needle import Needle
import os

# Initialize Needle in MDH mode
needle = Needle(
    method='mdh',
    mdh_configuration={
        'account_secret': os.getenv('MDH_SECRET_KEY'),
        'account_name': os.getenv('MDH_ACCOUNT_NAME'),
        'project_id': os.getenv('MDH_PROJECT_ID'),
        'project_name': os.getenv('MDH_PROJECT_NAME')
    },
    offlineCache=True
)

# Execute a query (returns a Pandas DataFrame)
df = needle.execQuery("SELECT * FROM my_table LIMIT 100")
print(df.head())
```

## Needle API

The `Needle` class provides a simple API for querying data. Below is an example of its usage:

```python
from sensorfabric.needle import Needle

# Initialize Needle
needle = Needle(
    method='aws',
    aws_configuration={'database': 'my_db'},
    offlineCache=True
)

# Execute a query (blocking)
df = needle.execQuery("SELECT * FROM my_table WHERE col = 'x' LIMIT 5")

# Use cached results for identical queries (if cached=True in Athena)
df2 = needle.execQuery("SELECT * FROM my_table WHERE col = 'x' LIMIT 5")
```

### Key Parameters for `Needle.__init__`
- `method`: Either `'aws'` or `'mdh'`
- `aws_configuration`: Dictionary with `database`, `catalog`, `workgroup`, and `s3_location` (AWS mode)
- `mdh_configuration`: Dictionary with `account_secret`, `account_name`, `project_id`, and `project_name` (MDH mode)
- `offlineCache`: Boolean (`True`/`False`) to enable/disable local caching in `.cache/`
- `profileName`: String specifying an AWS profile (AWS mode; optional)

## Security & Secrets

- **Never commit secrets**: Avoid storing MDH secrets or AWS keys in your codebase. Use environment variables, AWS Parameter Store, or a secret manager.
- **MDH Mode**: The package requests short-lived explorer credentials and refreshes them as needed.
- **Caching**: Set `offlineCache=False` in sensitive environments to prevent local caching of query results.

## Requirements

- Python 3.10 or higher
- Dependencies (automatically installed with `pip install sensorfabric`):
  - `pandas` for DataFrame handling
  - `boto3` for AWS interactions
  - Other dependencies as specified in `setup.py`

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

---
