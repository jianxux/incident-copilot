FROM python:3.11-slim

WORKDIR /app

# Copy source files first (needed for pip install)
COPY pyproject.toml .
COPY src/ src/

# Install dependencies
RUN pip install --no-cache-dir .

# Run
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
