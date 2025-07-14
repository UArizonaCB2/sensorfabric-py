from jinja2 import Template
from datetime import datetifme
from typing import Dict, List, Any, Optional
import json
import jsonschema
import os
from sensorfabric.utils import validate_sensor_data_schema


def generate_weekly_report_template(
    json_data: List[Dict[str, Any]], 
    weeks_enrolled: int,
    current_pregnancy_week: int,
    ring_wear_percentage: float,
    surveys_completed: int,
    total_surveys: int,
    enrolled_date: str,
    last_week_data: Optional[Dict] = None
) -> str:
    """
    Generate a Jinja2 HTML template for weekly health reports from Ultrahuman API data.
    
    Args:
        json_data: List of sensor data objects from Ultrahuman API
        weeks_enrolled: Number of weeks participant has been enrolled
        current_pregnancy_week: Current week of pregnancy
        ring_wear_percentage: Percentage of time ring was worn
        surveys_completed: Number of surveys completed this week
        total_surveys: Total number of surveys available
        enrolled_date: Date when participant enrolled
        last_week_data: Optional data from previous week for trend comparison
        
    Returns:
        HTML string with populated template
        
    Raises:
        jsonschema.ValidationError: If the input data doesn't match the expected schema
        FileNotFoundError: If the schema file cannot be found
    """
    
    # Validate the JSON data against the schema
    # TODO this actually needs to be the schema from SQL query.
    validate_sensor_data_schema(json_data)
    
    # Process the JSON data to extract metrics
    metrics = _process_sensor_data(json_data, last_week_data)
    
    template_str = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Weekly Health Report</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .metric { margin: 10px 0; padding: 10px; background-color: #f5f5f5; border-radius: 5px; }
            .trend-positive { color: green; }
            .trend-negative { color: red; }
            .trend-neutral { color: #666; }
        </style>
    </head>
    <body>
        <h1>Weekly Health Report</h1>
        
        <div class="metric">
            <strong>Enrollment Status:</strong> {{ weeks_enrolled }} weeks enrolled
        </div>
        
        <div class="metric">
            <strong>Pregnancy Progress:</strong> {{ current_pregnancy_week }} weeks - {{ current_pregnancy_week + 1 }} weeks pregnant
        </div>
        
        <div class="metric">
            <strong>Device Usage:</strong> {{ "%.0f"|format(ring_wear_percentage) }}% ring wear time
        </div>
        
        <div class="metric">
            <strong>Survey Completion:</strong> {{ surveys_completed }} of {{ total_surveys }} surveys completed
        </div>
        
        {% if metrics.blood_pressure %}
        <div class="metric">
            <strong>Blood Pressure:</strong> You recorded {{ metrics.blood_pressure.count }} blood pressures this week. 
            Blood pressure trend: {{ metrics.blood_pressure.trend }} as last week. 
            Number of blood pressures over 140/90 = {{ metrics.blood_pressure.high_readings or "none" }}
        </div>
        {% endif %}
        
        {% if metrics.heart_rate %}
        <div class="metric">
            <strong>Heart Rate:</strong> {{ metrics.heart_rate.total_beats }} heart beats recorded. 
            Average resting heart rate of {{ "%.0f"|format(metrics.heart_rate.avg_resting) }}
        </div>
        {% endif %}
        
        {% if metrics.temperature %}
        <div class="metric">
            <strong>Temperature:</strong> Total temperature readings = {{ metrics.temperature.total_readings }}. 
            Trending = {{ metrics.temperature.trend }}
            <br>
            {{ metrics.temperature.fever_readings or "No" }} temperatures over 100.0°F recorded
        </div>
        {% endif %}
        
        {% if metrics.sleep %}
        <div class="metric">
            <strong>Sleep:</strong> {{ "%.1f"|format(metrics.sleep.total_hours) }} hours of sleep this week. 
            Average {{ "%.1f"|format(metrics.sleep.avg_per_night) }} per night.
        </div>
        {% endif %}
        
        {% if metrics.weight %}
        <div class="metric">
            <strong>Weight:</strong> Change in weight this week = {{ metrics.weight.weekly_change }} lbs. 
            Total change {{ metrics.weight.total_change }} lbs since {{ enrolled_date }}
        </div>
        {% endif %}
        
        {% if metrics.movement %}
        <div class="metric">
            <strong>Movement:</strong> Total movement this week = {{ "%.0f"|format(metrics.movement.total_minutes) }} minutes. 
            Average steps per day = {{ "%.0f"|format(metrics.movement.avg_steps_per_day) }}
            <br>
            Trend - {{ "%.0f"|format(abs(metrics.movement.step_trend)) }} 
            {{ "fewer" if metrics.movement.step_trend < 0 else "more" }} than last week
        </div>
        {% endif %}
        
        <div class="metric">
            <small>Report generated on {{ report_date }}</small>
        </div>
    </body>
    </html>
    """
    
    template = Template(template_str)
    
    return template.render(
        weeks_enrolled=weeks_enrolled,
        current_pregnancy_week=current_pregnancy_week,
        ring_wear_percentage=ring_wear_percentage,
        surveys_completed=surveys_completed,
        total_surveys=total_surveys,
        enrolled_date=enrolled_date,
        metrics=metrics,
        report_date=datetime.now().strftime("%Y-%m-%d %H:%M")
    )


def _process_sensor_data(json_data: List[Dict[str, Any]], last_week_data: Optional[Dict] = None) -> Dict[str, Any]:
    """Process sensor data and calculate metrics for the template."""
    
    metrics = {}
    
    for item in json_data:
        data_type = item.get('type')
        obj = item.get('object', {})
        
        if data_type == 'hr':
            metrics['heart_rate'] = _process_heart_rate(obj)
        elif data_type == 'temp':
            metrics['temperature'] = _process_temperature(obj)
        elif data_type == 'steps':
            metrics['movement'] = _process_movement(obj, last_week_data)
        elif data_type == 'motion':
            metrics['sleep'] = _process_sleep(obj)
    
    return metrics


def _process_heart_rate(hr_data: Dict[str, Any]) -> Dict[str, Any]:
    """Process heart rate data."""
    values = hr_data.get('values', [])
    total_beats = sum(val['value'] for val in values) * 60  # Approximate total beats
    avg_resting = sum(val['value'] for val in values) / len(values) if values else 0
    
    return {
        'total_beats': total_beats,
        'avg_resting': avg_resting
    }


def _process_temperature(temp_data: Dict[str, Any]) -> Dict[str, Any]:
    """Process temperature data."""
    values = temp_data.get('values', [])
    total_readings = len(values)
    
    # Convert Celsius to Fahrenheit and check for fever
    fever_count = 0
    for val in values:
        temp_f = (val['value'] * 9/5) + 32
        if temp_f > 100.0:
            fever_count += 1
    
    return {
        'total_readings': total_readings,
        'trend': 'steady',  # Could be calculated from trend data if available
        'fever_readings': fever_count if fever_count > 0 else None
    }


def _process_movement(movement_data: Dict[str, Any], last_week_data: Optional[Dict] = None) -> Dict[str, Any]:
    """Process movement/steps data."""
    values = movement_data.get('values', [])
    total_steps = sum(val['value'] for val in values)
    avg_steps_per_day = total_steps / 7 if total_steps > 0 else 0
    total_minutes = total_steps * 0.5  # Approximate minutes based on steps
    
    # Calculate trend vs last week
    step_trend = 0
    if last_week_data and 'steps' in last_week_data:
        last_week_steps = last_week_data['steps']
        step_trend = total_steps - last_week_steps
    
    return {
        'total_minutes': total_minutes,
        'avg_steps_per_day': avg_steps_per_day,
        'step_trend': step_trend
    }


def _process_sleep(motion_data: Dict[str, Any]) -> Dict[str, Any]:
    """Process sleep data from motion object."""
    sleep_graph = motion_data.get('sleep_graph', {})
    sleep_data = sleep_graph.get('data', [])
    
    total_sleep_seconds = 0
    for stage in sleep_data:
        if stage['type'] in ['light_sleep', 'deep_sleep']:
            total_sleep_seconds += stage['end'] - stage['start']
    
    total_hours = total_sleep_seconds / 3600
    avg_per_night = total_hours / 7
    
    return {
        'total_hours': total_hours,
        'avg_per_night': avg_per_night
    }


### json data from ultrahuman API:
# 
# [
#     {
#         "type": "hr",
#         "object": {
#             "day_start_timestamp": 1671739200,
#             "title": "Heart Rate",
#             "values": [
#                 {
#                     "value": 81,
#                     "timestamp": 1671739294
#                 },
#                 {
#                     "value": 94,
#                     "timestamp": 1671739586
#                 },
#                 {
#                     "value": 88,
#                     "timestamp": 1671739887
#                 },
#                 {
#                     "value": 80,
#                     "timestamp": 1671740155
#                 },
#                 {
#                     "value": 76,
#                     "timestamp": 1671740447
#                 },
#                 {
#                     "value": 84,
#                     "timestamp": 1671740750
#                 },
#                 {
#                     "value": 79,
#                     "timestamp": 1671741034
#                 },
#                 {
#                     "value": 74,
#                     "timestamp": 1671741342
#                 },
#                 {
#                     "value": 84,
#                     "timestamp": 1671741623
#                 },
#                 {
#                     "value": 78,
#                     "timestamp": 1671741911
#                 },
#                 {
#                     "value": 85,
#                     "timestamp": 1671742204
#                 },
#                 {
#                     "value": 80,
#                     "timestamp": 1671742497
#                 },
#                 {
#                     "value": 93,
#                     "timestamp": 1671742812
#                 }
#             ],
#             "last_reading": 78,
#             "unit": "BPM"
#         }
#     },
#     {
#         "type": "temp",
#         "object": {
#             "day_start_timestamp": 1671739200,
#             "title": "Skin Temperature",
#             "values": [
#                 {
#                     "value": 32.84204864501953,
#                     "timestamp": 1671739393
#                 },
#                 {
#                     "value": 31.783939361572266,
#                     "timestamp": 1671739686
#                 },
#                 {
#                     "value": 32.68800354003906,
#                     "timestamp": 1671739979
#                 },
#                 {
#                     "value": 33.4249153137207,
#                     "timestamp": 1671740272
#                 },
#                 {
#                     "value": 30.226356506347656,
#                     "timestamp": 1671740565
#                 }
#             ],
#             "last_reading": 33,
#             "unit": "°C"
#         }
#     },
#     {
#         "type": "hrv",
#         "object": {
#             "day_start_timestamp": 1671739200,
#             "title": "HRV",
#             "values": [
#                 {
#                     "value": 100,
#                     "timestamp": 1671739586
#                 },
#                 {
#                     "value": 33,
#                     "timestamp": 1671740155
#                 },
#                 {
#                     "value": 34,
#                     "timestamp": 1671740447
#                 },
#                 {
#                     "value": 49,
#                     "timestamp": 1671741034
#                 },
#                 {
#                     "value": 39,
#                     "timestamp": 1671741342
#                 }
#             ],
#             "subtitle": "Average",
#             "avg": 32,
#             "trend_title": "-14",
#             "trend_direction": "negative"
#         }
#     },
#     {
#         "type": "steps",
#         "object": {
#             "day_start_timestamp": 1671739200,
#             "values": [
#                 {
#                     "value": 114.0,
#                     "timestamp": 1671739393
#                 },
#                 {
#                     "value": 25.0,
#                     "timestamp": 1671739686
#                 },
#                 {
#                     "value": 0.0,
#                     "timestamp": 1671739979
#                 },
#                 {
#                     "value": 0.0,
#                     "timestamp": 1671740272
#                 },
#                 {
#                     "value": 59.0,
#                     "timestamp": 1671740565
#                 }
#             ],
#             "subtitle": "Average",
#             "avg": 28.305084745762713,
#             "trend_title": "+5",
#             "trend_direction": "positive"
#         }
#     },
#     {
#         "type": "motion",
#         "object": {
#             "day_start_timestamp": 1671739200,
#             "values": [
#                 {
#                     "value": 104.0,
#                     "timestamp": 1671739393
#                 },
#                 {
#                     "value": 74.0,
#                     "timestamp": 1671739686
#                 },
#                 {
#                     "value": 15.0,
#                     "timestamp": 1671739979
#                 },
#                 {
#                     "value": 12.0,
#                     "timestamp": 1671740272
#                 },
#                 {
#                     "value": 63.0,
#                     "timestamp": 1671740565
#                 },
#                 {
#                     "value": 42.0,
#                     "timestamp": 1671740858
#                 }
#             ],
#             "sleep_graph": {
#                 "title": "Sleep Stages",
#                 "data": [
#                     {
#                         "start": 1671744060,
#                         "end": 1671744360,
#                         "type": "awake"
#                     },
#                     {
#                         "start": 1671744360,
#                         "end": 1671744960,
#                         "type": "deep_sleep"
#                     },
#                     {
#                         "start": 1671744960,
#                         "end": 1671745200,
#                         "type": "light_sleep"
#                     },
#                     {
#                         "start": 1671745200,
#                         "end": 1671745500,
#                         "type": "awake"
#                     },
#                     {
#                         "start": 1671745500,
#                         "end": 1671747540,
#                         "type": "light_sleep"
#                     },
#                     {
#                         "start": 1671747540,
#                         "end": 1671748740,
#                         "type": "deep_sleep"
#                     },
#                     {
#                         "start": 1671748740,
#                         "end": 1671749340,
#                         "type": "light_sleep"
#                     },
#                     {
#                         "start": 1671749340,
#                         "end": 1671750180,
#                         "type": "deep_sleep"
#                     },
#                     {
#                         "start": 1671750180,
#                         "end": 1671753720,
#                         "type": "light_sleep"
#                     }
#                 ]
#             },
#             "hr_graph": {
#                 "title": "HR",
#                 "data": [
#                     {
#                         "timestamp": 1671744060,
#                         "value": 80.5
#                     },
#                     {
#                         "timestamp": 1671744360,
#                         "value": 77.5
#                     },
#                     {
#                         "timestamp": 1671744660,
#                         "value": 75.0
#                     },
#                     {
#                         "timestamp": 1671744960,
#                         "value": 78.0
#                     },
#                     {
#                         "timestamp": 1671745200,
#                         "value": 80.5
#                     },
#                     {
#                         "timestamp": 1671745500,
#                         "value": 78.0
#                     },
#                     {
#                         "timestamp": 1671745800,
#                         "value": 74.5
#                     },
#                     {
#                         "timestamp": 1671746100,
#                         "value": 72.5
#                     },
#                     {
#                         "timestamp": 1671746400,
#                         "value": 70.0
#                     },
#                     {
#                         "timestamp": 1671746700,
#                         "value": 69.0
#                     },
#                     {
#                         "timestamp": 1671747000,
#                         "value": 70.5
#                     },
#                     {
#                         "timestamp": 1671747300,
#                         "value": 70.0
#                     },
#                     {
#                         "timestamp": 1671747540,
#                         "value": 70.0
#                     },
#                     {
#                         "timestamp": 1671747840,
#                         "value": 70.0
#                     }
#                 ]
#             },
#             "hrv_graph": {
#                 "title": "HRV",
#                 "data": [
#                     {
#                         "timestamp": 1671744060,
#                         "value": 14.5
#                     },
#                     {
#                         "timestamp": 1671744360,
#                         "value": 17.0
#                     },
#                     {
#                         "timestamp": 1671744660,
#                         "value": 14.5
#                     },
#                     {
#                         "timestamp": 1671744960,
#                         "value": 25.5
#                     },
#                     {
#                         "timestamp": 1671745200,
#                         "value": 32.75
#                     },
#                     {
#                         "timestamp": 1671745500,
#                         "value": 28.0
#                     },
#                     {
#                         "timestamp": 1671745800,
#                         "value": 12.5
#                     }
#                 ]
#             },
#             "summary": [
#                 {
#                     "title": "Sleep Efficiency",
#                     "state": "warning",
#                     "state_title": "Needs attention",
#                     "score": 65,
#                     "education_modal_deeplink": "ultrahuman://educationModal?id=sleep_efficiency_sleep"
#                 },
#                 {
#                     "title": "Total Sleep",
#                     "state": "good",
#                     "state_title": "Good",
#                     "score": 79,
#                     "education_modal_deeplink": "ultrahuman://educationModal?id=total_sleep_sleep"
#                 },
#                 {
#                     "title": "Temperature",
#                     "state": "optimal",
#                     "state_title": "Optimal",
#                     "score": 98,
#                     "education_modal_deeplink": "ultrahuman://educationModal?id=temperature_sleep"
#                 },
#                 {
#                     "title": "Restfulness",
#                     "state": "good",
#                     "state_title": "Good",
#                     "score": 76.75,
#                     "education_modal_deeplink": "ultrahuman://educationModal?id=restfulness_sleep"
#                 },
#                 {
#                     "title": "HRV Form",
#                     "state": "warning",
#                     "state_title": "Needs attention",
#                     "score": 50,
#                     "education_modal_deeplink": "ultrahuman://educationModal?id=hrv_sleep"
#                 },
#                 {
#                     "title": "Timing",
#                     "state": "warning",
#                     "state_title": "Needs attention",
#                     "score": 40,
#                     "education_modal_deeplink": "ultrahuman://educationModal?id=timing_sleep"
#                 },
#                 {
#                     "title": "Restoration Time",
#                     "state": "warning",
#                     "state_title": "Needs attention",
#                     "score": 60.47222222222222,
#                     "education_modal_deeplink": "ultrahuman://educationModal?id=restoration_time"
#                 }
#             ]
#         }
#     } // End of motion object
# ]
