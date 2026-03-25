FROM python:3.12-slim
# Environment settings
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Working directory
WORKDIR /code
# Install system dependencies (build tools, etc.)
# Added libraries for Pillow/images (libjpeg-dev, zlib1g-dev)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
# Install Python packages
COPY requirements.txt /code/
RUN pip install --upgrade pip && pip install -r requirements.txt
# Copy project files
COPY . /code/
