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
        """Handle CORS preflight headers"""
        pass

    def add_cors_headers(self, response):
        """Add CORS headers to response"""
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        return response

    def apply_rate_limit(self):
        """Apply rate limiting based on IP address"""
        client_ip = request.remote_addr
        current_time = datetime.now()

        # Get current request count for this IP
        request_data = rate_limit_store.get(client_ip, {'count': 0, 'reset_time': current_time})

        # Reset count if window has passed
        if current_time >= request_data['reset_time']:
            request_data = {'count': 0, 'reset_time': current_time + timedelta(minutes=15)}

        # Check if limit exceeded (100 requests per 15 minutes)
        if request_data['count'] >= 100:
            raise TooManyRequests('Rate limit exceeded')

        # Increment count
        request_data['count'] += 1
        rate_limit_store.set(client_ip, request_data)

    def handle_jwt_auth(self):
        """Handle JWT authentication for protected routes"""
        # Skip auth for login/register endpoints
        if request.endpoint in ['mobile_api.mobile_login', 'mobile_api.mobile_register']:
            return

        # Check for JWT token in mobile API routes
        if request.path.startswith('/api/mobile/'):
            token = request.headers.get('Authorization')
            if token and token.startswith('Bearer '):
                try:
                    token = token[7:]
                    jwt_secret = os.environ['JWT_SECRET']
                    data = jwt.decode(token, jwt_secret, algorithms=['HS256'])
                    g.user_id = data.get('user_id')
                    g.username = data.get('username')
                except (jwt.InvalidTokenError, KeyError):
                    pass

    def set_api_version(self):
        """Set API version in response headers"""
        g.api_version = '1.0'
