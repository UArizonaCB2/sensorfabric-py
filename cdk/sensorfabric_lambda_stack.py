from typing import Dict, Any
import aws_cdk as cdk
from aws_cdk import (
    aws_lambda as lambda_,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_logs as logs,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    aws_sqs as sqs,
    aws_events as events,
    aws_events_targets as targets,
    Duration,
    Stack,
    RemovalPolicy
)
from constructs import Construct


class SensorFabricLambdaStack(Stack):
    """
    CDK Stack for SensorFabric Lambda functions using Docker containers.
    
    This stack creates:
    - Lambda functions from ECR container images
    - IAM roles and policies
    - CloudWatch log groups
    - SNS topics for inter-function communication
    - EventBridge rules for scheduling
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Configuration
        self.ecr_registry = "509812589231.dkr.ecr.us-east-1.amazonaws.com"
        self.ecr_repository = "uh-biobayb"
        self.project_name = "uh-biobayb-dev"
        self.database_name = "uh-biobayb-dev"
        self.sns_topic_name = "mdh_uh_sync"
        self.aws_secret_name = "prod/biobayb/uh/keys"
        self.sf_data_bucket = "uoa-biobayb-uh-dev"
        self.uh_environment = "production"
        self.lambda_functions = {}
        # Environment variables are now properly configured:
        # biobayb_uh_sns_publisher: AWS_SECRET_NAME, UH_DLQ_URL, UH_SNS_TOPIC_ARN
        # biobayb_uh_uploader: SF_DATA_BUCKET, UH_ENVIRONMENT, AWS_SECRET_NAME
        # Both functions have access to AWS Secrets Manager secret 'prod/biobayb/uh/keys'

        # lambda configs (environment variables will be updated after resource creation)
        self.lambda_config = {
            "biobayb_uh_uploader": {
                "description": "UltraHuman data uploader Lambda function",
                "timeout": Duration.minutes(15),
                "memory_size": 3008,
                "environment": {
                    "UH_ENVIRONMENT": self.uh_environment,
                    "SF_DATA_BUCKET": self.sf_data_bucket,
                    "AWS_SECRET_NAME": self.aws_secret_name
                }
            },
            "biobayb_uh_sns_publisher": {
                "description": "UltraHuman SNS publisher Lambda function",
                "timeout": Duration.minutes(10),
                "memory_size": 1024,
                "environment": {
                    "AWS_SECRET_NAME": self.aws_secret_name,
                    "UH_ENVIRONMENT": self.uh_environment
                }
            }
        }

        # Create ECR repository reference
        self.ecr_repo = ecr.Repository.from_repository_name(
            self, "SensorFabricECRRepo", 
            repository_name=self.ecr_repository
        )

        # Create IAM roles
        self.create_iam_roles()
        
        # Create SNS topics and subscriptions
        self.create_sns_resources()
        
        # Create SQS resources
        self.create_sqs_resources()
        
        # Create Lambda functions (after SNS/SQS to reference ARNs)
        self.create_lambda_functions()

        self.subscribe_sns_to_lambda()

        # Create EventBridge rules for scheduling
        self.create_eventbridge_rules()

    def create_iam_roles(self) -> None:
        """Create IAM roles for Lambda functions."""
        
        # Base Lambda execution role
        self.lambda_execution_role = iam.Role(
            self, f"{self.project_name}_LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole")
            ]
        )

        # Additional policies for SensorFabric operations
        sensorfabric_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                # S3 permissions for data storage
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject",
                "s3:ListBucket",
                
                # Athena permissions for query execution
                "athena:StartQueryExecution",
                "athena:GetQueryExecution",
                "athena:GetQueryResults",
                "athena:StopQueryExecution",
                "athena:GetWorkGroup",
                
                # Glue permissions for data catalog
                "glue:GetDatabase",
                "glue:CreateDatabase",
                "glue:GetTable",
                "glue:GetPartitions",
                "glue:CreateTable",
                "glue:UpdateTable",
                "glue:CreatePartition",
                "glue:BatchCreatePartition",
                "glue:GetDatabases",
                "glue:GetTables",
                
                # SNS permissions for messaging
                "sns:Publish",
                "sns:Subscribe",
                "sns:Unsubscribe",
                "sns:ListTopics",
                "sns:GetTopicAttributes",
                
                # CloudWatch permissions for monitoring
                "cloudwatch:PutMetricData",
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
                
                # SQS permissions for dead letter queue
                "sqs:SendMessage",
                "sqs:ReceiveMessage",
                "sqs:DeleteMessage",
                "sqs:GetQueueAttributes"
            ],
            resources=["*"]
        )
        
        # Secrets Manager policy for accessing UltraHuman keys
        secrets_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret"
            ],
            resources=[
                f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:{self.aws_secret_name}*"
            ]
        )

        self.lambda_execution_role.add_to_policy(sensorfabric_policy)
        self.lambda_execution_role.add_to_policy(secrets_policy)

    def create_lambda_functions(self) -> None:
        """Create Lambda functions from ECR container images."""

        for function_name, config in self.lambda_config.items():
            # Create CloudWatch Log Group
            log_group = logs.LogGroup(
                self, f"{self.project_name}_{function_name}_LogGroup",
                log_group_name=f"/aws/lambda/{function_name}",
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=RemovalPolicy.DESTROY
            )

            # Create Lambda function
            lambda_function = lambda_.DockerImageFunction(
                self, f"{self.project_name}_{function_name}_Lambda",
                function_name=function_name,
                description=config["description"],
                code=lambda_.DockerImageCode.from_ecr(
                    repository=self.ecr_repo,
                    tag=function_name
                ),
                role=self.lambda_execution_role,
                timeout=config["timeout"],
                memory_size=config["memory_size"],
                environment=config["environment"],
                log_group=log_group,
                
                # Container-specific settings
                architecture=lambda_.Architecture.X86_64,
                
                # Dead letter queue for failed executions
                dead_letter_queue_enabled=True,
                
                # Retry configuration
                retry_attempts=2
            )

            self.lambda_functions[function_name] = lambda_function

            # Output the Lambda function ARN
            cdk.CfnOutput(
                self, f"{self.project_name}_{function_name}_Lambda_ARN",
                value=lambda_function.function_arn,
                description=f"ARN for {self.project_name}_{function_name} Lambda function"
            )
        
        # Add dynamic environment variables after all resources are created
        self.update_lambda_environment_variables()

    def create_sns_resources(self) -> None:
        """Create SNS topics for inter-function communication."""
        
        # Topic for UltraHuman data collection requests
        self.uh_data_collection_topic = sns.Topic(
            self, "UHDataCollectionTopic",
            topic_name=self.sns_topic_name,
            display_name="UltraHuman Data Collection Topic",
        )

        # Output SNS topic ARN
        cdk.CfnOutput(
            self, "UHDataCollectionTopicARN",
            value=self.uh_data_collection_topic.topic_arn,
            description="ARN for UltraHuman data collection SNS topic"
        )

    def subscribe_sns_to_lambda(self) -> None:
        """
        Subscribe the uploader Lambda to the topic and grant publish permissions to the publisher Lambda.
        To be run after lambdas are created.
        """
        # Subscribe the uploader Lambda to the topic
        if "biobayb_uh_uploader" in self.lambda_functions:
            self.uh_data_collection_topic.add_subscription(
                subscriptions.LambdaSubscription(self.lambda_functions["biobayb_uh_uploader"])
            )

        # Grant publish permissions to the publisher Lambda
        if "biobayb_uh_sns_publisher" in self.lambda_functions:
            self.uh_data_collection_topic.grant_publish(
                self.lambda_functions["biobayb_uh_sns_publisher"]
            )

    def create_sqs_resources(self) -> None:
        """Create SQS resources for dead letter queues."""
        
        # Dead letter queue for SNS publisher
        self.uh_dlq = sqs.Queue(
            self, "UHPublisherDLQ",
            queue_name="biobayb_uh_undeliverable",
            visibility_timeout=Duration.seconds(300),
            retention_period=Duration.days(14),
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # Output DLQ ARN
        cdk.CfnOutput(
            self, "UHPublisherDLQARN",
            value=self.uh_dlq.queue_arn,
            description="ARN for UltraHuman publisher dead letter queue"
        )

    def create_eventbridge_rules(self) -> None:
        """Create EventBridge rules for scheduled Lambda executions."""
        
        # Schedule for SNS publisher (runs daily at midnight AZ time UTC-7)
        if "biobayb_uh_sns_publisher" in self.lambda_functions:
            publisher_rule = events.Rule(
                self, f"{self.project_name}_UHPublisherScheduleRule",
                description="Schedule for UltraHuman SNS publisher",
                schedule=events.Schedule.cron(
                    minute="0",
                    hour="7",
                    day="*",
                    month="*",
                    year="*"
                )
            )
            
            publisher_rule.add_target(
                targets.LambdaFunction(self.lambda_functions["biobayb_uh_sns_publisher"])
            )

        # Manual trigger capability for uploader
        if "biobayb_uh_uploader" in self.lambda_functions:
            # This creates a custom event pattern that can be triggered manually
            uploader_rule = events.Rule(
                self, f"{self.project_name}_UHUploaderManualTriggerRule",
                description="Manual trigger for UltraHuman data uploader",
                event_pattern=events.EventPattern(
                    source=["sensorfabric.manual"],
                    detail_type=["UltraHuman Data Upload Request"]
                )
            )
            
            uploader_rule.add_target(
                targets.LambdaFunction(self.lambda_functions["biobayb_uh_uploader"])
            )

    def update_lambda_environment_variables(self) -> None:
        """Update Lambda functions with dynamic environment variables."""
        
        # Add SNS topic ARN and DLQ URL to SNS publisher
        if "biobayb_uh_sns_publisher" in self.lambda_functions:
            publisher_lambda = self.lambda_functions["biobayb_uh_sns_publisher"]
            publisher_lambda.add_environment("UH_SNS_TOPIC_ARN", self.uh_data_collection_topic.topic_arn)
            publisher_lambda.add_environment("UH_DLQ_URL", self.uh_dlq.queue_url)
