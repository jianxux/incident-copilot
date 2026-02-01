FROM python:3.11-slim

WORKDIR /app

# Install dependencies from requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ src/

# Railway uses dynamic PORT env var
ENV PORT=8000

# Run with shell form to allow variable expansion
CMD uvicorn src.main:app --host 0.0.0.0 --port $PORT
