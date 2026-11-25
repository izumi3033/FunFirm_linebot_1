FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common/ common/
COPY report_bot/ report_bot/
COPY assistant_bot/ assistant_bot/
# どちらのボットを動かすかは APP_MODULE で選ぶ（deploy.sh が設定する）
# Cloud Run は PORT 環境変数で待ち受けポートを渡す
CMD exec uvicorn ${APP_MODULE:-report_bot.main:app} --host 0.0.0.0 --port ${PORT:-8080}
