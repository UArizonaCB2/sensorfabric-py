import json
import os
import datetime
from typing import Dict, List, Any, Optional
import logging
import traceback
import awswrangler as wr
import boto3
from sensorfabric.mdh import MDH
from sensorfabric.uh import UltrahumanAPI
from sensorfabric.utils import flatten_json_to_columns, convert_dict_timestamps, validate_sensor_data_schema
import pandas as pd
import jsonschema


# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_DATABASE_NAME = 'uh-biobayb-dev'
DEFAULT_DATA_BUCKET = 'uoa-biobayb-uh-dev'
DEFAULT_PROJECT_NAME = 'uh-biobayb-dev'


class UltrahumanDataUploader:
    """
    AWS Lambda function for SNS-driven UltraHuman sensor data collection.
    
    This class handles:
    1. Processing SNS messages containing participant data
    2. Collecting UltraHuman sensor data for specified participants
    3. Uploading parquet data to S3 in organized folder structure
    4. Updating participant sync dates in MDH
    """
    
    def __init__(self):
        self.mdh = None
        self.uh_api = None

        # S3 configuration from environment variables
        self.data_bucket = os.environ.get('SF_DATA_BUCKET', DEFAULT_DATA_BUCKET)
        self.database_name = os.environ.get('SF_DATABASE_NAME', DEFAULT_DATABASE_NAME)
        # data bucket is required for upload. default to 
        if not self.data_bucket:
            raise ValueError("SF_DATA_BUCKET environment variable must be set")
        
        # Date configuration
        self.target_date = None

    def _check_create_database(self):
        logger.info(f"Checking for database: {self.database_name}")
        logger.info(wr.catalog.databases())
        if self.database_name not in wr.catalog.databases().values:
            logger.info(f"Database {self.database_name} does not exist. Creating...")
            wr.catalog.create_database(self.database_name, exist_ok=True)
            logger.info(f"Created database: {self.database_name}")

    def _initialize_connections(self):
        """Initialize MDH and Ultrahuman API connections."""
        try:
            # Initialize MDH connection
            mdh_configuration = {
                'account_secret': os.environ.get('MDH_SECRET_KEY'),
                'account_name': os.environ.get('MDH_ACCOUNT_NAME'),
                'project_id': os.environ.get('MDH_PROJECT_ID'),
            }
            self.mdh = MDH(**mdh_configuration)
            logger.info("MDH connection initialized successfully")
            
            # Initialize Ultrahuman API
            uh_environment = os.environ.get('UH_ENVIRONMENT', 'development')
            self.uh_api = UltrahumanAPI(environment=uh_environment)
            logger.info(f"Ultrahuman API initialized for {uh_environment} environment")
            
        except Exception as e:
            logger.error(f"Failed to initialize connections: {str(e)}")
            raise

    def _set_target_date(self, target_date: Optional[str] = None):
        """Set the target date for data collection."""
        if not target_date:
            # Default to yesterday to ensure data is available
            self.target_date = datetime.datetime.strftime((datetime.datetime.now() - datetime.timedelta(days=1)), '%Y-%m-%d')
        else:
            self.target_date = target_date

        logger.info(f"Collecting data for date: {self.target_date}")

    def _process_sns_message(self, sns_message: Dict[str, Any]) -> Dict[str, Any]:
        """Process SNS message to extract participant data.
        
        Args:
            sns_message: SNS message containing participant data
            
        Returns:
            Dict with participant data for UltraHuman collection
            
        Raises:
            ValueError: If required fields are missing
        """
        try:
            # Parse the SNS message body
            message_body = json.loads(sns_message.get('Message', '{}'))
            
            # Extract required fields
            participant_id = message_body.get('participant_id')
            email = message_body.get('email')
            target_date = message_body.get('target_date')
            
            # Validate required fields
            if not participant_id:
                raise ValueError("Missing required field: participant_id")
            if not email:
                raise ValueError("Missing required field: email")
            if not target_date:
                raise ValueError("Missing required field: target_date")
            
            # Extract optional fields with defaults
            timezone = message_body.get('timezone', 'America/Phoenix')
            custom_fields = message_body.get('custom_fields', {})
            
            participant_data = {
                'participantIdentifier': participant_id,
                'email': email,
                'target_date': target_date,
                'timezone': timezone,
                'customFields': custom_fields
            }
            
            logger.info(f"Processed SNS message for participant {participant_id}")
            return participant_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse SNS message JSON: {str(e)}")
            raise ValueError(f"Invalid JSON in SNS message: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to process SNS message: {str(e)}")
            raise

    def _collect_and_upload_participant_data(self, participant: Dict[str, Any]) -> Dict[str, Any]:
        self._check_create_database()
        """Collect and upload UltraHuman data for a single participant."""
        participant_id = participant.get('participantIdentifier')
        
        # For SNS-based processing, email and timezone come directly from message
        email = participant.get('accountEmail')
        demographics = participant.get('demographics', {})
        if 'email' in participant and participant.get('email') is not None and participant.get('email') != '':
            email = participant.get('email')
        if 'uh_email' in participant and participant.get('uh_email') is not None and participant.get('uh_email') != '':
            email = participant.get('uh_email')
        timezone = demographics.get('timeZone', 'America/Phoenix')
        
        # Use target_date from SNS message if available, otherwise use instance target_date
        target_date = participant.get('target_date', self.target_date)
        if not email:
            logger.warning(f"No email found for participant {participant_id}")
            return {'participant_id': participant_id, 'success': False, 'error': 'No email found'}
        
        record_count = 0
        try:
            # Get DataFrame for this participant and date
            json_obj = self.uh_api.get_metrics(email, target_date)
            # we may want to store the raw json file alongside the parquet files.
            # pull out UH keys -
            # response structure is {"data": {"metric_data": [{}]}
            data = json_obj.get('data', {})
            if type(data) == list:
                return {
                    'participant_id': participant_id,
                    'success': False,
                    'error': 'No data found'
                }
            metrics_data = data.get('metric_data', [])
            for metric in metrics_data:
                metric_type = metric.get('type') if type(metric) == dict else None
                if type(metric) == dict and 'object_values' in metric and len(metric['object_values']) <= 0:
                    # empty data.
                    continue
                flattened = flatten_json_to_columns(json_data=metric, participant_id=participant_id, fill=True)
                converted = convert_dict_timestamps(flattened, timezone)
                try:
                    obj_values = converted.get('object_values', None)
                    obj_total = converted.get('object_total', None)
                    obj_values_value = converted.get('object_values_value', None)

                    if obj_values is None and obj_total is None and obj_values_value is None:
                        logger.error(f"Empty sensor data for participant {participant_id}, metric {metric_type}")
                        continue

                    validate_sensor_data_schema(converted)
                except jsonschema.ValidationError as e:
                    logger.error(f"Sensor data validation failed for participant {participant_id}, metric {metric_type}: {e.message}")
                    continue
                # push data into dataframe and then s3 through the wrangler.
                df = pd.DataFrame.from_dict(converted, orient="columns")
                if df.empty:
                    continue
                else:
                    wr.s3.to_parquet(
                        df=df,
                        path=f"s3://{self.data_bucket}/raw/dataset/{metric_type}",
                        dataset=True,
                        database=self.database_name,
                        table=metric_type,
                        s3_additional_kwargs={
                            'Metadata': {
                                'participant_id': participant_id,
                                'participant_email': email,
                                'data_date': target_date,
                                'data_type': 'ultrahuman_metrics',
                                'metric_type': metric_type,
                                'upload_timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                'record_count': str(len(df))
                            }
                        },
                        partition_cols=['pid'],
                        mode='append',
                    )
                    record_count += len(df)

            logger.info(f"Successfully uploaded data for participant {participant_id}")
            
            # Update participant's sync date in MDH
            try:
                self._update_participant_sync_date(participant_id)
            except Exception as e:
                logger.warning(f"Failed to update sync date for participant {participant_id}: {str(e)}")
                # Don't fail the entire operation if sync date update fails

            return {
                'participant_id': participant_id,
                'success': True,
                'record_count': record_count,
            }
            
        except Exception as e:
            logger.error(f"Failed to collect/upload data for participant {participant_id}: {str(e)}")
            return {
                'participant_id': participant_id,
                'success': False,
                'error': str(e)
            }
    
    def _update_participant_sync_date(self, participant_id: str) -> None:
        """Update participant's uh_sync_date field in MDH.
        
        Args:
            participant_id: The participant identifier to update
            
        Raises:
            Exception: If update fails
        """
        try:
            # Generate current ISO8601 timestamp
            current_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
            # Update participant's custom field
            update_data = [
                {
                    participant_id : {
                        'customFields': {
                            'uh_sync_date': current_timestamp
                        }
                    }
                }
            ]
            
            # Use MDH API to update participant
            self.mdh.update_participants(update_data)
            
            logger.info(f"Updated uh_sync_date for participant {participant_id} to {current_timestamp}")
            
        except Exception as e:
            logger.error(f"Failed to update sync date for participant {participant_id}: {str(e)}")
            raise
    
    def process_sns_messages(self, sns_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process SNS messages containing participant data for UltraHuman collection.
        
        Args:
            sns_records: List of SNS records from Lambda event
            
        Returns:
            Dictionary with processing results and statistics
        """
        try:
            # Initialize connections
            self._initialize_connections()
            
            if not sns_records:
                return {
                    'success': True,
                    'message': 'No SNS records to process',
                    'participants_processed': 0,
                    'successful_uploads': 0,
                    'failed_uploads': 0
                }
            
            # Process each SNS message
            results = []
            successful_uploads = 0
            failed_uploads = 0
            total_data_size = 0
            
            for record in sns_records:
                try:
                    # Extract participant data from SNS message
                    participant_data = self._process_sns_message(record['Sns'])
                    
                    # Collect and upload data for this participant
                    result = self._collect_and_upload_participant_data(participant_data)
                    results.append(result)
                    
                    if result['success']:
                        successful_uploads += 1
                        total_data_size += result.get('record_count', 0)
                    else:
                        failed_uploads += 1
                        
                except Exception as e:
                    logger.error(f"Failed to process SNS record: {str(e)}")
                    failed_uploads += 1
                    results.append({
                        'participant_id': 'unknown',
                        'success': False,
                        'error': f'SNS processing error: {str(e)}'
                    })
            
            return {
                'success': True,
                'message': f'SNS message processing completed',
                'participants_processed': len(sns_records),
                'successful_uploads': successful_uploads,
                'failed_uploads': failed_uploads,
                'total_records_uploaded': total_data_size,
                'results': results
            }
            
        except Exception as e:
            logger.error(f"SNS message processing failed: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': str(e),
                'message': 'SNS message processing failed'
            }
    
    def collect_daily_data(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Legacy method for collecting daily UltraHuman data (scheduled mode).
        
        Args:
            target_date: Optional date string (YYYY-MM-DD) to collect data for specific date
            
        Returns:
            Dictionary with collection results and statistics
        """
        logger.warning("collect_daily_data is deprecated. Use process_sns_messages for SNS-based processing.")
        
        try:
            # Initialize connections
            self._initialize_connections()
            
            # Set target date
            self._set_target_date(target_date)
            
            return {
                'success': False,
                'message': 'Scheduled mode not supported. Use SNS-based processing.',
                'target_date': self.target_date,
                'participants_processed': 0,
                'successful_uploads': 0,
                'failed_uploads': 0
            }
            
        except Exception as e:
            logger.error(f"Legacy daily data collection failed: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': str(e),
                'message': 'Legacy daily data collection failed'
            }


def get_secret():
    """
    Uses secretmanager to fill in MDH secrets
    """
    secret_name = os.getenv("AWS_SECRET_NAME")
    region_name = os.getenv("AWS_REGION", "us-east-1")
    
    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )
    
    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            logger.error("The requested secret " + secret_name + " was not found")
        elif e.response['Error']['Code'] == 'InvalidRequestException':
            logger.error("The request was invalid due to: " + e.response['Error']['Message'])
        elif e.response['Error']['Code'] == 'InvalidParameterException':
            logger.error("The request had invalid params - " + e.response['Error']['Message'])
        elif e.response['Error']['Code'] == 'DecryptionFailure':
            logger.error("The requested secret can't be decrypted using the provided KMS key - " + e.response['Error']['Message'])
        elif e.response['Error']['Code'] == 'InternalServiceError':
            logger.error("The request was not processed because of an internal error. - " + e.response['Error']['Message'])
        raise e
    else:
        if 'SecretString' in get_secret_value_response:
            secret = get_secret_value_response['SecretString']
            return json.loads(secret)
        else:
            decoded_binary_secret = base64.b64decode(get_secret_value_response['SecretBinary'])
            return json.loads(decoded_binary_secret)


