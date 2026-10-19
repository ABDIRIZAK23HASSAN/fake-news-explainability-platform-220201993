# Build context = repository root:  docker compose build backend
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY scripts/bootstrap.py scripts/bootstrap.py
WORKDIR /srv/backend
RUN useradd -m app && mkdir -p storage && chown -R app /srv
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=10 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
