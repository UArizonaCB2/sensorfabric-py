# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SensorFabric is a Python library developed by the University of Arizona's Center of Bioinformatics and Biostatistics (CB2) for accessing, storing, and processing sensor data. It provides a homogeneous layer for working with various sensor data sources including AWS Athena, MyDataHelps (MDH), and UltraHuman APIs.

## Core Architecture

### Main Modules

- **`athena.py`**: AWS Athena query execution and caching with Pandas DataFrame results
- **`mdh.py`**: MyDataHelps API authentication and data access utilities  
- **`uh.py`**: UltraHuman API client for metrics data (development/production environments)
- **`needle.py`**: Unified interface supporting multiple data sources ('aws', 'mdh')
- **`utils.py`**: Shared utilities including AWS credentials management and timestamp conversion
- **`json/`**: JSON processing utilities with `Flatten.py` for nested JSON flattening
- **`schemas/`**: JSON schema definitions for sensor data validation
- **`endpoints.py`**: API endpoint configurations for external services

### Key Classes

- `athena`: Connects to AWS Athena with query caching and pagination support
- `MDH`: MyDataHelps API gateway with token management
- `UltrahumanAPI`: API client with environment-based configuration
- `Needle`: Unified data source interface supporting multiple backends

## Development Commands

### Installation & Setup
```bash
# Install the package
pip install sensorfabric

# Install in development mode from source
pip install -e .

# Virtual environment setup (if using fabric-venv)
source fabric-venv/bin/activate
```

### Building & Distribution
```bash
# Build the package
python setup.py build

# Create distribution packages
python setup.py sdist bdist_wheel
```

## Environment Configuration

### AWS Athena
- Requires AWS credentials configured via `aws configure`
- Set `AWS_PROFILE` environment variable for non-default profiles
- Workgroups must have S3 query result locations configured

### UltraHuman API
- `UH_ENVIRONMENT`: 'development' or 'production' (default: 'development')
- `UH_DEV_API_KEY` / `UH_PROD_API_KEY`: API keys for respective environments
- `UH_DEV_BASE_URL` / `UH_PROD_BASE_URL`: Base URLs for respective environments

### MyDataHelps
- Requires account secret, account name, and project ID for authentication
- Supports JWT token management with automatic refresh

## Data Processing Patterns

### Athena Queries
- Results returned as Pandas DataFrames
- Supports both synchronous (`execQuery`) and asynchronous (`startQueryExec`/`queryResults`) execution
- Query caching available with `.cache` directory storage using MD5 hashed query strings

### JSON Processing
- Use `sensorfabric.json.Flatten.flatten()` for nested JSON flattening
- Sensor data follows schema defined in `schemas/sensor_data_schema.json`
- Supports multiple sensor types: hr, temp, hrv, steps, motion

### Timestamp Handling
- Unix timestamp to ISO8601 conversion utilities in `utils.py`
- Timezone-aware datetime processing with pytz support

## Key Dependencies

Core dependencies from setup.py:
- boto3 (AWS services)
- pandas (data manipulation) 
- numpy (numerical operations)
- pyjwt==2.8.0 (JWT token handling)
- requests (HTTP requests)
- cryptography (security)
- awswrangler (extended AWS data operations)

## File Structure Notes

- Main package code in `sensorfabric/`
- Build artifacts in `build/` (ignored in development)
- Virtual environment in `fabric-venv/` (if present)
- Egg info in `sensorfabric.egg-info/`