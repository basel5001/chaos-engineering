FROM python:3.14-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/
COPY manifests/ manifests/
COPY pyproject.toml .

# Install the package
RUN pip install --no-cache-dir -e .

# Non-root user
RUN useradd -m -r chaos && chown -R chaos:chaos /app
USER chaos

ENTRYPOINT ["python", "-m", "src.runner.cli"]
CMD ["--help"]
