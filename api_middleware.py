# SPDX-License-Identifier: MIT
import time
import jwt
import os
from functools import wraps
from flask import request, jsonify, g, current_app
from werkzeug.exceptions import TooManyRequests
from collections import defaultdict
from datetime import datetime, timedelta
import sqlite3

# Rate limiting storage with TTL cleanup
class TTLDict:
    def __init__(self, ttl_seconds=3600):
        self.data = {}
        self.ttl = ttl_seconds

    def get(self, key, default=None):
        self.cleanup()
        return self.data.get(key, {}).get('value', default)

    def set(self, key, value):
        self.cleanup()
        self.data[key] = {
            'value': value,
            'timestamp': datetime.now()
        }

    def cleanup(self):
        now = datetime.now()
        expired_keys = []
        for key, item in self.data.items():
            if now - item['timestamp'] > timedelta(seconds=self.ttl):
                expired_keys.append(key)

        for key in expired_keys:
            del self.data[key]

rate_limit_store = TTLDict(ttl_seconds=3600)


class APIMiddleware:
    def __init__(self, app=None):
        self.app = app
        if app:
            self.init_app(app)

    def init_app(self, app):
        app.before_request(self.before_request)
        app.after_request(self.after_request)

    def before_request(self):
        # Skip middleware for non-API routes
        if not request.path.startswith('/api/'):
            return

        # Apply CORS headers
        self.handle_cors()

        # Handle preflight requests
        if request.method == 'OPTIONS':
            return '', 200

        # Apply rate limiting
        self.apply_rate_limit()

        # Handle JWT authentication
        self.handle_jwt_auth()

        # Set API version
        self.set_api_version()

    def after_request(self, response):
        # Add CORS headers to all API responses
        if request.path.startswith('/api/'):
            self.add_cors_headers(response)
        return response

    def handle_cors(self):
        # Set CORS headers for preflight requests
        pass

    def add_cors_headers(self, response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response

    def apply_rate_limit(self):
        # Get client identifier (IP address)
        client_id = request.remote_addr
        current_time = datetime.now()

        # Get current request count for this client
        current_count = rate_limit_store.get(client_id, 0)

        # Rate limit: 100 requests per hour
        if current_count >= 100:
            raise TooManyRequests('Rate limit exceeded')

        # Increment counter
        rate_limit_store.set(client_id, current_count + 1)

    def handle_jwt_auth(self):
        # JWT auth is handled per-route, not globally
        pass

    def set_api_version(self):
        g.api_version = '1.0'
