FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Install dependencies first so Docker can cache this slow layer.
# It only reruns when requirements.txt changes, not on every code edit.
COPY requirements.txt .

# CPU-only PyTorch first (Cloud Run has no GPU), which keeps the image much smaller.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements.txt

# Copy the app code last, since it changes most often.
COPY . .

# Cloud Run sends traffic to the port in $PORT.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 120 app:app
