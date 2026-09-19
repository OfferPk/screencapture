# Playwright + cron image for scheduled Google Maps / Places scrapes
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

ENV TZ=Asia/Karachi
RUN apt-get update && apt-get install -y cron tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY maps/ ./maps/
COPY crontab /etc/cron.d/gmaps-cron
RUN chmod 0644 /etc/cron.d/gmaps-cron \
    && crontab /etc/cron.d/gmaps-cron \
    && mkdir -p /app/out

CMD ["cron", "-f"]
