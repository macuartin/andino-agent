# Deployment

For installation, CLI usage, and ANDINO_HOME setup, see [Getting Started](getting-started.md).

## Multi-Agent Architecture

Each Andino agent runs as an **independent process** with its own HTTP server, port, and optional Slack channel. Multiple agents on one server share `ANDINO_HOME` (`~/.andino/`) but are otherwise isolated.

```
                         ┌─────────────────────────┐
                         │  Reverse Proxy (Nginx)   │
                         │  agents.company.com      │
                         └──────┬──────┬──────┬─────┘
                                │      │      │
                    ┌───────────┘      │      └───────────┐
                    ▼                  ▼                  ▼
            ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
            │  researcher  │  │  prospector   │  │     sre      │
            │  :8105       │  │  :8110        │  │  :8120       │
            └──────────────┘  └──────────────┘  └──────────────┘
                    │                  │                  │
                    └──────────┬───────┘──────────────────┘
                               ▼
                         ~/.andino/
                         ├── .env (shared secrets)
                         ├── agents/
                         ├── sessions/
                         └── workspaces/
```

---

## Option 1: Host Deployment (systemd)

Best for: VMs, bare metal servers, single-machine setups.

### Setup

```bash
# 1. Install
python3 -m venv ~/.local/share/andino/venv
source ~/.local/share/andino/venv/bin/activate
pip install andino-agent[all]

# 2. Create agents from templates
andino init researcher -t researcher
andino init prospector -t prospector
andino init sre -t sre

# 3. Configure each agent
vim ~/.andino/agents/researcher/.env
vim ~/.andino/agents/prospector/.env
vim ~/.andino/agents/sre/.env

# 4. Validate before deploying
andino validate researcher
andino validate prospector
andino validate sre
```

### systemd services

```bash
# Install the unit template (one-time)
mkdir -p ~/.config/systemd/user
cp deploy/andino@.service ~/.config/systemd/user/
systemctl --user daemon-reload

# Enable and start all agents
for agent in researcher prospector sre; do
  systemctl --user enable andino@$agent
  systemctl --user start andino@$agent
done

# Keep running after logout
loginctl enable-linger $USER
```

### Managing agents

```bash
# Status
systemctl --user status andino@researcher

# Logs
journalctl --user -u andino@researcher -f

# Restart after config change
systemctl --user restart andino@researcher

# Stop
systemctl --user stop andino@prospector

# View all andino services
systemctl --user list-units 'andino@*'
```

### Reverse proxy (Nginx)

```nginx
# /etc/nginx/sites-available/andino
server {
    listen 80;
    server_name agents.company.com;

    location /researcher/ {
        proxy_pass http://127.0.0.1:8105/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /prospector/ {
        proxy_pass http://127.0.0.1:8110/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /sre/ {
        proxy_pass http://127.0.0.1:8120/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/andino /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# For TLS, add certbot:
# sudo certbot --nginx -d agents.company.com
```

Now agents are accessible at:
- `https://agents.company.com/researcher/task`
- `https://agents.company.com/prospector/task`
- `https://agents.company.com/sre/health`

---

## Option 2: Docker Compose

Best for: reproducible deployments, CI/CD pipelines, team environments.

### Dockerfile

One Dockerfile for all agents — the agent config is mounted at runtime:

```dockerfile
# deploy/Dockerfile
FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml /sdk/
COPY src/ /sdk/src/
RUN pip install --no-cache-dir /sdk[all] && rm -rf /sdk

# Agent config is mounted via volume
CMD ["andino", "run", "./agent.yaml"]
```

### docker-compose.yml

```yaml
# deploy/docker-compose.yml
services:
  researcher:
    build:
      context: ..
      dockerfile: deploy/Dockerfile
    ports:
      - "8105:8105"
    volumes:
      - ./agents/researcher:/app
      - andino-data:/data
    env_file:
      - .env
    restart: unless-stopped

  prospector:
    build:
      context: ..
      dockerfile: deploy/Dockerfile
    ports:
      - "8110:8110"
    volumes:
      - ./agents/prospector:/app
      - andino-data:/data
    env_file:
      - .env
    restart: unless-stopped

  sre:
    build:
      context: ..
      dockerfile: deploy/Dockerfile
    ports:
      - "8120:8120"
    volumes:
      - ./agents/sre:/app
      - andino-data:/data
    env_file:
      - .env
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - researcher
      - prospector
      - sre
    restart: unless-stopped

volumes:
  andino-data:
```

### Setup

```bash
cd deploy/

# 1. Initialize agent configs
for agent in researcher prospector sre; do
  andino init tmp-$agent -t $agent
  mkdir -p agents/$agent
  cp -r ~/.andino/agents/tmp-$agent/* agents/$agent/
done

# 2. Create shared .env
cp ../.env.example .env
vim .env

# 3. Update agent.yaml paths for Docker volumes
# Set session.storage_dir and workspace.base_dir to /data/...

# 4. Build and start
docker compose build
docker compose up -d

# 5. View logs
docker compose logs -f
```

### Persistent data

Use absolute paths in agent.yaml for Docker deployments:

```yaml
session:
  storage_dir: /data/sessions
workspace:
  base_dir: /data/workspaces
```

The `andino-data` volume is shared across all agents. Each agent scopes its data by session_id.

---

## Port Conventions

| Template | Default Port |
|----------|-------------|
| blank | 8100 |
| researcher | 8105 |
| prospector | 8110 |
| sre | 8120 |

Each agent must use a unique port. Set in `agent.yaml` → `server.port`.

---

## Adding a New Agent

### Host (systemd)

```bash
andino init my-agent -t blank
vim ~/.andino/agents/my-agent/agent.yaml
andino validate my-agent
systemctl --user enable andino@my-agent
systemctl --user start andino@my-agent
```

### Docker

```bash
mkdir deploy/agents/my-agent
# Add agent.yaml + system_prompt.md + skills/
# Add service to docker-compose.yml
docker compose up my-agent -d
```

---

## Health Checks

All agents expose `/health` without authentication:

```bash
for port in 8105 8110 8120; do
  curl -s http://localhost:$port/health | jq -r '.agent_name + ": " + .status'
done
```
