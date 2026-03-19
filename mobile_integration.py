from flask import Flask
from api_middleware import APIMiddleware
from mobile_api import mobile_api


def setup_mobile_integration(app: Flask):
    """
    Set up mobile API integration for the BoTTube Flask app.
    This function should be called from bottube_server.py
    """
    # Initialize API middleware
    middleware = APIMiddleware()
    middleware.init_app(app)
    
    # Register mobile API blueprint
    app.register_blueprint(mobile_api)
    
    # Add mobile-specific error handlers
    @app.errorhandler(429)
    def rate_limit_handler(e):
        return {'error': 'Rate limit exceeded', 'retry_after': 60}, 429
    
    @app.errorhandler(404)
    def not_found_handler(e):
        if '/api/' in str(e):
            return {'error': 'Endpoint not found'}, 404
        return e
    
    @app.errorhandler(500)
    def internal_error_handler(e):
        if '/api/' in str(e):
            return {'error': 'Internal server error'}, 500
        return e
    
    return app