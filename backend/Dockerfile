# synex-api: FastAPI. The sign-in to LinkedIn runs a real browser inside the API process, so the API uses the same
# Playwright image (browser and its system libraries) as the worker. Railway: root directory "backend".
FROM mcr.microsoft.com/playwright/python:v1.65.2-noble
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/backend
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
COPY certs ./certs
EXPOSE 8000
# Railway sets PORT; fall back to 8000 for a local run.
CMD ["sh", "-c", "python -m app.check_env && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
