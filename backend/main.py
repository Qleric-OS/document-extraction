"""
Backend Main API
================

Main Flask application with weather endpoint integration.
"""

from flask import Flask, jsonify, request
from services.weather import WeatherService
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Initialize Weather Service
weather_service = WeatherService()

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "weather-api",
        "version": "1.0.0"
    })

@app.route("/weather", methods=["GET"])
def get_weather():
    """
    Get weather information for a city.
    
    Query Parameters:
        city: The city name to get weather for (required)
        
    Returns:
        JSON weather data for the specified city
    """
    city = request.args.get("city")
    
    if not city:
        return jsonify({
            "error": "City parameter is required",
            "example": "/weather?city=new york"
        }), 400
    
    try:
        weather_data = weather_service.get_weather(city)
        logger.info(f"Weather data retrieved for {city}")
        
        # Log any alerts for monitoring
        if weather_data.get("alert_count", 0) > 0:
            alert_count = weather_data["alert_count"]
            alert_types = [alert["type"] for alert in weather_data.get("alerts", [])]
            logger.warning(f"Weather alerts triggered for {city}: {alert_count} alerts - {alert_types}")
        
        return jsonify(weather_data)
    
    except Exception as e:
        logger.error(f"Error getting weather data for {city}: {e}")
        return jsonify({
            "error": "Internal server error",
            "message": "Failed to retrieve weather data"
        }), 500

@app.route("/weather/cities", methods=["GET"])
def get_available_cities():
    """Get list of available cities."""
    try:
        cities = weather_service.get_available_cities()
        return jsonify({
            "available_cities": cities,
            "count": len(cities)
        })
    except Exception as e:
        logger.error(f"Error getting available cities: {e}")
        return jsonify({
            "error": "Internal server error"
        }), 500

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        "error": "Endpoint not found",
        "available_endpoints": [
            "/health",
            "/weather?city=<city_name>",
            "/weather/cities"
        ]
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    return jsonify({
        "error": "Internal server error"
    }), 500

if __name__ == "__main__":
    port = int(8000)  # Using port 8000 as specified in completion protocol
    logger.info(f"Starting weather API server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True)
