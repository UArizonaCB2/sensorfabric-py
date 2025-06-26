import json
import os
import datetime
from typing import Dict, List, Any, Optional
import logging
import traceback
import awswrangler as wr

from sensorfabric.needle import Needle
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
    AWS Lambda function for daily UltraHuman sensor data collection.
    
    This class handles:
    1. Fetching active participants from MDH
    2. Collecting daily UltraHuman sensor data for each participant
    3. Uploading parquet data to S3 in organized folder structure
    """
    
    def __init__(self):
        self.needle = None
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
        if self.database_name not in wr.catalog.databases():
            logger.info(f"Database {self.database_name} does not exist. Creating...")
            wr.catalog.create_database(self.database_name, exist_ok=True)
            logger.info(f"Created database: {self.database_name}")

    def _initialize_connections(self):
        """Initialize MDH and Ultrahuman API connections."""
        try:
            # Initialize MDH connection via Needle
            mdh_configuration = {
                'account_secret': os.environ.get('MDH_SECRET_KEY'),
                'account_name': os.environ.get('MDH_ACCOUNT_NAME'),
                'project_id': os.environ.get('MDH_PROJECT_ID'),
                'project_name': os.environ.get('MDH_PROJECT_NAME', DEFAULT_PROJECT_NAME),
            }
            self.needle = Needle(method='mdh', mdh_configuration=mdh_configuration)
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

    def _get_active_participants(self) -> List[Dict[str, Any]]:
        """Fetch active participants from MDH."""
        try:
            participants_data = self.needle.mdh.getAllParticipants()
            active_participants = []
            
            for participant in participants_data.get('participants', []):
                # Filter for active participants
                if participant.get('enrolled'):
                    active_participants.append(participant)
            
            logger.info(f"Found {len(active_participants)} active participants")
            return active_participants

        except Exception as e:
            logger.error(f"Failed to fetch participants: {str(e)}")
            raise

    def _collect_and_upload_participant_data(self, participant: Dict[str, Any]) -> Dict[str, Any]:
        self._check_create_database()
        """Collect and upload UltraHuman data for a single participant."""
        participant_id = participant.get('participantIdentifier')
        customFields = participant.get('customFields', {})
        demographics = participant.get('demographics', {})
        demographicsEmail = demographics.get('email', None)
        accountEmail = participant.get('accountEmail', None)
        customEmail = customFields.get('uh_email', None)
        email = None

        if customEmail is not None and len(customEmail) > 0:
            email = customEmail
        elif demographicsEmail is not None and len(demographicsEmail) > 0:
            email = demographicsEmail
        elif accountEmail is not None and len(accountEmail) > 0:
            email = accountEmail

        # default to phoenix timezone if no tz set
        timezone = customFields.get('timeZone', 'America/Phoenix')
        if not email:
            logger.warning(f"No email found for participant {participant_id}")
            return {'participant_id': participant_id, 'success': False, 'error': 'No email found'}
        
        record_count = 0
        try:
            # Get DataFrame for this participant and date
            json_obj = self.uh_api.get_metrics(email, self.target_date)
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
                flattened = flatten_json_to_columns(metric, fill=True)
                converted = convert_dict_timestamps(flattened, timezone)
                try:
                    validate_sensor_data_schema(converted)
                    obj_values = converted.get('object_values', None)
                    obj_total = converted.get('object_total', None)
                    obj_values_value = converted.get('object_values_value', None)

                    if obj_values is None and obj_total is None and obj_values_value is None:
                        logger.error(f"Empty sensor data for participant {participant_id}, metric {metric_type}")
                        continue

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
                        path=f"s3://{self.data_bucket}/dataset/{participant_id}/{metric_type}/",
                        dataset=True,
                        database=self.database_name,
                        table=participant_id,
                        s3_additional_kwargs={
                            'Metadata': {
                                'participant_id': participant_id,
                                'participant_email': email,
                                'data_date': self.target_date,
                                'data_type': 'ultrahuman_metrics',
                                'metric_type': metric_type,
                                'upload_timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                'record_count': str(len(df))
                            }
                        },
                        mode='append',
                    )
                    record_count += len(df)

            logger.info(f"Successfully uploaded data for participant {participant_id}")

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
    
    def collect_daily_data(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Main orchestration method for collecting daily UltraHuman data.
        
        Args:
            target_date: Optional date string (YYYY-MM-DD) to collect data for specific date
            
        Returns:
            Dictionary with collection results and statistics
        """
        try:
            # Initialize connections
            self._initialize_connections()
            
            # Set target date
            self._set_target_date(target_date)
            
            # Get active participants
            participants = self._get_active_participants()
            
            if not participants:
                return {
                    'success': True,
                    'message': 'No active participants found',
                    'target_date': self.target_date,
                    'participants_processed': 0,
                    'successful_uploads': 0,
                    'failed_uploads': 0
                }
            
            # Collect and upload data for each participant
            results = []
            successful_uploads = 0
            failed_uploads = 0
            total_data_size = 0
            
            for participant in participants:
                result = self._collect_and_upload_participant_data(participant)
                results.append(result)
                
                if result['success']:
                    successful_uploads += 1
                    total_data_size += result.get('record_count', 0)
                else:
                    failed_uploads += 1
            
            return {
                'success': True,
                'message': f'Daily data collection completed for {self.target_date}',
                'target_date': self.target_date,
                'participants_processed': len(participants),
                'successful_uploads': successful_uploads,
                'failed_uploads': failed_uploads,
                'total_records_uploaded': total_data_size,
                'results': results
            }
            
        except Exception as e:
            logger.error(f"Daily data collection failed: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': str(e),
                'message': 'Daily data collection failed'
            }


