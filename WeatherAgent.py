from python_a2a import A2AServer, skill, agent, run_server, TaskStatus, TaskState
import os
import requests
import logging
from datetime import datetime, timedelta
@agent(
    name="Weather Agent",
    description="Provides comprehensive weather information including current conditions and forecasts",
    version="2.0.0",
    url="https://zzz.example.com"
)
class WeatherAgent(A2AServer):
    
    @skill(
        name="Get Weather Forecast",
        description="Get current weather and forecast for a location with various parameters",
        tags=["weather", "forecast", "current", "daily", "hourly"],
        examples="Get weather forecast for New York for the next 7 days"
    )
    def get_weather(self, location, forecast_days=7, include_current=True, include_hourly=False, include_daily=True):
        """Get comprehensive weather data using Open-Meteo API."""
        try:
            # First, get coordinates for the location using geocoding
            geocoding_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1&language=en&format=json"
            geo_response = requests.get(geocoding_url, timeout=5)
            geo_response.raise_for_status()
            geo_data = geo_response.json()
            
            if not geo_data.get("results"):
                return f"Could not find coordinates for location: {location}"
            
            result = geo_data["results"][0]
            latitude = result["latitude"]
            longitude = result["longitude"]
            city_name = result["name"]
            country = result.get("country", "")
            
            # Build the forecast API request
            base_url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": latitude,
                "longitude": longitude,
                "forecast_days": min(forecast_days, 16),  # Max 16 days
                "timezone": "auto",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "precipitation_unit": "inch"
            }
            
            # Add weather variables based on requirements
            if include_current:
                params["current"] = "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m"
            
            if include_hourly:
                params["hourly"] = "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,precipitation"
            
            if include_daily:
                params["daily"] = "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max"
            
            logging.debug(f"Request URL: {base_url}")
            logging.debug(f"Request params: {params}")
            
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            
            logging.debug(f"Response Status Code: {response.status_code}")
            
            data = response.json()
            
            # Format the response
            weather_report = self._format_weather_response(data, city_name, country, include_current, include_daily, include_hourly)
            
            return weather_report
        
        except requests.RequestException as e:
            return f"Error fetching weather: {e}"
        except (KeyError, TypeError, IndexError) as e:
            return f"Could not parse weather data: {e}"
    
    def _format_weather_response(self, data, city_name, country, include_current, include_daily, include_hourly):
        """Format the weather API response into a readable format."""
        report = f"Weather forecast for {city_name}, {country}\n"
        report += "=" * 50 + "\n\n"
        
        # Current weather
        if include_current and "current" in data:
            current = data["current"]
            report += "CURRENT CONDITIONS:\n"
            report += f"Temperature: {current.get('temperature_2m', 'N/A')}°F\n"
            report += f"Humidity: {current.get('relative_humidity_2m', 'N/A')}%\n"
            report += f"Wind Speed: {current.get('wind_speed_10m', 'N/A')} mph\n"
            report += f"Wind Direction: {current.get('wind_direction_10m', 'N/A')}°\n"
            weather_desc = self._get_weather_description(current.get('weather_code'))
            report += f"Conditions: {weather_desc}\n\n"
        
        # Daily forecast
        if include_daily and "daily" in data:
            daily = data["daily"]
            report += "DAILY FORECAST:\n"
            
            for i, date in enumerate(daily["time"]):
                if i >= 7:  # Limit to 7 days for readability
                    break
                    
                date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
                day_name = date_obj.strftime("%A, %B %d")
                
                max_temp = daily["temperature_2m_max"][i]
                min_temp = daily["temperature_2m_min"][i]
                precipitation = daily["precipitation_sum"][i]
                wind_speed = daily["wind_speed_10m_max"][i]
                weather_desc = self._get_weather_description(daily["weather_code"][i])
                
                report += f"{day_name}:\n"
                report += f"  High: {max_temp}°F, Low: {min_temp}°F\n"
                report += f"  Conditions: {weather_desc}\n"
                report += f"  Precipitation: {precipitation} in\n"
                report += f"  Max Wind: {wind_speed} mph\n\n"
        
        return report
    
    def _get_weather_description(self, weather_code):
        """Convert weather code to human-readable description."""
        if weather_code is None:
            return "Unknown"
        
        weather_codes = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            56: "Light freezing drizzle",
            57: "Dense freezing drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            66: "Light freezing rain",
            67: "Heavy freezing rain",
            71: "Slight snow fall",
            73: "Moderate snow fall",
            75: "Heavy snow fall",
            77: "Snow grains",
            80: "Slight rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            85: "Slight snow showers",
            86: "Heavy snow showers",
            95: "Thunderstorm",
            96: "Thunderstorm with slight hail",
            99: "Thunderstorm with heavy hail"
        }
        
        return weather_codes.get(weather_code, f"Weather code: {weather_code}")
    
    def handle_task(self, task):
        # Extract location from message
        message_data = task.message or {}
        content = message_data.get("content", {})
        text = content.get("text", "") if isinstance(content, dict) else ""
        
        if "weather" in text.lower():
            # Parse forecast parameters from the message
            forecast_days = 7  # default
            include_hourly = "hourly" in text.lower()
            
            # Extract number of days if specified
            import re
            days_match = re.search(r'(\d+)\s*days?', text.lower())
            if days_match:
                forecast_days = min(int(days_match.group(1)), 16)
            
            # Extract location
            if "in" in text.lower():
                location = text.split("in", 1)[1].strip().rstrip("?.")
                # Remove any trailing parameters
                location = re.split(r'\s+for\s+|\s+with\s+', location)[0].strip()
            elif "for" in text.lower():
                location = text.split("for", 1)[1].strip().rstrip("?.")
                location = re.split(r'\s+in\s+|\s+with\s+', location)[0].strip()
            else:
                # Try to extract location from the message
                words = text.split()
                location = " ".join(words[-2:])  # Take last 2 words as potential location
            
            if location:
                # Get weather and create response
                weather_text = self.get_weather(
                    location=location,
                    forecast_days=forecast_days,
                    include_current=True,
                    include_hourly=include_hourly,
                    include_daily=True
                )
                task.artifacts = [{
                    "parts": [{"type": "text", "text": weather_text}]
                }]
                task.status = TaskStatus(state=TaskState.COMPLETED)
            else:
                task.status = TaskStatus(
                    state=TaskState.INPUT_REQUIRED,
                    message={"role": "agent", "content": {"type": "text", 
                             "text": "Please specify a location for the weather forecast."}}
                )
        else:
            task.status = TaskStatus(
                state=TaskState.INPUT_REQUIRED,
                message={"role": "agent", "content": {"type": "text", 
                         "text": "Please ask about weather for a specific location. You can specify forecast days (1-16) and request hourly data."}}
            )
        return task
# Run the server
if __name__ == "__main__":
    agent = WeatherAgent(google_a2a_compatible=True)
    run_server(agent, port=8001, debug=True)