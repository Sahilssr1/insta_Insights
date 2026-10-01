# InsightBoard backend — Docker image for free hosts (Hugging Face Spaces, etc.)
#
# Hugging Face Spaces (Docker SDK) expects the container to listen on 7860.
# All configuration comes from environment variables / Space secrets;
# see backend/.env.example for the full list. The app runs its alembic
# migrations automatically on startup, so a fresh/empty database is fine.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/

EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--app-dir", "/app/backend"]
