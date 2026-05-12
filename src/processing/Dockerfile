FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY processing/ processing/

RUN pip install --no-cache-dir -e .

CMD ["python", "-m", "processing.main"]
