FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py .
# Cloud Run は PORT 環境変数で待ち受けポートを渡す
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
