# QorTime agent verify API (qortime_ai/agent_api). Built Oct 28 2026, during the hackathon week.
# Read-only: serves GET /agent/v1/* and a stateless MCP endpoint at /agent/mcp. No secrets needed.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY qortime_ai ./qortime_ai
RUN pip install --no-cache-dir '.[agent-api]' && useradd -r -u 10001 app
USER app
ENV PORT=8080
CMD ["sh", "-c", "uvicorn qortime_ai.agent_api.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
