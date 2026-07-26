FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
RUN pip install --no-cache-dir asyncpg python-dotenv "mcp>=1.2.0"

COPY backend/ backend/
COPY mcp_server/ mcp_server/

ENV PYTHONUNBUFFERED=1
WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
