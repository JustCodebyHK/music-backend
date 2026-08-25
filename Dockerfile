FROM python:3.11-slim

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