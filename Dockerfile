# =============================================================================
# Dockerfile - ProcureSpendIQ Analytics
# Optimised for Azure Web App (Linux container)
# =============================================================================

FROM python:3.11-slim

# Install ODBC Driver 18 for SQL Server
RUN apt-get update && apt-get install -y \
        curl \
        apt-transport-https \
        gnupg2 \
        unixodbc-dev \
    && curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/12/prod.list \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Azure Web App injects PORT env variable at runtime
ENV PORT=8501

# Non-root user for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl --fail http://localhost:${PORT}/_stcore/health || exit 1

# Shell form so $PORT is expanded at runtime by Azure
CMD streamlit run app.py \
    --server.port=${PORT} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false
