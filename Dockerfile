# Multi-stage build for Udemy Course Enroller
FROM python:3.11-slim as builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH
ENV DEPLOYMENT_ENV=server

# Copy application code
COPY . .

# Create non-root user and set up directories
RUN groupadd --system --gid 1001 appuser && \
    useradd --system --gid appuser --uid 1001 --create-home appuser && \
    mkdir -p logs Courses data && \
    chmod +x docker-entrypoint.sh && \
    chown -R appuser:appuser /app

USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Run with entrypoint
ENTRYPOINT ["./docker-entrypoint.sh"]
