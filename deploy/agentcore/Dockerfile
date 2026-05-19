# syntax=docker/dockerfile:1.7
# AgentCore Runtime은 ARM64 컨테이너를 요구한다.
# 빌드: docker buildx build --platform linux/arm64 -t <ecr>/k8s-rca-agent:<tag> -f deploy/agentcore/Dockerfile .

# ============================================================
# Builder
# ============================================================
FROM --platform=linux/arm64 python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --target=/install ".[agentcore]"

# ============================================================
# Runtime
# ============================================================
FROM --platform=linux/arm64 python:3.11-slim

# uvx (uv) — stdio 모드로 EKS MCP server를 띄울 때 필요. http 모드만 쓰면 제거 가능.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && pip install --no-cache-dir uv \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r agent --gid=1000 && \
    useradd -r -g agent --uid=1000 --no-create-home --shell=/sbin/nologin agent

WORKDIR /app
COPY --from=builder /install /usr/local/lib/python3.11/site-packages

USER 1000:1000

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_LEVEL=INFO \
    AWS_REGION=us-west-2 \
    EKS_MCP_TRANSPORT=http

EXPOSE 8080

ENTRYPOINT ["python", "-m", "k8s_rca_agent.agentcore_app"]
