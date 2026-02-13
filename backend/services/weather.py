"""
Mock Weather Service
====================

A simple weather service that returns random temperature data.
Used for testing and development purposes.
"""

import random
from typing import Dict, Any

class WeatherService:
    """Mock weather service that generates random weather data."""
    
    def __init__(self):
        """Initialize the weather service."""
        self.cities = {
            "new york": {"country": "USA", "timezone": "EST"},
            "london": {"country": "UK", "timezone": "GMT"},
            "tokyo": {"country": "Japan", "timezone": "JST"},
            "paris": {"country": "France", "timezone": "CET"},
            "sydney": {"country": "Australia", "timezone": "AEST"},
            "berlin": {"country": "Germany", "timezone": "CET"},
            "toronto": {"country": "Canada", "timezone": "EST"},
            "moscow": {"country": "Russia", "timezone": "MSK"},
            "beijing": {"country": "China", "timezone": "CST"},
            "mumbai": {"country": "India", "timezone": "IST"}
        }
    
    def get_weather(self, city: str) -> Dict[str, Any]:
        """
        Get mock weather data for a city.
        
        Args:
            city: The city name to get weather for
            
        Returns:
            Dictionary containing weather information
        """
        city_lower = city.lower().strip()
        
        # Generate random weather data
        temperature = round(random.uniform(-10, 35), 1)  # Temperature between -10°C and 35°C
        humidity = random.randint(30, 90)  # Humidity between 30% and 90%
        wind_speed = round(random.uniform(0, 25), 1)  # Wind speed between 0 and 25 km/h
        
        # Random weather conditions
        conditions = ["sunny", "cloudy", "rainy", "partly cloudy", "overcast", "windy"]
        condition = random.choice(conditions)
        
        # Get city info or use defaults
        city_info = self.cities.get(city_lower, {"country": "Unknown", "timezone": "UTC"})
        
        return {
            "city": city.title(),
            "country": city_info["country"],
            "timezone": city_info["timezone"],
            "temperature": temperature,
            "unit": "celsius",
            "humidity": humidity,
            "wind_speed": wind_speed,
            "condition": condition,
            "timestamp": "2025-06-17T12:00:00Z"  # Mock timestamp
        }
    
    def get_available_cities(self) -> list:
        """Get list of available cities."""
        return list(self.cities.keys())
