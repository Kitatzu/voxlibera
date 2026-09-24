FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY voxlibera ./voxlibera
RUN pip install --no-cache-dir .

COPY rooms.yaml ./
COPY web ./web
COPY samples ./samples

ENV VOXLIBERA_ROOMS_FILE=/app/rooms.yaml \
    VOXLIBERA_WEB_DIR=/app/web \
    VOXLIBERA_SAMPLES_DIR=/app/samples \
    VOXLIBERA_DATA_DIR=/data

VOLUME ["/data"]
EXPOSE 8000
CMD ["voxlibera-server"]
