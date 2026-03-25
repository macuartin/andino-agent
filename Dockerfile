FROM python:3.12-slim AS builder

WORKDIR /sdk

# Install dependencies first (cached layer — only invalidated when pyproject.toml changes)
COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install .[all] 2>/dev/null || \
    (mkdir -p src/andino && echo '__version__ = "0.0.0"' > src/andino/__init__.py && \
     pip install --no-cache-dir --prefix=/install .[all])

# Copy source and reinstall (fast — deps already cached above)
COPY src/ src/
RUN pip install --no-cache-dir --prefix=/install . --no-deps

# --- Runtime ---
FROM python:3.12-slim

COPY --from=builder /install /usr/local

RUN useradd -m -u 1000 andino
WORKDIR /app
USER andino

ENTRYPOINT ["andino"]
CMD ["--help"]
