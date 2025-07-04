#!/bin/bash

# Run Alembic migration
echo "Running Alembic migrations..."
alembic upgrade head

# Start Uvicorn server
echo "Starting Uvicorn server..."
gunicorn -k uvicorn.workers.UvicornWorker -b 0.0.0.0:5000 src.main:app