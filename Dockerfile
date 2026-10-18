FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    KLASSENKAMPF_HEADLESS=1 KLASSENKAMPF_DATA_DIR=/data
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN groupadd --gid 10001 game && useradd --uid 10001 --gid game --no-create-home game \
    && mkdir /data && chown game:game /data
COPY --chown=game:game *.py ./
COPY --chown=game:game games/ ./games/
COPY --chown=game:game static/ ./static/
COPY --chown=game:game templates/ ./templates/
USER 10001:10001
EXPOSE 8080
STOPSIGNAL SIGTERM
CMD ["python", "server.py", "--headless", "--host", "0.0.0.0", "--port", "8080"]
