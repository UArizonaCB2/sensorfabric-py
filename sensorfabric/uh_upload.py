import json
import boto3
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging
import traceback
import awswrangler as wr

from sensorfabric.needle import Needle
from sensorfabric.uh import UltrahumanAPI

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

class UltrahumanDataUploader:
    """
    AWS Lambda function for daily UltraHuman sensor data collection.
    
    This class handles:
    1. Fetching active participants from MDH
    2. Collecting daily UltraHuman sensor data for each participant
    3. Uploading parquet data to S3 in organized folder structure
    """
    
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.needle = None
        self.uh_api = None
        
        # S3 configuration from environment variables
        self.data_bucket = os.environ.get('SF_DATA_BUCKET')
        
        if not self.data_bucket:
            raise ValueError("SF_DATA_BUCKET environment variable must be set")
        
        # Date configuration
        self.target_date = None
        
    def _initialize_connections(self):
        """Initialize MDH and Ultrahuman API connections."""
        try:
            # Initialize MDH connection via Needle
            self.needle = Needle(method='mdh')
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
        if target_date:
            self.target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
        else:
            # Default to yesterday to ensure data is available
            self.target_date = (datetime.now() - timedelta(days=1)).date()
        
        logger.info(f"Collecting data for date: {self.target_date}")
    
    def _get_active_participants(self) -> List[Dict[str, Any]]:
        """Fetch active participants from MDH."""
        try:
            participants_data = self.needle.mdh.getAllParticipants()
            active_participants = []
            
            for participant in participants_data.get('participants', []):
                # Filter for active participants
                if participant.get('status') == 'active':
                    active_participants.append(participant)
            
            logger.info(f"Found {len(active_participants)} active participants")
            return active_participants
            
        except Exception as e:
            logger.error(f"Failed to fetch participants: {str(e)}")
            raise
    
    def _collect_and_upload_participant_data(self, participant: Dict[str, Any]) -> Dict[str, Any]:
        """Collect and upload UltraHuman data for a single participant."""
        participant_id = participant.get('identifier')
        email = participant.get('customFields', {}).get('email')
        
        if not email:
            logger.warning(f"No email found for participant {participant_id}")
            return {'participant_id': participant_id, 'success': False, 'error': 'No email found'}
        
        date_str = self.target_date.strftime('%Y-%m-%d')
        
        try:
            # Get DataFrame for this participant and date
            df = self.uh_api.get_metrics_as_dataframe(email, date_str)
            
            if df.empty:
                logger.warning(f"No data available for participant {participant_id} on {date_str}")
                return {
                    'participant_id': participant_id,
                    'success': False,
                    'error': 'No data available for this date'
                }
            
            # Create S3 path with organized folder structure
            s3_path = f"s3://{self.data_bucket}/ultrahuman-data/participants/{participant_id}/{self.target_date.strftime('%Y/%m/%d')}.parquet"
            
            # Add additional metadata columns
            df['participant_id'] = participant_id
            df['upload_timestamp'] = datetime.utcnow().isoformat()
            df['data_type'] = 'ultrahuman_metrics'
            
            # Upload to S3 using awswrangler with metadata
            wr.s3.to_parquet(
                df=df,
                path=s3_path,
                index=False,
                dataset=False,
                s3_additional_kwargs={
                    'Metadata': {
                        'participant_id': participant_id,
                        'participant_email': email,
                        'data_date': date_str,
                        'data_type': 'ultrahuman_metrics',
                        'upload_timestamp': datetime.utcnow().isoformat(),
                        'record_count': str(len(df))
                    }
                }
            )
            
            logger.info(f"Successfully uploaded data for participant {participant_id}: {s3_path}")
            
            return {
                'participant_id': participant_id,
                'success': True,
                's3_path': s3_path,
                'record_count': len(df),
                'columns': list(df.columns)
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
                    'date': self.target_date.isoformat(),
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
                    total_data_size += result.get('data_size', 0)
                else:
                    failed_uploads += 1
            
            return {
                'success': True,
                'message': f'Daily data collection completed for {self.target_date}',
                'date': self.target_date.isoformat(),
                'participants_processed': len(participants),
                'successful_uploads': successful_uploads,
                'failed_uploads': failed_uploads,
                'total_data_size_bytes': total_data_size,
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
        target_date = event.get('target_date')
        
        # Collect the daily data
        result = uploader.collect_daily_data(target_date)
        
        # Prepare Lambda response
        response = {
            'statusCode': 200 if result['success'] else 500,
            'body': json.dumps(result, indent=2),
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
