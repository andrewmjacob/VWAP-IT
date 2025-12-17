FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md /app/
RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir .
COPY src /app/src
ENTRYPOINT ["python", "-m", "tip.cli"]
