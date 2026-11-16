# synex-api: FastAPI. The sign-in to LinkedIn runs a real browser inside the API process, so the API uses the same
# Playwright image (browser and its system libraries) as the worker. Railway: root directory "backend".
FROM mcr.microsoft.com/playwright/python:v1.65.2-noble
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/backend
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
COPY certs ./certs
# The browser build must match the pinned Playwright (requirements.txt): fail the image build now, not the first LinkedIn
# sign-in later. The server also checks at start (SYNEX_CHECK_BROWSER) and refuses to run without a working browser.
ENV SYNEX_CHECK_BROWSER=1
RUN python -c "from playwright.sync_api import sync_playwright as s; p = s().start(); b = p.chromium.launch(headless=True); b.new_page().goto('about:blank'); b.close(); p.stop(); print('browser ok')"
EXPOSE 8000
# Railway sets PORT; fall back to 8000 for a local run.
CMD ["sh", "-c", "python -m app.check_env && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
