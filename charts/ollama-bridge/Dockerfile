FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

# Install production dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY main.py .

CMD ["python3", "main.py"]
