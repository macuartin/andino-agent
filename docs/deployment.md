# Deployment

## Local Development

```bash
cd andino-agent
pip install -e ".[bedrock]"

cd ../examples/researcher
python -m andino_sdk agent.yaml
```

## Docker

Each agent is a standalone container. The Dockerfile pattern:

```dockerfile
FROM python:3.12-slim
WORKDIR /app

# Install SDK
COPY andino-agent/ /sdk/
RUN pip install --no-cache-dir /sdk[bedrock] && rm -rf /sdk

# Copy agent config
COPY examples/researcher/ .

CMD ["python", "-m", "andino_sdk", "agent.yaml"]
```

Build context must be the repo root so both `andino-agent/` and `examples/` are accessible.

## Docker Compose

```yaml
# docker-compose.agents.yml
services:
  researcher:
    build:
      context: .
      dockerfile: examples/researcher/Dockerfile
    ports:
      - "8101:8101"
    env_file:
      - .env

  architect:
    build:
      context: .
      dockerfile: examples/architect/Dockerfile
    ports:
      - "8102:8102"
    env_file:
      - .env

  coder:
    build:
      context: .
      dockerfile: examples/coder/Dockerfile
    ports:
      - "8103:8103"
    env_file:
      - .env

  reviewer:
    build:
      context: .
      dockerfile: examples/reviewer/Dockerfile
    ports:
      - "8104:8104"
    env_file:
      - .env
```

### Commands

```bash
# Build all agents
docker compose -f docker-compose.agents.yml build

# Start all agents
docker compose -f docker-compose.agents.yml up -d

# Start one agent
docker compose -f docker-compose.agents.yml up researcher -d

# View logs
docker compose -f docker-compose.agents.yml logs researcher -f

# Rebuild after SDK changes
docker compose -f docker-compose.agents.yml build researcher
docker compose -f docker-compose.agents.yml up researcher -d
```

## Environment Variables

Create a `.env` file with your provider credentials:

```bash
# AWS Bedrock
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=...          # if using SSO/temporary credentials
AWS_REGION=us-east-1

# Or Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Or OpenAI
OPENAI_API_KEY=sk-...
```

## Session Persistence

If using sessions, mount a volume for the storage directory:

```yaml
services:
  researcher:
    volumes:
      - researcher-sessions:/app/.sessions

volumes:
  researcher-sessions:
```

Or configure a custom path in `agent.yaml`:

```yaml
session:
  storage_dir: /data/sessions
```

## Creating a New Agent

1. Create the agent directory:
```bash
mkdir examples/my-agent
```

2. Write `agent.yaml`:
```yaml
name: my-agent
version: "1.0.0"
description: "What this agent does"

model:
  provider: bedrock
  model_id: us.anthropic.claude-sonnet-4-6
  max_tokens: 4096

system_prompt: ./system_prompt.md

tools:
  - strands_tools.http_request:http_request

server:
  port: 8105

limits:
  max_concurrent_tasks: 1
  task_timeout_seconds: 600
```

3. Write `system_prompt.md` with the agent's persona and instructions.

4. Write `Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY andino-agent/ /sdk/
RUN pip install --no-cache-dir /sdk[bedrock] && rm -rf /sdk
COPY examples/my-agent/ .
CMD ["python", "-m", "andino_sdk", "agent.yaml"]
```

5. Add to `docker-compose.agents.yml`:
```yaml
  my-agent:
    build:
      context: .
      dockerfile: examples/my-agent/Dockerfile
    ports:
      - "8105:8105"
    env_file:
      - .env
```

## Port Conventions

| Agent | Port |
|---|---|
| researcher | 8101 |
| architect | 8102 |
| coder | 8103 |
| reviewer | 8104 |
| (next agent) | 8105+ |
