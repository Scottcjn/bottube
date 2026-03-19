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
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Version'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age'] = '3600'
        return response
    
    def apply_rate_limit(self):
        client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        endpoint = request.endpoint or 'unknown'
        
        # Different limits for different endpoints
        limits = {
            'auth': {'requests': 10, 'window': 300},     # 10 requests per 5 minutes
            'upload': {'requests': 5, 'window': 300},    # 5 uploads per 5 minutes
            'default': {'requests': 100, 'window': 60}   # 100 requests per minute
        }
        
        limit_key = 'auth' if 'auth' in endpoint else 'upload' if 'upload' in endpoint else 'default'
        limit_config = limits[limit_key]
        
        key = f"{client_ip}:{limit_key}"
        current_time = time.time()
        
        # Clean old entries
        if key in rate_limit_store:
            rate_limit_store[key] = [t for t in rate_limit_store[key] if current_time - t < limit_config['window']]
        else:
            rate_limit_store[key] = []
        
        # Check rate limit
        if len(rate_limit_store[key]) >= limit_config['requests']:
            raise TooManyRequests('Rate limit exceeded')
        
        # Add current request
        rate_limit_store[key].append(current_time)
    
    def handle_jwt_auth(self):
        auth_header = request.headers.get('Authorization')
        g.mobile_user = None
        g.jwt_token = None
        
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            try:
                payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
                user_id = payload.get('user_id')
                
                if user_id:
                    from bottube_server import get_db
                    db = get_db()
                    user = db.execute(
                        'SELECT * FROM users WHERE id = ?', (user_id,)
                    ).fetchone()
                    
                    if user:
                        g.mobile_user = dict(user)
                        g.jwt_token = token
                        
            except jwt.ExpiredSignatureError:
                pass  # Token expired, user remains None
            except jwt.InvalidTokenError:
                pass  # Invalid token, user remains None
    
    def set_api_version(self):
        version = request.headers.get('X-API-Version', '1.0')
        g.api_version = version

def jwt_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.mobile_user:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated

def generate_jwt_token(user_id, expires_in=86400):
    payload = {
        'user_id': user_id,
        'exp': time.time() + expires_in,
        'iat': time.time()
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')

def api_response(data=None, message=None, status=200, error=None):
    response_data = {
        'success': status < 400,
        'timestamp': int(time.time())
    }
    
    if data is not None:
        response_data['data'] = data
    
    if message:
        response_data['message'] = message
    
    if error:
        response_data['error'] = error
    
    if hasattr(g, 'api_version'):
        response_data['api_version'] = g.api_version
    
    return jsonify(response_data), status