FROM python:3.12-slim AS proto-builder

ENV PIP_NO_CACHE_DIR=1
WORKDIR /build

# Keep protoc's Python gencode on the same protobuf major as the runtime.
# Installing grpcio-tools alone may resolve protobuf 7 even though pyproject
# intentionally pins the application runtime to protobuf 6.
RUN pip install "grpcio-tools>=1.74,<2" "protobuf>=6.31,<7"
COPY proto/nest.proto ./proto/nest.proto
COPY scripts/generate_clova_proto.py ./scripts/generate_clova_proto.py
COPY silki_ai/generated/__init__.py ./silki_ai/generated/__init__.py
RUN python scripts/generate_clova_proto.py

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /uvx /bin/

RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
COPY silki_ai ./silki_ai
COPY --from=proto-builder /build/silki_ai/generated ./silki_ai/generated
COPY prompts ./prompts
RUN uv sync --frozen
RUN python -c "import sys; from silki_ai.generated import nest_pb2; sys.modules['nest_pb2'] = nest_pb2; from silki_ai.generated import nest_pb2_grpc"

EXPOSE 8000
CMD ["uvicorn", "silki_ai.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
