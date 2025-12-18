FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psycopg and healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install pinned Python dependencies first (better caching)
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY pyproject.toml README.md /app/
COPY src /app/src

# Install the package itself (no deps, already installed)
RUN pip install --no-cache-dir --no-deps -e .

ENTRYPOINT ["python", "-m", "tip.cli"]
