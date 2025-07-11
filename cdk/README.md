# SensorFabric CDK Infrastructure

This directory contains the AWS CDK infrastructure code for deploying SensorFabric Lambda functions using Docker containers.

## Prerequisites

- AWS CLI configured with appropriate credentials
- AWS CDK CLI installed (`npm install -g aws-cdk`)
- Python 3.7+ with pip

## Setup

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Bootstrap CDK (first time only):
```bash
cdk bootstrap
```

## Deployment

### Using CDK directly:
```bash
# Deploy the stack
cdk deploy

# View the diff before deployment
cdk diff

# Destroy the stack
cdk destroy
```

### Using the build script:
```bash
# Build, push, and deploy with CDK
../build_and_deploy.sh --use-cdk
```

## Stack Components

### Lambda Functions
- **biobayb_uh_uploader**: Processes UltraHuman sensor data from SNS messages
- **biobayb_uh_sns_publisher**: Publishes SNS messages to trigger data collection

### Supporting Resources
- **IAM Roles**: Lambda execution roles with appropriate permissions
- **CloudWatch Log Groups**: Centralized logging for Lambda functions
- **SNS Topics**: Inter-function communication
- **EventBridge Rules**: Scheduled execution and manual triggers

### Environment Variables
Functions are configured with environment variables for:
- UltraHuman API configuration
- Database and S3 bucket settings
- Project-specific parameters

## Configuration

### Environment Variables
Set these environment variables or CDK context values:
- `AWS_ACCOUNT`: AWS account ID (default: 509812589231)
- `AWS_REGION`: AWS region (default: us-east-1)

### Lambda Function Settings
- **Memory**: 1024MB - 3008MB depending on function
- **Timeout**: 10-15 minutes
- **Architecture**: x86_64
- **Runtime**: Docker container from ECR

## Monitoring

### CloudWatch Logs
- Log groups are automatically created for each Lambda function
- Retention period: 30 days
- Log group names: `/aws/lambda/{function_name}`

### Dead Letter Queues
- Enabled for failed Lambda executions
- Retry attempts: 2

## Scheduled Execution

### SNS Publisher
- Runs daily at 6:00 AM UTC
- Triggered by EventBridge rule
- Publishes messages for data collection

### Manual Triggers
- Custom EventBridge pattern for manual execution
- Source: `sensorfabric.manual`
- Detail type: `UltraHuman Data Upload Request`

## Troubleshooting

### Common Issues
1. **ECR Image Not Found**: Ensure Docker images are built and pushed to ECR
2. **Permission Errors**: Check IAM roles and policies
3. **Timeout Issues**: Increase Lambda timeout or optimize code
4. **Memory Errors**: Increase Lambda memory allocation

### Debugging
```bash
# View CloudFormation events
aws cloudformation describe-stack-events --stack-name SensorFabricLambdaStack

# Check Lambda function logs
aws logs tail /aws/lambda/biobayb_uh_uploader --follow

# Test Lambda function
aws lambda invoke --function-name biobayb_uh_uploader /tmp/response.json
```