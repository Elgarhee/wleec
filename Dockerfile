FROM python:3.12-slim-bookworm

WORKDIR /usr/src/app

RUN chmod 777 /usr/src/app

# Install standard whitelisted utilities and binaries
RUN apt-get update && apt-get install -y --no-install-recommends \
    aria2 \
    ffmpeg \
    p7zip-full \
    cpulimit \
    git \
    curl \
    unzip \
    ca-certificates \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Install official rclone
RUN curl https://rclone.org/install.sh | bash

# Install uv for package management
RUN pip install uv

RUN uv venv --system-site-packages

COPY requirements.txt .
RUN uv pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["bash", "start.sh"]

