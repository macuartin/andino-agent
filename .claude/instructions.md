# Development Instructions

## Running the Project

```bash
# Install with all extras
pip install -e ".[all]"

# Create a new agent
andino init test-agent

# Edit config and add credentials
vim ~/.andino/agents/test-agent/agent.yaml
echo "AWS_REGION=us-east-1" >> ~/.andino/agents/test-agent/.env

# Run
andino run test-agent
```

## Running Tests

```bash
# Full suite
pytest tests/ -v

# Specific module
pytest tests/test_server.py -v

# Specific test class
pytest tests/test_task_executor.py::TestStripThinking -v
```

## Linting

```bash
ruff check src/andino/

# Auto-fix
ruff check src/andino/ --fix
```

## Adding a New Built-in Tool

1. Create `src/andino/tools/<name>.py` following the pattern in `jira.py` or `datadog.py`:
   - `_<service>_auth()` — reads credentials from env vars
   - `_<service>_request()` — async HTTP helper with httpx
   - `_ok(text)` / `_err(text)` — response formatters
   - `@tool async def <service>_<action>(...)` — one function per operation
2. Add exports to `src/andino/tools/__init__.py`
3. Create `tests/test_<name>_tools.py` with mocked HTTP responses
4. Add credential env vars to `.env.example`

Usage in agent.yaml:
```yaml
tools:
  - andino.tools.<name>:<service>_<action>
```

## Adding a New Channel

1. Create `src/andino/channels/<name>.py` extending `BaseChannel`
2. Implement `start()`, `stop()`, and message handling
3. Register in the channel loader dict in `src/andino/channels/__init__.py`
4. Document in `docs/channels.md`

## Docker Build

```bash
docker build -t andino-agent .
docker run -e AWS_REGION=us-east-1 andino-agent
```

## systemd Deployment

```bash
cp deploy/andino@.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable andino@researcher
systemctl --user start andino@researcher
journalctl --user -u andino@researcher -f
```

## Git Workflow

- Never add `Co-Authored-By` lines to commits
- Commit messages: imperative, explain "why" not "what"
- Run `ruff check` and `pytest` before committing
- Push directly to `main` (single-contributor project)
