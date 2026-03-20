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
        origin = request.headers.get('Origin')
        allowed_origins = [
            'http://localhost:19006',  # Expo dev server
            'exp://localhost:19000',   # Expo app
            'capacitor://localhost',   # Capacitor apps
            'ionic://localhost',       # Ionic apps
        ]

        # Allow any localhost origin for development
        if origin and ('localhost' in origin or origin in allowed_origins):
            g.cors_origin = origin
        else:
            g.cors_origin = None

    def add_cors_headers(self, response):
        if hasattr(g, 'cors_origin') and g.cors_origin:
            response.headers['Access-Control-Allow-Origin'] = g.cors_origin

        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age'] = '3600'
        return response

    def apply_rate_limit(self):
        client_ip = request.remote_addr
        current_time = time.time()

        # Get current request count for this IP
        request_data = rate_limit_store.get(client_ip, {'count': 0, 'reset_time': current_time + 60})

        # Reset counter if time window has passed
        if current_time > request_data['reset_time']:
            request_data = {'count': 1, 'reset_time': current_time + 60}
        else:
            request_data['count'] += 1

        # Check if rate limit exceeded (100 requests per minute)
        if request_data['count'] > 100:
            raise TooManyRequests('Rate limit exceeded')

        # Store updated count
        rate_limit_store.set(client_ip, request_data)

    def handle_jwt_auth(self):
        # Skip auth for login/register endpoints
        if request.path in ['/api/mobile/auth/login', '/api/mobile/auth/register']:
            return

        token = request.headers.get('Authorization')
        if token and token.startswith('Bearer '):
            try:
                token = token[7:]
                jwt_secret = os.environ.get('JWT_SECRET', 'fallback-secret-key')
                data = jwt.decode(token, jwt_secret, algorithms=['HS256'])
                g.user_id = data['user_id']
                g.username = data['username']
            except jwt.InvalidTokenError:
                g.user_id = None
                g.username = None

    def set_api_version(self):
        g.api_version = '1.0'
