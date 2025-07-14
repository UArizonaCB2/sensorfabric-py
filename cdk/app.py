#!/usr/bin/env python3

import aws_cdk as cdk
from sensorfabric_lambda_stack import SensorFabricLambdaStack

app = cdk.App()

# Get environment variables or use defaults
account = app.node.try_get_context("account") or "509812589231"
region = app.node.try_get_context("region") or "us-east-1"

# Create the Lambda stack
SensorFabricLambdaStack(
    app, 
    "SensorFabricLambdaStack",
    env=cdk.Environment(account=account, region=region),
    description="SensorFabric Lambda functions deployed via Docker containers"
)

app.synth()