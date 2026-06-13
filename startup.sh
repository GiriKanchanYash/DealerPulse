#!/bin/bash
set -e
 
python -m streamlit run app.py \
  --server.port 8000 \
  --server.address 0.0.0.0 \
  --server.enableCORS false \
  --server.enableXsrfProtection false \
  --server.headless true \
  --logger.level=warning \
  --client.showErrorDetails=true