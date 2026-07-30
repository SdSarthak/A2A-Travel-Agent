from datetime import datetime

import requests
from python_a2a import A2AServer, TaskState, TaskStatus, agent, run_server, skill

import config
from travel_utils import (
    configure_logging,
    extract_location,
    extract_message_text,
    parse_forecast_days,
    text_artifact,
)

logger = configure_logging("weather-agent")

WEATHER_KEYWORDS = ("weather", "forecast", "temperature", "rain", "climate", "conditions")


@agent(
    name="Weather Agent",
    description="Provides comprehensive weather information including current conditions and forecasts",
    version="2.1.0",
    url=config.WEATHER_AGENT_URL,
)
class WeatherAgent(A2AServer):

    @skill(
        name="Get Weather Forecast",
        description="Get current weather and forecast for a location with various parameters",
        tags=["weather", "forecast", "current", "daily", "hourly"],
        examples="Get weather forecast for New York for the next 7 days",
    )
    def get_weather(self, location, forecast_days=None, include_current=True,
                    include_hourly=False, include_daily=True):
        """Get comprehensive weather data using Open-Meteo API."""
        if forecast_days is None:
            forecast_days = config.DEFAULT_FORECAST_DAYS

        try:
            geocoded = self.geocode(location)
        except requests.RequestException as e:
            return f"Error looking up location '{location}': {e}"

        if geocoded is None:
            return f"Could not find coordinates for location: {location}"

        try:
            params = {
                "latitude": geocoded["latitude"],
                "longitude": geocoded["longitude"],
                "forecast_days": max(1, min(forecast_days, config.MAX_FORECAST_DAYS)),
                "timezone": "auto",
                "temperature_unit": config.TEMPERATURE_UNIT,
                "wind_speed_unit": config.WIND_SPEED_UNIT,
                "precipitation_unit": config.PRECIPITATION_UNIT,
            }

            # Add weather variables based on requirements
            if include_current:
                params["current"] = (
                    "temperature_2m,relative_humidity_2m,weather_code,"
                    "wind_speed_10m,wind_direction_10m"
                )

            if include_hourly:
                params["hourly"] = (
                    "temperature_2m,relative_humidity_2m,weather_code,"
                    "wind_speed_10m,precipitation"
                )

            if include_daily:
                params["daily"] = (
                    "weather_code,temperature_2m_max,temperature_2m_min,"
                    "precipitation_sum,wind_speed_10m_max"
                )

            logger.debug("requesting forecast for %s", geocoded["name"])

            response = requests.get(
                config.OPEN_METEO_FORECAST_URL,
                params=params,
                timeout=config.REQUEST_TIMEOUT,
                headers={"User-Agent": config.USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()

            return self._format_weather_response(
                data,
                geocoded["name"],
                geocoded["country"],
                include_current,
                include_daily,
                include_hourly,
            )

        except requests.RequestException as e:
            return f"Error fetching weather: {e}"
        except (KeyError, TypeError, IndexError, ValueError) as e:
            return f"Could not parse weather data: {e}"

    def geocode(self, location):
        """Resolve a place name to coordinates, or None when it is unknown."""
        response = requests.get(
            config.OPEN_METEO_GEOCODING_URL,
            params={"name": location, "count": 1, "language": "en", "format": "json"},
            timeout=config.GEOCODING_TIMEOUT,
            headers={"User-Agent": config.USER_AGENT},
        )
        response.raise_for_status()
        results = response.json().get("results") or []
        if not results:
            return None

        result = results[0]
        return {
            "latitude": result["latitude"],
            "longitude": result["longitude"],
            "name": result.get("name", location),
            "country": result.get("country", ""),
        }

    def _format_weather_response(self, data, city_name, country, include_current,
                                 include_daily, include_hourly):
        """Format the weather API response into a readable format."""
        header = f"Weather forecast for {city_name}, {country}".rstrip(", ")
        report = header + "\n" + "=" * 50 + "\n\n"
        unit = config.temperature_symbol()

        # Current weather
        if include_current and "current" in data:
            current = data["current"]
            report += "CURRENT CONDITIONS:\n"
            report += f"Temperature: {current.get('temperature_2m', 'N/A')}{unit}\n"
            report += f"Humidity: {current.get('relative_humidity_2m', 'N/A')}%\n"
            report += f"Wind Speed: {current.get('wind_speed_10m', 'N/A')} {config.WIND_SPEED_UNIT}\n"
            report += f"Wind Direction: {current.get('wind_direction_10m', 'N/A')}°\n"
            report += f"Conditions: {self._get_weather_description(current.get('weather_code'))}\n\n"

        # Daily forecast
        if include_daily and "daily" in data:
            daily = data["daily"]
            report += "DAILY FORECAST:\n"

            for i, date in enumerate(daily.get("time", [])):
                if i >= config.MAX_FORECAST_DAYS:
                    break

                day_name = self._format_date(date, "%A, %B %d")
                report += f"{day_name}:\n"
                report += (
                    f"  High: {self._value_at(daily, 'temperature_2m_max', i)}{unit}, "
                    f"Low: {self._value_at(daily, 'temperature_2m_min', i)}{unit}\n"
                )
                report += f"  Conditions: {self._get_weather_description(self._value_at(daily, 'weather_code', i))}\n"
                report += (
                    f"  Precipitation: {self._value_at(daily, 'precipitation_sum', i)} "
                    f"{config.PRECIPITATION_UNIT}\n"
                )
                report += (
                    f"  Max Wind: {self._value_at(daily, 'wind_speed_10m_max', i)} "
                    f"{config.WIND_SPEED_UNIT}\n\n"
                )

        # Hourly forecast (next 12 hours)
        if include_hourly and "hourly" in data:
            hourly = data["hourly"]
            report += "HOURLY FORECAST (next 12 hours):\n"

            for i, timestamp in enumerate(hourly.get("time", [])[:12]):
                hour = self._format_date(timestamp, "%a %H:%M")
                report += (
                    f"  {hour}: {self._value_at(hourly, 'temperature_2m', i)}{unit}, "
                    f"{self._get_weather_description(self._value_at(hourly, 'weather_code', i))}, "
                    f"precipitation {self._value_at(hourly, 'precipitation', i)} "
                    f"{config.PRECIPITATION_UNIT}\n"
                )
            report += "\n"

        return report

    @staticmethod
    def _value_at(series, key, index):
        """Safely read ``series[key][index]`` from an Open-Meteo payload."""
        values = series.get(key) or []
        if index < len(values) and values[index] is not None:
            return values[index]
        return "N/A"

    @staticmethod
    def _format_date(value, fmt):
        """Format an ISO timestamp, falling back to the raw string."""
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime(fmt)
        except ValueError:
            return str(value)

    def _get_weather_description(self, weather_code):
        """Convert weather code to human-readable description."""
        if weather_code is None or weather_code == "N/A":
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
            99: "Thunderstorm with heavy hail",
        }

        try:
            return weather_codes.get(int(weather_code), f"Weather code: {weather_code}")
        except (TypeError, ValueError):
            return "Unknown"

    def handle_task(self, task):
        text = extract_message_text(task)

        if not any(keyword in text.lower() for keyword in WEATHER_KEYWORDS):
            task.status = TaskStatus(
                state=TaskState.INPUT_REQUIRED,
                message={"role": "agent", "content": {"type": "text",
                         "text": "Please ask about weather for a specific location. "
                                 "You can specify forecast days (1-16) and request hourly data."}},
            )
            return task

        location = extract_location(text)
        if not location:
            task.status = TaskStatus(
                state=TaskState.INPUT_REQUIRED,
                message={"role": "agent", "content": {"type": "text",
                         "text": "Please specify a location for the weather forecast."}},
            )
            return task

        weather_text = self.get_weather(
            location=location,
            forecast_days=parse_forecast_days(text),
            include_current=True,
            include_hourly="hourly" in text.lower(),
            include_daily=True,
        )
        task.artifacts = text_artifact(weather_text)
        task.status = TaskStatus(state=TaskState.COMPLETED)
        return task


# Run the server
if __name__ == "__main__":
    weather_agent = WeatherAgent(google_a2a_compatible=True)
    logger.info("starting weather agent on port %s", config.WEATHER_AGENT_PORT)
    run_server(weather_agent, host=config.AGENT_HOST, port=config.WEATHER_AGENT_PORT)
