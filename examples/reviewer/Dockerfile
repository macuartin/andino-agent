FROM python:3.12-slim

WORKDIR /app

COPY andino-agent/ /sdk/
RUN pip install --no-cache-dir /sdk[bedrock] && rm -rf /sdk

COPY examples/reviewer/ .

CMD ["python", "-m", "andino", "agent.yaml"]
