#!/bin/bash
# Start Domus backend server

# Navigate to project root
cd "$(dirname "$0")"

# Set Python path to include shared module
export PYTHONPATH="${PWD}:${PYTHONPATH}"

# Start uvicorn
cd be
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
