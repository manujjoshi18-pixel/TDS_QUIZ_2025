FROM mcr.microsoft.com/devcontainers/python:3.10

# Install system dependencies for Playwright/Chromium
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libgbm1 libasound2 libxcomposite1 libxrandr2 libxdamage1 \
    libxfixes3 libcups2 libatspi2.0-0 libx11-xcb1 libpangocairo-1.0-0 \
    libgtk-3-0

RUN pip install playwright && playwright install-deps

WORKDIR /workspace
