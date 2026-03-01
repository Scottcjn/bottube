FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    flask>=2.0.0 \
    markupsafe \
    werkzeug \
    requests>=2.20.0 \
    pillow \
    python-magic

# Copy application files
COPY . .

# Create necessary directories
RUN mkdir -p /app/videos /app/thumbnails /app/avatars

# Expose port
EXPOSE 8097

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8097/ || exit 1

# Run the server
CMD ["python", "bottube_server.py"]
