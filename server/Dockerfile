FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
# Render assigns PORT (defaults to 10000) and expects the container to bind to
# it; the shell form here lets $PORT expand, falling back to 8000 locally.
CMD ["sh", "-c", "uvicorn main:asgi_app --host 0.0.0.0 --port ${PORT:-8000}"]
