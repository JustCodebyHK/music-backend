FROM python:3.11-slim

# Disable all proxy settings at the system level to prevent "Tunnel connection failed" errors
ENV HTTP_PROXY=""
ENV HTTPS_PROXY=""
ENV ALL_PROXY=""
ENV http_proxy=""
ENV https_proxy=""
ENV all_proxy=""
ENV NO_PROXY="*"
ENV no_proxy="*"
ENV PIP_NO_PROXY="*"

# Create .curlrc to prevent curl from using any proxy
RUN mkdir -p /root && echo "noproxy = *" > /root/.curlrc

# Install system dependencies, git, ffmpeg, and curl
RUN apt-get update && apt-get install -y \
    git \
    ffmpeg \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Deno JS runtime required by yt-dlp for YouTube challenge deciphering
RUN curl -fsSL https://deno.land/x/install/install.sh | sh
ENV DENO_INSTALL="/root/.deno"
ENV PATH="$DENO_INSTALL/bin:$PATH"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]