FROM python:3.12-slim

WORKDIR /app

# Install SDK
COPY andino-agent/ /sdk/
RUN pip install --no-cache-dir /sdk[bedrock] && rm -rf /sdk

# Copy agent config
COPY examples/researcher/ .

CMD ["python", "-m", "andino_sdk", "agent.yaml"]
