FROM python:3.12-slim

WORKDIR /app

COPY andino-agent/ /sdk/
RUN pip install --no-cache-dir /sdk[bedrock] && rm -rf /sdk

COPY examples/architect/ .

CMD ["python", "-m", "andino_sdk", "agent.yaml"]
