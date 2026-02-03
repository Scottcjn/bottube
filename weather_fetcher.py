#!/usr/bin/env python3
"""
Weather Fetcher for SkyWatch AI bot.

Fetches current weather from Open-Meteo (free, no API key required),
rotates through 20 major US cities, and deduplicates against recent reports.
"""

import hashlib
import logging
import random
import time

import requests

log = logging.getLogger("weather-fetcher")

# 20 major US cities with coordinates
US_CITIES = [
    {"name": "New York City", "state": "NY", "lat": 40.7128, "lon": -74.0060},
    {"name": "Los Angeles", "state": "CA", "lat": 34.0522, "lon": -118.2437},
    {"name": "Chicago", "state": "IL", "lat": 41.8781, "lon": -87.6298},
    {"name": "Houston", "state": "TX", "lat": 29.7604, "lon": -95.3698},
    {"name": "Phoenix", "state": "AZ", "lat": 33.4484, "lon": -112.0740},
    {"name": "Philadelphia", "state": "PA", "lat": 39.9526, "lon": -75.1652},
    {"name": "San Antonio", "state": "TX", "lat": 29.4241, "lon": -98.4936},
    {"name": "San Diego", "state": "CA", "lat": 32.7157, "lon": -117.1611},
    {"name": "Dallas", "state": "TX", "lat": 32.7767, "lon": -96.7970},
    {"name": "San Jose", "state": "CA", "lat": 37.3382, "lon": -121.8863},
    {"name": "Austin", "state": "TX", "lat": 30.2672, "lon": -97.7431},
    {"name": "Miami", "state": "FL", "lat": 25.7617, "lon": -80.1918},
    {"name": "Denver", "state": "CO", "lat": 39.7392, "lon": -104.9903},
    {"name": "Seattle", "state": "WA", "lat": 47.6062, "lon": -122.3321},
    {"name": "Portland", "state": "OR", "lat": 45.5152, "lon": -122.6784},
    {"name": "Atlanta", "state": "GA", "lat": 33.7490, "lon": -84.3880},
    {"name": "Boston", "state": "MA", "lat": 42.3601, "lon": -71.0589},
    {"name": "Nashville", "state": "TN", "lat": 36.1627, "lon": -86.7816},
    {"name": "New Orleans", "state": "LA", "lat": 29.9511, "lon": -90.0715},
    {"name": "Baton Rouge", "state": "LA", "lat": 30.4515, "lon": -91.1871},
]

# WMO Weather Interpretation Codes -> human-readable descriptions
WMO_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
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
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
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


def _city_hash(city_name, date_str):
    """Deterministic hash for deduplication (city + date)."""
    return hashlib.sha256(f"{city_name.lower()}:{date_str}".encode()).hexdigest()[:16]


class WeatherFetcher:
    """Fetches current weather from Open-Meteo API."""

    API_URL = "https://api.open-meteo.com/v1/forecast"

    def fetch_current(self, city):
        """Fetch current weather for a city dict.

        Returns dict with: city, state, temp_f, feels_like_f, humidity,
        wind_mph, condition, daily_high_f, daily_low_f, or None on failure.
        """
        params = {
            "latitude": city["lat"],
            "longitude": city["lon"],
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "America/New_York",
            "forecast_days": 1,
        }
        try:
            r = requests.get(self.API_URL, params=params, timeout=15)
            if r.status_code != 200:
                log.warning("Open-Meteo returned %d for %s", r.status_code, city["name"])
                return None
            data = r.json()
        except Exception as e:
            log.warning("Open-Meteo fetch failed for %s: %s", city["name"], e)
            return None

        current = data.get("current", {})
        daily = data.get("daily", {})

        wmo_code = current.get("weather_code", 0)
        condition = WMO_CODES.get(wmo_code, f"Code {wmo_code}")

        return {
            "city": city["name"],
            "state": city["state"],
            "temp_f": round(current.get("temperature_2m", 0)),
            "feels_like_f": round(current.get("apparent_temperature", 0)),
            "humidity": round(current.get("relative_humidity_2m", 0)),
            "wind_mph": round(current.get("wind_speed_10m", 0)),
            "condition": condition,
            "wmo_code": wmo_code,
            "daily_high_f": round(daily.get("temperature_2m_max", [0])[0]),
            "daily_low_f": round(daily.get("temperature_2m_min", [0])[0]),
        }

    def pick_fresh_city(self, already_covered=None):
        """Pick a city not already covered today, preferring uncovered ones.

        Args:
            already_covered: set of city hashes that have been reported.

        Returns a city dict or None if all covered.
        """
        already_covered = already_covered or set()
        today = time.strftime("%Y-%m-%d")

        # Prefer uncovered cities
        uncovered = [
            c for c in US_CITIES
            if _city_hash(c["name"], today) not in already_covered
        ]
        if uncovered:
            return random.choice(uncovered)

        # All covered today — pick random for re-reporting
        return random.choice(US_CITIES)
