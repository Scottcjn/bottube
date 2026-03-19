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
    
    def apply_rate_limit(self):
        client_ip = request.remote_addr
        current_time = time.time()
        
        # Clean old entries
        rate_limit_store[client_ip] = [
            timestamp for timestamp in rate_limit_store.get(client_ip, [])
            if current_time - timestamp < 60  # 1 minute window
        ]
        
        # Check rate limit (100 requests per minute)
        if len(rate_limit_store.get(client_ip, [])) >= 100:
            raise TooManyRequests('Rate limit exceeded')
        
        # Add current request
        rate_limit_store.setdefault(client_ip, []).append(current_time)
    
    def handle_jwt_auth(self):
        # Skip auth for login/register endpoints
        if request.endpoint in ['mobile_api.mobile_login', 'mobile_api.mobile_register']:
            return
        
        token = request.headers.get('Authorization')
        if token and token.startswith('Bearer '):
            try:
                token = token[7:]
                data = jwt.decode(token, 'your-secret-key', algorithms=['HS256'])
                g.user_id = data['user_id']
                g.username = data['username']
            except jwt.InvalidTokenError:
                pass
    
    def set_api_version(self):
        g.api_version = 'v1'