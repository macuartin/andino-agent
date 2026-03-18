# Deployment

For installation, CLI usage, and ANDINO_HOME setup, see [Getting Started](getting-started.md).

## Host Deployment (Bare Metal / VM)

### Install

```bash
python3 -m venv ~/.local/share/andino/venv
source ~/.local/share/andino/venv/bin/activate
pip install andino-agent[bedrock]
```

### Create and configure an agent

```bash
andino init researcher
vim ~/.andino/agents/researcher/agent.yaml
vim ~/.andino/agents/researcher/.env
```

### Run with systemd (recommended)

```bash
# Install the systemd user unit
mkdir -p ~/.config/systemd/user
cp deploy/andino@.service ~/.config/systemd/user/
systemctl --user daemon-reload

# Start the agent
systemctl --user start andino@researcher

# Enable on login
systemctl --user enable andino@researcher

# View logs
journalctl --user -u andino@researcher -f

# Manage
systemctl --user status andino@researcher
systemctl --user restart andino@researcher
systemctl --user stop andino@researcher
```

### Enable lingering (keep running after logout)

```bash
loginctl enable-linger $USER
```

This allows user services to keep running even when you log out.

## Local Development

```bash
cd andino-agent
pip install -e ".[bedrock]"
andino run ./examples/researcher/agent.yaml
```

## Docker

Each agent is a standalone container. The Dockerfile pattern:

```dockerfile
FROM python:3.12-slim
WORKDIR /app

# Install SDK
COPY pyproject.toml /sdk/
COPY src/ /sdk/src/
RUN pip install --no-cache-dir /sdk[bedrock] && rm -rf /sdk

# Copy agent config
COPY examples/researcher/ .

CMD ["python", "-m", "andino", "agent.yaml"]
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

### Host deployment

```bash
andino init my-agent
vim ~/.andino/agents/my-agent/agent.yaml
vim ~/.andino/agents/my-agent/system_prompt.md
andino run my-agent
```

### Docker deployment

1. Create the agent directory and config:
```bash
mkdir examples/my-agent
```

2. Write `agent.yaml` and `system_prompt.md`.

3. Write `Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml /sdk/
COPY src/ /sdk/src/
RUN pip install --no-cache-dir /sdk[bedrock] && rm -rf /sdk
COPY examples/my-agent/ .
CMD ["andino", "run", "./agent.yaml"]
```

4. Add to `docker-compose.agents.yml`:
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
