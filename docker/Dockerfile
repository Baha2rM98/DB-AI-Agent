FROM python:3.14-slim

# Build the runtime in a predictable working directory so both local
# development and container execution use the same import paths.
WORKDIR /app

# Install only the small set of system packages needed for building wheels
# and probing the application in health checks.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first to maximize Docker layer reuse.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

# Copy the application source after dependencies are installed.
COPY app /app/app

# Run the container as a non-root user for safer defaults.
RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app
ENV HOST=0.0.0.0
ENV PORT=8000

# Probe the root endpoint so Docker can tell when the API is ready.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/')" || exit 1

# Start uvicorn directly instead of shelling through a Python script.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
