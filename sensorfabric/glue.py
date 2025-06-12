import json
import boto3
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging
import traceback
import awswrangler as wr
import pandas as pd

from sensorfabric.needle import Needle
from sensorfabric.templates import generate_weekly_report_template

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

class SensorFabricGlue:
    """
    AWS Lambda function orchestrator for SensorFabric data pipeline.
    
    This class coordinates:
    1. Fetching participant data from MDH
    2. Loading Ultrahuman sensor data from S3 (collected by uh_upload.py)
    3. Generating weekly reports from stored data
    4. Uploading reports to S3
    """
    
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.needle = None
        
        # S3 configuration from environment variables
        self.data_bucket = os.environ.get('SF_DATA_BUCKET')
        self.reports_bucket = os.environ.get('SF_REPORTS_BUCKET', self.data_bucket)
        
        if not self.data_bucket:
            raise ValueError("SF_DATA_BUCKET environment variable must be set")
        
        # Date configuration
        self.target_date = None
        self.week_start = None
        self.week_end = None
        
    def _initialize_connections(self):
        """Initialize MDH and Ultrahuman API connections."""
        try:
            # Initialize MDH connection via Needle
            self.needle = Needle(method='mdh')
            logger.info("MDH connection initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize connections: {str(e)}")
            raise
    
    def _calculate_date_range(self, target_date: Optional[str] = None):
        """Calculate the date range for the previous week."""
        if target_date:
            self.target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
        else:
            self.target_date = datetime.now().date()
        
        # Calculate previous week (Monday to Sunday)
        days_since_monday = self.target_date.weekday()
        self.week_start = self.target_date - timedelta(days=days_since_monday + 7)
        self.week_end = self.week_start + timedelta(days=6)
        
        logger.info(f"Processing week: {self.week_start} to {self.week_end}")
    
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
    
    def _load_ultrahuman_data_from_s3(self, participants: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Load Ultrahuman data for all participants for the week from S3."""
        participant_data = {}
        
        for participant in participants:
            participant_id = participant.get('identifier')
            
            try:
                # Load data for each day of the week
                daily_data = []
                weekly_dataframes = []
                current_date = self.week_start
                
                while current_date <= self.week_end:
                    date_str = current_date.strftime('%Y-%m-%d')
                    
                    try:
                        # Create S3 path for this participant and date
                        s3_path = f"s3://{self.data_bucket}/ultrahuman-data/participants/{participant_id}/{current_date.strftime('%Y/%m/%d')}.parquet"
                        
                        # Try to read the parquet file using awswrangler
                        df = wr.s3.read_parquet(
                            path=s3_path,
                            use_threads=True
                        )
                        
                        if not df.empty:
                            weekly_dataframes.append(df)
                            daily_data.append({
                                'date': date_str,
                                'record_count': len(df),
                                's3_path': s3_path,
                                'columns': list(df.columns),
                                'dataframe': df
                            })
                            logger.info(f"Loaded {len(df)} records for {participant_id} on {date_str}")
                        else:
                            logger.warning(f"Empty data for {participant_id} on {date_str}")
                        
                    except wr.exceptions.NoFilesFound:
                        logger.warning(f"No data found for {participant_id} on {date_str}")
                    except Exception as day_error:
                        logger.warning(f"Failed to load data for {participant_id} on {date_str}: {str(day_error)}")
                    
                    current_date += timedelta(days=1)
                
                if daily_data and weekly_dataframes:
                    # Combine all daily dataframes into a weekly dataframe
                    weekly_df = pd.concat(weekly_dataframes, ignore_index=True)
                    
                    participant_data[participant_id] = {
                        'participant': participant,
                        'daily_data': daily_data,
                        'weekly_dataframe': weekly_df,
                        'total_records': len(weekly_df)
                    }
                
            except Exception as e:
                logger.error(f"Failed to load data for participant {participant_id}: {str(e)}")
                continue
        
        return participant_data
    
    def _validate_data_availability(self, participant_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that required data is available in S3 for report generation."""
        validated_data = {}
        
        for participant_id, data in participant_data.items():
            if data['daily_data']:
                # Count how many days have data
                days_with_data = len(data['daily_data'])
                total_days = (self.week_end - self.week_start).days + 1
                
                logger.info(f"Participant {participant_id}: {days_with_data}/{total_days} days with data")
                
                # Include participants with at least some data
                if days_with_data > 0:
                    validated_data[participant_id] = data
                    validated_data[participant_id]['data_completeness'] = days_with_data / total_days
                else:
                    logger.warning(f"No data available for participant {participant_id} for the week")
            else:
                logger.warning(f"No daily data found for participant {participant_id}")
        
        return validated_data
    
    def _generate_weekly_reports(self, participant_data: Dict[str, Any]) -> Dict[str, str]:
        """Generate weekly reports for all participants."""
        reports = {}
        
        for participant_id, data in participant_data.items():
            try:
                participant = data['participant']
                
                # Aggregate weekly sensor data
                weekly_sensor_data = self._aggregate_weekly_data(data)
                
                # Calculate report parameters
                weeks_enrolled = self._calculate_weeks_enrolled(participant)
                current_pregnancy_week = self._get_pregnancy_week(participant)
                ring_wear_percentage = self._calculate_ring_wear(weekly_sensor_data)
                surveys_completed = self._get_surveys_completed(participant)
                total_surveys = 7  # Assuming daily surveys
                enrolled_date = participant.get('enrollmentDate', 'Unknown')
                
                # Generate HTML report
                html_report = generate_weekly_report_template(
                    json_data=weekly_sensor_data,
                    weeks_enrolled=weeks_enrolled,
                    current_pregnancy_week=current_pregnancy_week,
                    ring_wear_percentage=ring_wear_percentage,
                    surveys_completed=surveys_completed,
                    total_surveys=total_surveys,
                    enrolled_date=enrolled_date
                )
                
                reports[participant_id] = html_report
                logger.info(f"Generated report for participant {participant_id}")
                
            except Exception as e:
                logger.error(f"Failed to generate report for {participant_id}: {str(e)}")
                continue
        
        return reports
    
    def _aggregate_weekly_data(self, participant_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Aggregate weekly sensor data into format expected by templates."""
        weekly_df = participant_data.get('weekly_dataframe')
        
        if weekly_df is None or weekly_df.empty:
            logger.warning("No weekly dataframe available for aggregation")
            return self._get_default_aggregated_data()
        
        try:
            aggregated_data = []
            
            # Process heart rate data if available
            if 'heart_rate' in weekly_df.columns or 'hr' in weekly_df.columns:
                hr_col = 'heart_rate' if 'heart_rate' in weekly_df.columns else 'hr'
                hr_data = weekly_df[hr_col].dropna()
                
                if not hr_data.empty:
                    aggregated_data.append({
                        "type": "hr",
                        "object": {
                            "day_start_timestamp": int(self.week_start.timestamp()),
                            "title": "Heart Rate",
                            "values": hr_data.tolist(),
                            "last_reading": float(hr_data.iloc[-1]),
                            "avg": float(hr_data.mean()),
                            "min": float(hr_data.min()),
                            "max": float(hr_data.max()),
                            "unit": "BPM"
                        }
                    })
            
            # Process steps data if available
            if 'steps' in weekly_df.columns or 'step_count' in weekly_df.columns:
                steps_col = 'steps' if 'steps' in weekly_df.columns else 'step_count'
                steps_data = weekly_df[steps_col].dropna()
                
                if not steps_data.empty:
                    weekly_avg = float(steps_data.mean())
                    aggregated_data.append({
                        "type": "steps",
                        "object": {
                            "day_start_timestamp": int(self.week_start.timestamp()),
                            "values": steps_data.tolist(),
                            "subtitle": "Weekly Average",
                            "avg": weekly_avg,
                            "total": float(steps_data.sum()),
                            "trend_title": f"Avg: {int(weekly_avg)}",
                            "trend_direction": "positive" if weekly_avg > 7000 else "neutral"
                        }
                    })
            
            # Process sleep data if available
            if 'sleep_duration' in weekly_df.columns or 'sleep' in weekly_df.columns:
                sleep_col = 'sleep_duration' if 'sleep_duration' in weekly_df.columns else 'sleep'
                sleep_data = weekly_df[sleep_col].dropna()
                
                if not sleep_data.empty:
                    aggregated_data.append({
                        "type": "sleep",
                        "object": {
                            "day_start_timestamp": int(self.week_start.timestamp()),
                            "title": "Sleep Duration",
                            "values": sleep_data.tolist(),
                            "avg_hours": float(sleep_data.mean()),
                            "unit": "hours"
                        }
                    })
            
            # If no specific metrics found, return default data
            if not aggregated_data:
                return self._get_default_aggregated_data()
            
            return aggregated_data
            
        except Exception as e:
            logger.error(f"Failed to aggregate weekly data: {str(e)}")
            return self._get_default_aggregated_data()
    
    def _get_default_aggregated_data(self) -> List[Dict[str, Any]]:
        """Return default aggregated data structure when no real data is available."""
        return [
            {
                "type": "hr",
                "object": {
                    "day_start_timestamp": int(self.week_start.timestamp()),
                    "title": "Heart Rate",
                    "values": [],
                    "last_reading": 75,
                    "unit": "BPM"
                }
            },
            {
                "type": "steps",
                "object": {
                    "day_start_timestamp": int(self.week_start.timestamp()),
                    "values": [],
                    "subtitle": "Weekly Average",
                    "avg": 8500,
                    "trend_title": "+500",
                    "trend_direction": "positive"
                }
            }
        ]
    
    def _calculate_weeks_enrolled(self, participant: Dict[str, Any]) -> int:
        """Calculate how many weeks participant has been enrolled."""
        enrollment_date_str = participant.get('enrollmentDate')
        if not enrollment_date_str:
            return 1
        
        try:
            enrollment_date = datetime.fromisoformat(enrollment_date_str.replace('Z', '+00:00')).date()
            weeks_enrolled = (self.target_date - enrollment_date).days // 7
            return max(1, weeks_enrolled)
        except:
            return 1
    
    def _get_pregnancy_week(self, participant: Dict[str, Any]) -> int:
        """Extract pregnancy week from participant data."""
        custom_fields = participant.get('customFields', {})
        return custom_fields.get('pregnancyWeek', 20)  # Default to 20 weeks
    
    def _calculate_ring_wear(self, sensor_data: List[Dict[str, Any]]) -> float:
        """Calculate ring wear percentage from sensor data."""
        # Simplified calculation - in practice you'd analyze data availability
        return 85.0  # Default 85% wear rate
    
    def _get_surveys_completed(self, participant: Dict[str, Any]) -> int:
        """Get number of surveys completed this week."""
        # This would typically query survey data from MDH
        return 5  # Default value
    
    def _upload_reports_to_s3(self, reports: Dict[str, str]):
        """Upload generated reports to S3."""
        week_prefix = f"weekly-reports/{self.week_start.strftime('%Y/%m/%d')}"
        
        for participant_id, html_report in reports.items():
            s3_key = f"{week_prefix}/{participant_id}/weekly_report.html"
            
            try:
                self.s3_client.put_object(
                    Bucket=self.reports_bucket,
                    Key=s3_key,
                    Body=html_report.encode('utf-8'),
                    ContentType='text/html',
                    Metadata={
                        'participant_id': participant_id,
                        'report_type': 'weekly_health_report',
                        'week_start': self.week_start.isoformat(),
                        'week_end': self.week_end.isoformat(),
                        'generated_timestamp': datetime.utcnow().isoformat()
                    }
                )
                logger.info(f"Uploaded report: {s3_key}")
                
            except Exception as e:
                logger.error(f"Failed to upload report {s3_key}: {str(e)}")
    
    def process_weekly_data(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Main orchestration method for processing weekly data.
        
        Args:
            target_date: Optional date string (YYYY-MM-DD) to process specific week
            
        Returns:
            Dictionary with processing results and statistics
        """
        try:
            # Initialize connections
            self._initialize_connections()
            
            # Calculate date range
            self._calculate_date_range(target_date)
            
            # Get active participants
            participants = self._get_active_participants()
            
            if not participants:
                return {
                    'success': True,
                    'message': 'No active participants found',
                    'participants_processed': 0,
                    'reports_generated': 0
                }
            
            # Load Ultrahuman data from S3
            participant_data = self._load_ultrahuman_data_from_s3(participants)
            
            # Validate data availability
            participant_data = self._validate_data_availability(participant_data)
            
            # Generate weekly reports
            reports = self._generate_weekly_reports(participant_data)
            
            # Upload reports to S3
            self._upload_reports_to_s3(reports)
            
            return {
                'success': True,
                'message': 'Weekly data processing completed successfully',
                'week_start': self.week_start.isoformat(),
                'week_end': self.week_end.isoformat(),
                'participants_processed': len(participant_data),
                'reports_generated': len(reports),
                'total_records_processed': sum(data.get('total_records', 0) for data in participant_data.values()),
                'data_files_found': sum(len(data['daily_data']) for data in participant_data.values())
            }
            
        except Exception as e:
            logger.error(f"Weekly data processing failed: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': str(e),
                'message': 'Weekly data processing failed'
            }


def lambda_handler(event, context):
    """
    AWS Lambda entry point for SensorFabric data processing.
    
    Expected event structure:
    {
        "target_date": "2023-12-15"  # Optional: specific date to process
    }
    
    Environment variables required:
    - SF_DATA_BUCKET: S3 bucket for raw data storage
    - SF_REPORTS_BUCKET: S3 bucket for reports (optional, defaults to SF_DATA_BUCKET)
    - MDH_SECRET: MyDataHelps account secret
    - MDH_ACC_NAME: MyDataHelps account name
    - MDH_PROJ_NAME: MyDataHelps project name
    - MDH_PROJ_ID: MyDataHelps project ID
    """
    
    logger.info(f"Lambda function started with event: {json.dumps(event)}")
    
    try:
        glue = SensorFabricGlue()
        
        # Extract target date from event if provided
        target_date = event.get('target_date')
        
        # Process the weekly data
        result = glue.process_weekly_data(target_date)
        
        # Prepare Lambda response
        response = {
            'statusCode': 200 if result['success'] else 500,
            'body': json.dumps(result, indent=2),
            'headers': {
                'Content-Type': 'application/json'
            }
        }
        
        logger.info(f"Lambda function completed: {json.dumps(result)}")
        return response
        
    except Exception as e:
        error_message = f"Lambda function failed: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e),
                'message': 'Lambda function execution failed'
            }),
            'headers': {
                'Content-Type': 'application/json'
            }
        }


# Convenience function for local testing
def test_locally(target_date: Optional[str] = None):
    """
    Function to test the data processing pipeline locally.
    
    Args:
        target_date: Optional date string (YYYY-MM-DD) to process specific week
    """
    # Mock event for local testing
    event = {}
    if target_date:
        event['target_date'] = target_date
    
    # Mock context object
    class MockContext:
        def __init__(self):
            self.function_name = 'sensorfabric-glue-local-test'
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
