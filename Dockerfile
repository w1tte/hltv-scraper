FROM python:3.11-slim

# Install Chrome + Xvfb + tini (init for reaping zombie processes)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg2 tini \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    google-chrome-stable \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

ENV DISPLAY=:99

WORKDIR /app

COPY pyproject.toml ./
COPY src/ src/
COPY migrations/ migrations/

RUN pip install --no-cache-dir -e .

# Data volume for logs and HTML archive
VOLUME /app/data

# tini as PID 1 reaps zombie Chrome processes
ENTRYPOINT ["/usr/bin/tini", "--"]

# Start Xvfb then run the scraper
CMD ["sh", "-c", "Xvfb :99 -screen 0 1280x900x24 -nolisten tcp & sleep 1 && exec hltv-scraper"]
