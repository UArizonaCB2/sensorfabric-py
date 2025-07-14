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

# Build Lambda functions (Docker images) - Legacy
./build_lambdas.sh

# Clean build artifacts
./build_lambdas.sh --clean

# Build and deploy to AWS Lambda via ECR
./build_and_deploy.sh

# Build and deploy using CDK
./build_and_deploy.sh --use-cdk

# Full deployment pipeline with testing and rollback
./deploy.sh

# Deploy using CDK with comprehensive pipeline
./deploy.sh --cdk
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
- `MDH_SECRET_KEY`: Account secret for authentication
- `MDH_ACCOUNT_NAME`: Account name for authentication
- `MDH_PROJECT_ID`: Project ID for data access
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

## Lambda Functions

The project includes AWS Lambda functions for data processing deployed via Docker containers to overcome the 50MB zip file limitation.

### UltraHuman Lambda Functions
- **`uh_upload.py`**: Lambda function for uploading UltraHuman sensor data (`biobayb_uh_uploader`)
- **`uh_publisher.py`**: Lambda function for publishing UltraHuman data to other systems (`biobayb_uh_sns_publisher`)

### Docker Container Deployment
- **ECR Repository**: `509812589231.dkr.ecr.us-east-1.amazonaws.com/uh-biobayb`
- **Container Limit**: 10GB (vs 50MB zip limit)
- **Base Image**: `public.ecr.aws/lambda/python:3.13`
- **Platform**: linux/amd64 for AWS Lambda compatibility

### Build and Deployment Scripts
- **`build_lambdas.sh`**: Legacy script for building Docker images
- **`build_and_deploy.sh`**: Enhanced script for building, pushing to ECR, and deploying
- **`deploy.sh`**: Comprehensive deployment pipeline with testing, validation, and rollback
- **`cdk/`**: AWS CDK infrastructure for Lambda functions with Docker containers

### Deployment Methods
1. **Direct Lambda Updates**: Using AWS CLI to update function code with new container images
2. **CDK Deployment**: Infrastructure as Code using AWS CDK for complete stack management
3. **Automated Pipeline**: Full CI/CD pipeline with testing, validation, and rollback capabilities

### Container Features
- **Optimized Layer Caching**: Requirements installed separately for better rebuild performance
- **System Dependencies**: Includes gcc and python3-devel for native package compilation
- **Lambda-Specific Environment**: Proper Python path and optimization flags
- **Cache Directory**: Pre-created cache directory for Athena query caching

## Key Dependencies

Core dependencies from setup.py:
- boto3 (AWS services)
- pandas (data manipulation) 
- numpy (numerical operations)
- pyjwt==2.10.1 (JWT token handling)
- requests (HTTP requests)
- cryptography (security)
- awswrangler (extended AWS data operations)
- jsonschema==4.24.0 (JSON schema validation)

## File Structure Notes

- Main package code in `sensorfabric/`
- Build artifacts in `build/` (ignored in development)
- Virtual environment in `fabric-venv/` (if present)
- Egg info in `sensorfabric.egg-info/`
- Docker configurations in `docker/`
- CDK infrastructure in `cdk/`
- Deployment scripts: `build_lambdas.sh`, `build_and_deploy.sh`, `deploy.sh`
- Lambda function backups in `backup/` (created during deployment)

## Deployment Pipeline

### Quick Start
```bash
# Simple deployment (direct Lambda updates)
./build_and_deploy.sh

# Full deployment with CDK
./deploy.sh --cdk

# Rollback if needed
./deploy.sh --rollback
```

### Pipeline Features
- **Pre-deployment Validation**: Checks prerequisites, AWS credentials, and project structure
- **Automated Backup**: Creates backups of current Lambda functions before deployment
- **Health Checks**: Validates function state and monitors for recent errors
- **Testing**: Automated testing of deployed functions with sample events
- **Rollback Capability**: Automatic rollback on failure or manual rollback command
- **Logging**: Comprehensive logging with timestamps and colored output