def lambda_handler(event, context):
    """
    AWS Lambda entry point for UltraHuman data collection via SNS.
    
    Expected event structure (SNS):
    {
        "Records": [
            {
                "EventSource": "aws:sns",
                "Sns": {
                    "Message": "{\"participant_id\": \"123\", \"email\": \"user@example.com\", \"target_date\": \"2023-12-15\", \"timezone\": \"America/Phoenix\"}"
                }
            }
        ]
    }
    
    Environment variables required:
    - SF_DATA_BUCKET: S3 bucket for data storage
    - UH_ENVIRONMENT: Environment to use ('development' or 'production').
    - AWS_SECRET_NAME: Name of the secret in AWS Secrets Manager
    Variables from SecretsManager:
    - MDH_SECRET_KEY: MyDataHelps account secret
    - MDH_ACCOUNT_NAME: MyDataHelps account name
    - MDH_PROJECT_NAME: MyDataHelps project name
    - MDH_PROJECT_ID: MyDataHelps project ID
    - UH_DEV_BASE_URL: Development base URL for UltraHuman API
    - UH_DEV_API_KEY: Development API key for UltraHuman API
    - UH_PROD_BASE_URL: Production base URL for UltraHuman API
    - UH_PROD_API_KEY: Production API key for UltraHuman API
    """
    
    logger.info(f"UltraHuman SNS data collection Lambda started with event: {json.dumps(event)}")

    # setup environment with secrets
    secrets = get_secret()
    # hoist to env
    for key, value in secrets.items():
        os.environ[key] = value

    try:
        uploader = UltrahumanDataUploader()
        
        # Check if this is an SNS event
        if 'Records' in event:
            # Process SNS records
            sns_records = [record for record in event['Records'] if record.get('EventSource') == 'aws:sns']
            
            if sns_records:
                result = uploader.process_sns_messages(sns_records)
            else:
                result = {
                    'success': False,
                    'message': 'No SNS records found in event',
                    'participants_processed': 0,
                    'successful_uploads': 0,
                    'failed_uploads': 0
                }
        else:
            # Legacy mode - log warning and return error
            logger.warning("Received non-SNS event. This Lambda now requires SNS events.")
            result = {
                'success': False,
                'message': 'This Lambda now requires SNS events. Legacy scheduled mode is deprecated.',
                'participants_processed': 0,
                'successful_uploads': 0,
                'failed_uploads': 0
            }
        
        # Prepare Lambda response
        response = {
            'statusCode': 200 if result['success'] else 500,
            'body': json.dumps(result),
            'headers': {
                'Content-Type': 'application/json'
            }
        }
        
        logger.info(f"UltraHuman SNS data collection completed: {json.dumps(result)}")
        return response
        
    except Exception as e:
        error_message = f"UltraHuman SNS data collection Lambda failed: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e),
                'message': 'UltraHuman SNS data collection Lambda execution failed'
            }),
            'headers': {
                'Content-Type': 'application/json'
            }
        }


