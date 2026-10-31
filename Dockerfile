FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DAYTODAY_DB=/app/data/daytoday.db

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY web ./web
COPY eval ./eval
COPY data ./data

ENV PYTHONPATH=/app/src
RUN python -m daytoday.cli seed

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/health')"
CMD ["uvicorn", "daytoday.api:app", "--host", "0.0.0.0", "--port", "8000"]
