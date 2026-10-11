# Legacy Player shared server and problem-report receiver. Build from the repository root:
#   docker build -f deploy/Dockerfile -t legacy-player-server .
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# /data/reports exists in the image (owned by lp) so the compose file's lp-reports volume starts out writable by uid 10001;
# a volume mounted on a path the image does not have is created owned by root and the receiver could not write to it.
RUN useradd --create-home --uid 10001 lp && mkdir -p /data/reports && chown -R lp:lp /data
WORKDIR /app
COPY server ./server
COPY runtime ./runtime
COPY launcher/__init__.py launcher/servercode.py ./launcher/
USER lp
VOLUME /data
EXPOSE 8765 8790
# Default: the shared server. The compose file overrides this for the report receiver.
CMD ["python", "-m", "server.cli", "start", "--share", "--port", "8765", "--state-dir", "/data/state", "--replay-dir", "/data/replays"]