# Convenience function for local testing
def test_locally(participant_id: str = "test_participant", email: str = "test@example.com", target_date: Optional[str] = None):
    """
    Function to test the UltraHuman SNS data collection pipeline locally.
    
    Args:
        participant_id: Test participant ID
        email: Test participant email
        target_date: Optional date string (YYYY-MM-DD) to collect data for specific date
    """
    # Set default target date if not provided
    if not target_date:
        target_date = datetime.datetime.strftime((datetime.datetime.now() - datetime.timedelta(days=1)), '%Y-%m-%d')
    
    # Mock SNS event for local testing
    event = {
        "Records": [
            {
                "EventSource": "aws:sns",
                "Sns": {
                    "Message": json.dumps({
                        "participant_id": participant_id,
                        "email": email,
                        "target_date": target_date,
                        "timezone": "America/Phoenix"
                    })
                }
            }
        ]
    }
    
    # Mock context object
    class MockContext:
        def __init__(self):
            self.function_name = 'ultrahuman-sns-uploader-local-test'
            self.aws_request_id = 'local-test-123'
    
    context = MockContext()
    
    # Run the lambda handler
    response = lambda_handler(event, context)
    
    print("Response:")
    print(json.dumps(json.loads(response['body']), indent=2))
    
    return response

# Legacy test function for backward compatibility
def test_locally_legacy(target_date: Optional[str] = None):
    """
    Legacy test function - now deprecated.
    
    Args:
        target_date: Optional date string (YYYY-MM-DD) to collect data for specific date
    """
    print("WARNING: test_locally_legacy is deprecated. Use test_locally() with SNS parameters.")
    
    # Mock legacy event
    event = {}
    if target_date:
        event['target_date'] = target_date
    
    # Mock context object
    class MockContext:
        def __init__(self):
            self.function_name = 'ultrahuman-data-uploader-legacy-test'
            self.aws_request_id = 'legacy-test-123'
    
    context = MockContext()
    
    # Run the lambda handler
    response = lambda_handler(event, context)
    
    print("Response:")
    print(json.dumps(json.loads(response['body']), indent=2))
    
    return response


if __name__ == "__main__":
    # For local testing with SNS
    test_locally()
