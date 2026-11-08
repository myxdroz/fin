FROM python:3.12-slim

ARG APP_VERSION=unknown
ENV APP_VERSION=$APP_VERSION

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data

ENV FIN_DATABASE_URL=sqlite:////data/fin.db \
    FIN_SYNC_ON_STARTUP=true \
    FIN_SCHEDULER_ENABLED=true

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/api/health', timeout=5).raise_for_status()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
