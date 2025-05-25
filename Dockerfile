FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for Pillow and ffmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies with troubleshooting steps
RUN pip install --upgrade pip && \
    # Install packages one by one to identify problematic packages
    pip install Flask==3.0.2 && \
    pip install Werkzeug==3.0.1 && \
    pip install Pillow==10.4.0 && \
    pip install gunicorn==21.2.0 && \
    pip install pytest==7.3.1 && \
    pip install pytest-cov==4.1.0 && \
    # Install ffmpeg-python with specific pip options
    pip install --no-deps ffmpeg-python==0.2.0 && \
    pip install --no-build-isolation ffmpeg-python==0.2.0

# Copy application code
COPY . .

# Create uploads directory
RUN mkdir -p uploads

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Expose port
EXPOSE 5001

# Run with gunicorn (production server)
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "app:app"]