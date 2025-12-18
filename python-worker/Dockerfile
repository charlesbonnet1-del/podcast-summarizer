FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for pydub and Azure Speech
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libssl-dev \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose HTTP port
EXPOSE 8080

# Run HTTP server
CMD ["python", "server.py"]
