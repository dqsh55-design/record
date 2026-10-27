FROM python:3.12-slim
WORKDIR /app
COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
COPY server /app/server
COPY scripts /app/scripts
COPY data/official-realtime.json /app/data/official-realtime.json
COPY data/official-access-policy.json /app/data/official-access-policy.json
COPY index.html /app/index.html
RUN mkdir -p /data && chown 10001:10001 /data
USER 10001:10001
ENV RECORD_CACHE_PATH=/data/official-cache.sqlite3
EXPOSE 8000
CMD ["gunicorn", "server.app:create_app()", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "8", "--timeout", "75"]
