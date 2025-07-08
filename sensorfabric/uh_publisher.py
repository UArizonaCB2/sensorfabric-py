import json
import os
import datetime
from typing import Dict, List, Any, Optional
import logging
import traceback
import boto3
from botocore.exceptions import ClientError

from sensorfabric.needle import Needle

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_PROJECT_NAME = 'uh-biobayb-dev'


class UltrahumanSNSPublisher:
    """
    AWS Lambda function for publishing UltraHuman data collection requests via SNS.
    
    This class handles:
    1. Fetching active participants from MDH via Needle
    2. Publishing SNS messages for each participant to trigger data collection
    3. Dead letter queue handling for failed message publishing
    """
    
    def __init__(self):
        self.needle = None
        self.sns_client = None
        
        # SNS configuration from environment variables
        self.sns_topic_arn = os.environ.get('UH_SNS_TOPIC_ARN')
        self.dead_letter_queue_url = os.environ.get('UH_DLQ_URL')
        
        # Validate required environment variables
        if not self.sns_topic_arn:
            raise ValueError("UH_SNS_TOPIC_ARN environment variable must be set")
        
        # Date configuration
        self.target_date = None
        
        # Initialize AWS clients
        self.sns_client = boto3.client('sns')
        self.sqs_client = boto3.client('sqs') if self.dead_letter_queue_url else None

    def _initialize_connections(self):
        """Initialize MDH connection via Needle."""
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
            
        except Exception as e:
            logger.error(f"Failed to initialize MDH connection: {str(e)}")
            raise

    def _set_target_date(self, target_date: Optional[str] = None):
        """Set the target date for data collection."""
        if not target_date:
            # Default to yesterday to ensure data is available
            self.target_date = datetime.datetime.strftime(
                (datetime.datetime.now() - datetime.timedelta(days=1)), 
                '%Y-%m-%d'
            )
        else:
            self.target_date = target_date

        logger.info(f"Target date set to: {self.target_date}")

    def _get_active_participants(self) -> List[Dict[str, Any]]:
        """Fetch active participants from MDH."""
        try:
            participants_data = self.needle.mdh.getAllParticipants()
            active_participants = []
            
            for participant in participants_data.get('participants', []):
                # Filter for active participants
                custom_fields = participant.get('customFields', {})
                last_sync_date = custom_fields.get('uh_sync_date', None)
                # check last sync date to make sure we don't oversync
                if last_sync_date is None:
                    continue
                if participant.get('enrolled'):
                    active_participants.append(participant)

            logger.info(f"Found {len(active_participants)} active participants")
            return active_participants

        except Exception as e:
            # TODO maybe send a message to dead letter queue?
            logger.error(f"Failed to fetch participants: {str(e)}")
            raise

    def _extract_participant_email(self, participant: Dict[str, Any]) -> Optional[str]:
        """Extract email from participant data with fallback logic."""
        custom_fields = participant.get('customFields', {})
        demographics = participant.get('demographics', {})
        
        # Priority order: custom uh_email, demographics email, account email
        custom_email = custom_fields.get('uh_email')
        demographics_email = demographics.get('email')
        account_email = participant.get('accountEmail')
        
        if custom_email and len(custom_email) > 0:
            return custom_email
        elif demographics_email and len(demographics_email) > 0:
            return demographics_email
        elif account_email and len(account_email) > 0:
            return account_email
        
        return None

    def _publish_sns_message(self, participant: Dict[str, Any]) -> Dict[str, Any]:
        """Publish SNS message for a single participant."""
        participant_id = participant.get('participantIdentifier')
        email = self._extract_participant_email(participant)
        
        if not email:
            logger.warning(f"No email found for participant {participant_id}")
            return {
                'participant_id': participant_id,
                'success': False,
                'error': 'No email found for participant'
            }
        
        # Extract timezone from custom fields
        custom_fields = participant.get('customFields', {})
        timezone = custom_fields.get('timeZone', 'America/Phoenix')
        
        # Create SNS message payload
        message_data = {
            'participant_id': participant_id,
            'email': email,
            'target_date': self.target_date,
            'timezone': timezone,
            'custom_fields': custom_fields
        }
        
        try:
            # Publish message to SNS topic
            response = self.sns_client.publish(
                TopicArn=self.sns_topic_arn,
                Message=json.dumps(message_data),
                Subject=f'UltraHuman Data Collection Request - {participant_id}',
                MessageAttributes={
                    'participant_id': {
                        'DataType': 'String',
                        'StringValue': participant_id
                    },
                    'target_date': {
                        'DataType': 'String',
                        'StringValue': self.target_date
                    },
                    'operation': {
                        'DataType': 'String',
                        'StringValue': 'uh_data_collection'
                    }
                }
            )
            
            logger.info(f"Successfully published SNS message for participant {participant_id}")
            return {
                'participant_id': participant_id,
                'success': True,
                'message_id': response['MessageId'],
                'email': email
            }
            
        except ClientError as e:
            error_msg = f"Failed to publish SNS message for participant {participant_id}: {str(e)}"
            logger.error(error_msg)
            
            # Send to dead letter queue if available
            if self.dead_letter_queue_url:
                self._send_to_dead_letter_queue(participant, error_msg)
            
            return {
                'participant_id': participant_id,
                'success': False,
                'error': error_msg
            }
        except Exception as e:
            error_msg = f"Unexpected error publishing SNS message for participant {participant_id}: {str(e)}"
            logger.error(error_msg)
            
            # Send to dead letter queue if available
            if self.dead_letter_queue_url:
                self._send_to_dead_letter_queue(participant, error_msg)
            
            return {
                'participant_id': participant_id,
                'success': False,
                'error': error_msg
            }

    def _send_to_dead_letter_queue(self, participant: Dict[str, Any], error_message: str):
        """Send failed participant data to dead letter queue."""
        if not self.sqs_client or not self.dead_letter_queue_url:
            logger.warning("Dead letter queue not configured, skipping DLQ send")
            return
        
        try:
            dlq_message = {
                'participant_data': participant,
                'target_date': self.target_date,
                'error_message': error_message,
                'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'operation': 'uh_sns_publish_failed'
            }
            
            self.sqs_client.send_message(
                QueueUrl=self.dead_letter_queue_url,
                MessageBody=json.dumps(dlq_message),
                MessageAttributes={
                    'participant_id': {
                        'DataType': 'String',
                        'StringValue': participant.get('participantIdentifier', 'unknown')
                    },
                    'error_type': {
                        'DataType': 'String',
                        'StringValue': 'sns_publish_failed'
                    }
                }
            )
            
            logger.info(f"Sent failed participant {participant.get('participantIdentifier')} to dead letter queue")
            
        except Exception as e:
            logger.error(f"Failed to send message to dead letter queue: {str(e)}")

    def publish_participant_messages(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Main orchestration method for publishing SNS messages for all active participants.
        
        Args:
            target_date: Optional date string (YYYY-MM-DD) for data collection
            
        Returns:
            Dictionary with publishing results and statistics
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
                    'successful_publishes': 0,
                    'failed_publishes': 0,
                    'results': []
                }
            
            # Publish SNS messages for each participant
            results = []
            successful_publishes = 0
            failed_publishes = 0
            success_participants = []
            for participant in participants:
                result = self._publish_sns_message(participant)
                results.append(result)
                if result['success']:
                    successful_publishes += 1
                    success_participants.append({
                        'participantIdentifier': participant.get('participantIdentifier'),
                        'customFields': {'uh_sync_date': self.target_date}
                    })
                else:
                    failed_publishes += 1
            
            # Update participants in MDH
            mdh_result = self.needle.update_participants(success_participants)

            return {
                'success': True,
                'message': f'SNS message publishing completed for {self.target_date}',
                'target_date': self.target_date,
                'participants_processed': len(participants),
                'successful_publishes': successful_publishes,
                'failed_publishes': failed_publishes,
                'mdh_result': mdh_result,
                'results': results
            }
            
        except Exception as e:
            logger.error(f"SNS message publishing failed: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': str(e),
                'message': 'SNS message publishing failed'
            }


