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
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age'] = '86400'

    def apply_rate_limit(self):
        client_ip = request.environ.get('REMOTE_ADDR')
        current_time = time.time()

        # Clean old entries
        self.cleanup_rate_limit_store(current_time)

        # Check rate limit
        if client_ip in rate_limit_store:
            requests = rate_limit_store[client_ip]
            # Allow 100 requests per minute
            if len([r for r in requests if current_time - r < 60]) >= 100:
                raise TooManyRequests()

        # Record request
        if client_ip not in rate_limit_store:
            rate_limit_store[client_ip] = []
        rate_limit_store[client_ip].append(current_time)

    def cleanup_rate_limit_store(self, current_time):
        for ip in list(rate_limit_store.keys()):
            rate_limit_store[ip] = [t for t in rate_limit_store[ip] if current_time - t < 60]
            if not rate_limit_store[ip]:
                del rate_limit_store[ip]

    def handle_jwt_auth(self):
        # Only apply JWT auth to protected endpoints
        protected_paths = ['/api/mobile/profile', '/api/mobile/protected']
        if not any(request.path.startswith(path) for path in protected_paths):
            return

        token = request.headers.get('Authorization')
        if not token:
            return

        try:
            if token.startswith('Bearer '):
                token = token[7:]
            data = jwt.decode(token, 'your-secret-key', algorithms=['HS256'])
            g.user_id = data['user_id']
            g.username = data['username']
        except jwt.InvalidTokenError:
            pass

    def set_api_version(self):
        g.api_version = 'v1'
