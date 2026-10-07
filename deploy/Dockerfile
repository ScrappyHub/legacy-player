# Legacy Player shared server and problem-report receiver. Build from the repository root:
#   docker build -f deploy/Dockerfile -t legacy-player-server .
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home --uid 10001 lp && mkdir -p /data && chown lp /data
WORKDIR /app
COPY server ./server
COPY runtime ./runtime
COPY launcher/__init__.py launcher/servercode.py ./launcher/
USER lp
VOLUME /data
EXPOSE 8765 8790
# Default: the shared server. The compose file overrides this for the report receiver.
CMD ["python", "-m", "server.cli", "start", "--share", "--port", "8765", "--state-dir", "/data/state", "--replay-dir", "/data/replays"]
