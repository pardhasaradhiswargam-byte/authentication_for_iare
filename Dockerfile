# Use official Python runtime
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (Render uses dynamic PORT)
EXPOSE 10000

# Environment variables
ENV PYTHONUNBUFFERED=1

# Run with gunicorn
CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --threads 4 app:app