def lambda_handler(event, context):
    """
    AWS Lambda entry point for publishing UltraHuman data collection requests via SNS.
    
    Expected event structure:
    {
        "target_date": "2023-12-15"  # Optional: specific date to collect data for
    }
    
    Environment variables required:
    - UH_SNS_TOPIC_ARN: SNS topic ARN for publishing messages
    - UH_DLQ_URL: SQS queue URL for dead letter messages (optional)
    - MDH_SECRET_KEY: MyDataHelps account secret
    - MDH_ACCOUNT_NAME: MyDataHelps account name
    - MDH_PROJECT_NAME: MyDataHelps project name
    - MDH_PROJECT_ID: MyDataHelps project ID
    """
    
    logger.info(f"UltraHuman SNS Publisher Lambda started with event: {json.dumps(event)}")
    
    try:
        publisher = UltrahumanSNSPublisher()
        
        # Extract target date from event if provided
        target_date = event.get('target_date', None)
        
        # Publish messages for all participants
        result = publisher.publish_participant_messages(target_date)
        
        # Prepare Lambda response
        response = {
            'statusCode': 200 if result['success'] else 500,
            'body': json.dumps(result),
            'headers': {
                'Content-Type': 'application/json'
            }
        }
        
        logger.info(f"UltraHuman SNS Publisher completed: {json.dumps(result)}")
        return response
        
    except Exception as e:
        error_message = f"UltraHuman SNS Publisher Lambda failed: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e),
                'message': 'UltraHuman SNS Publisher Lambda execution failed'
            }),
            'headers': {
                'Content-Type': 'application/json'
            }
        }


# Convenience function for local testing
def test_locally(target_date: Optional[str] = None):
    """
    Function to test the UltraHuman SNS Publisher pipeline locally.
    
    Args:
        target_date: Optional date string (YYYY-MM-DD) for data collection
    """
    # Mock event for local testing
    event = {}
    if target_date:
        event['target_date'] = target_date
    
    # Mock context object
    class MockContext:
        def __init__(self):
            self.function_name = 'ultrahuman-sns-publisher-local-test'
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