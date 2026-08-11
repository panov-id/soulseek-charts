# The official image ships the browsers and their system dependencies but not
# the Python package, so it is added here once and cached.
FROM mcr.microsoft.com/playwright/python:latest

ENV PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN pip install --break-system-packages playwright \
    && playwright install chromium

COPY take_screenshots.py /screenshot/take_screenshots.py

ENTRYPOINT ["python3", "/screenshot/take_screenshots.py"]
