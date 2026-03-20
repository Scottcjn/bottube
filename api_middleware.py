import time
import jwt
from functools import wraps
from flask import request, jsonify, g, current_app
from werkzeug.exceptions import TooManyRequests
import sqlite3

# Rate limiting storage
rate_limit_store = {}


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
        response.headers['Access-Control-Max-Age'] = '86400'

    def apply_rate_limit(self):
        client_ip = request.environ.get('REMOTE_ADDR')
        current_time = time.time()

        # Rate limit: 100 requests per minute per IP
        window_size = 60  # 1 minute
        max_requests = 100

        if client_ip not in rate_limit_store:
            rate_limit_store[client_ip] = []

        # Clean old requests outside the window
        rate_limit_store[client_ip] = [
            req_time for req_time in rate_limit_store[client_ip]
            if current_time - req_time < window_size
        ]

        # Check if limit exceeded
        if len(rate_limit_store[client_ip]) >= max_requests:
            raise TooManyRequests('Rate limit exceeded')

        # Add current request
        rate_limit_store[client_ip].append(current_time)

    def handle_jwt_auth(self):
        # Skip auth for public endpoints
        public_endpoints = ['/api/mobile/auth/login', '/api/mobile/auth/register']
        if request.path in public_endpoints:
            return

        token = request.headers.get('Authorization')
        if not token:
            return  # Let individual routes handle auth requirements

        try:
            if token.startswith('Bearer '):
                token = token[7:]
            data = jwt.decode(token, 'your-secret-key', algorithms=['HS256'])
            g.user_id = data['user_id']
            g.username = data['username']
        except jwt.InvalidTokenError:
            g.user_id = None
            g.username = None

    def set_api_version(self):
        g.api_version = '1.0'
