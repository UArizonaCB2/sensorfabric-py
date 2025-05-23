import os
import requests
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any
import io


class UltrahumanAPI:
    """
    API client for Ultrahuman metrics data.
    Supports both development (staging) and production environments.
    
    Environment variables:
    - UH_ENVIRONMENT: 'development' or 'production' (default: 'development')
    - UH_DEV_API_KEY: API key for development/staging environment
    - UH_DEV_BASE_URL: Base URL for development/staging environment
    - UH_PROD_API_KEY: API key for production environment  
    - UH_PROD_BASE_URL: Base URL for production environment
    """
    
    # Default configurations
    DEFAULT_CONFIGS = {
        'development': {
            'base_url': 'https://www.staging.ultrahuman.com/api/v1/metrics',
            'api_key': 'eyJhbGciOiJIUzI1NiJ9.eyJzZWNyZXQiOiJjZGM5MjdkYjQ3ZjA5ZDhhNzQxYiIsImV4cCI6MjQzMDEzNTM5Nn0.x3SqFIubvafBxZ1GxvPRqHCd0CLa4_jip8LHbopzLsQ'
        },
        'production': {
            'base_url': os.getenv("UH_PROD_BASE_URL", None),  # Must be set via environment variable
            'api_key': os.getenv("UH_PROD_API_KEY", None)    # Must be set via environment variable
        }
    }
    
    def __init__(self, environment: Optional[str] = None):
        """
        Initialize the Ultrahuman API client.
        
        Parameters
        ----------
        environment : str, optional
            Environment to use ('development' or 'production').
            If not provided, will read from UH_ENVIRONMENT env var.
            Defaults to 'development' if not set.
        """
        self.environment = environment or os.getenv('UH_ENVIRONMENT', 'development')
        
        if self.environment not in ['development', 'production']:
            raise ValueError("Environment must be 'development' or 'production'")
            
        self._configure_environment()
    
    def _configure_environment(self):
        """Configure API settings based on environment."""
        config = self.DEFAULT_CONFIGS[self.environment].copy()
        
        if self.environment == 'development':
            # For development, allow env vars to override defaults
            self.base_url = os.getenv('UH_DEV_BASE_URL', config['base_url'])
            self.api_key = os.getenv('UH_DEV_API_KEY', config['api_key'])
        else:
            # For production, require env vars
            self.base_url = os.getenv('UH_PROD_BASE_URL')
            self.api_key = os.getenv('UH_PROD_API_KEY')
            
            if not self.base_url:
                raise ValueError("UH_PROD_BASE_URL environment variable must be set for production")
            if not self.api_key:
                raise ValueError("UH_PROD_API_KEY environment variable must be set for production")
    
    def get_metrics(self, email: str, date: str) -> Dict[str, Any]:
        """
        Fetch metrics data for a participant.
        
        Parameters
        ----------
        email : str
            Participant email address
        date : str
            Date in DD/MM/YYYY format (e.g., '23/12/2022')
            
        Returns
        -------
        dict
            JSON response from the API
            
        Raises
        ------
        requests.RequestException
            If the API request fails
        ValueError
            If the response is not valid JSON
        """
        headers = {
            'Authorization': self.api_key
        }
        
        params = {
            'email': email,
            'date': date
        }
        
        try:
            response = requests.get(
                self.base_url,
                headers=headers,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            raise requests.RequestException(f"Failed to fetch metrics data: {e}")
        except ValueError as e:
            raise ValueError(f"Invalid JSON response: {e}")
    
    def get_metrics_as_parquet(self, email: str, date: str) -> bytes:
        """
        Fetch metrics data and return as parquet file bytes.
        
        Parameters
        ----------
        email : str
            Participant email address
        date : str
            Date in DD/MM/YYYY format (e.g., '23/12/2022')
            
        Returns
        -------
        bytes
            Parquet file content as bytes
            
        Raises
        ------
        requests.RequestException
            If the API request fails
        ValueError
            If the response cannot be converted to DataFrame
        """
        metrics_data = self.get_metrics(email, date)
        
        try:
            # Convert JSON response to DataFrame
            # Handle different possible response structures
            if isinstance(metrics_data, dict):
                if 'data' in metrics_data and isinstance(metrics_data['data'], list):
                    # Response has data wrapper
                    df = pd.DataFrame(metrics_data['data'])
                elif isinstance(metrics_data, dict) and len(metrics_data) > 0:
                    # Response is a single record or has multiple fields
                    df = pd.DataFrame([metrics_data])
                else:
                    # Empty response
                    df = pd.DataFrame()
            elif isinstance(metrics_data, list):
                # Response is a list of records
                df = pd.DataFrame(metrics_data)
            else:
                raise ValueError("Unexpected response format")
            
            # Add metadata columns
            df['fetch_timestamp'] = datetime.now().isoformat()
            df['participant_email'] = email
            df['request_date'] = date
            
            # Convert to parquet bytes
            buffer = io.BytesIO()
            df.to_parquet(buffer, index=False)
            return buffer.getvalue()
            
        except Exception as e:
            raise ValueError(f"Failed to convert response to parquet: {e}")
    
    def save_metrics_parquet(self, email: str, date: str, filename: Optional[str] = None) -> str:
        """
        Fetch metrics data and save as parquet file.
        
        Parameters
        ----------
        email : str
            Participant email address
        date : str
            Date in DD/MM/YYYY format (e.g., '23/12/2022')
        filename : str, optional
            Output filename. If not provided, generates one based on email and date.
            
        Returns
        -------
        str
            Path to the saved parquet file
        """
        if filename is None:
            # Generate filename from email and date
            safe_email = email.replace('@', '_at_').replace('.', '_')
            safe_date = date.replace('/', '-')
            filename = f"ultrahuman_metrics_{safe_email}_{safe_date}.parquet"
        
        parquet_bytes = self.get_metrics_as_parquet(email, date)
        
        with open(filename, 'wb') as f:
            f.write(parquet_bytes)
            
        return filename


# Convenience functions for quick access
def get_participant_metrics(email: str, date: str, environment: str = 'development') -> Dict[str, Any]:
    """
    Convenience function to get metrics data for a participant.
    
    Parameters
    ----------
    email : str
        Participant email address
    date : str
        Date in DD/MM/YYYY format
    environment : str
        Environment to use ('development' or 'production')
        
    Returns
    -------
    dict
        JSON response from the API
    """
    client = UltrahumanAPI(environment=environment)
    return client.get_metrics(email, date)


def get_participant_metrics_parquet(email: str, date: str, environment: str = 'development') -> bytes:
    """
    Convenience function to get metrics data as parquet bytes.
    
    Parameters
    ----------
    email : str
        Participant email address
    date : str
        Date in DD/MM/YYYY format
    environment : str
        Environment to use ('development' or 'production')
        
    Returns
    -------
    bytes
        Parquet file content as bytes
    """
    client = UltrahumanAPI(environment=environment)
    return client.get_metrics_as_parquet(email, date)