def lambda_handler(event, context):
    """
    AWS Lambda entry point for UltraHuman data collection.
    
    Expected event structure:
    {
        "target_date": "2023-12-15"  # Optional: specific date to collect data for
    }
    
    Environment variables required:
    - SF_DATA_BUCKET: S3 bucket for data storage
    - MDH_SECRET: MyDataHelps account secret
    - MDH_ACC_NAME: MyDataHelps account name
    - MDH_PROJ_NAME: MyDataHelps project name
    - MDH_PROJ_ID: MyDataHelps project ID
    - UH_ENVIRONMENT: Ultrahuman environment ('development' or 'production')
    - UH_PROD_API_KEY: Ultrahuman production API key (if using production)
    - UH_PROD_BASE_URL: Ultrahuman production base URL (if using production)
    """
    
    logger.info(f"UltraHuman data collection Lambda started with event: {json.dumps(event)}")
    
    try:
        uploader = UltrahumanDataUploader()
        
        # Extract target date from event if provided
        target_date = event.get('target_date', None)
        
        # Collect the daily data
        result = uploader.collect_daily_data(target_date)
        
        # Prepare Lambda response
        response = {
            'statusCode': 200 if result['success'] else 500,
            'body': json.dumps(result),
            'headers': {
                'Content-Type': 'application/json'
            }
        }
        
        logger.info(f"UltraHuman data collection completed: {json.dumps(result)}")
        return response
        
    except Exception as e:
        error_message = f"UltraHuman data collection Lambda failed: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e),
                'message': 'UltraHuman data collection Lambda execution failed'
            }),
            'headers': {
                'Content-Type': 'application/json'
            }
        }


# Convenience function for local testing
def test_locally(target_date: Optional[str] = None):
    """
    Function to test the UltraHuman data collection pipeline locally.
    
    Args:
        target_date: Optional date string (YYYY-MM-DD) to collect data for specific date
    """
    # Mock event for local testing
    event = {}
    if target_date:
        event['target_date'] = target_date
    
    # Mock context object
    class MockContext:
        def __init__(self):
            self.function_name = 'ultrahuman-data-uploader-local-test'
            self.aws_request_id = 'local-test-123'
    
    context = MockContext()
    
    # Run the lambda handler
    response = lambda_handler(event, context)
    
    print("Response:")
    print(json.dumps(json.loads(response['body']), indent=2))
    
    return response


if __name__ == "__main__":
    # For local testing
    test_locally()
