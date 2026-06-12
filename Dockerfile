FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY scripts ./scripts

EXPOSE 8000

CMD ["uvicorn", "health_agent_bridge.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
