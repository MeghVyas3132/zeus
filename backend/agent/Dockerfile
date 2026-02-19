FROM python:3.11-slim AS base

# Install git, Node.js 20, .NET SDK 8.0, Go 1.22, JDK 17 + Maven
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git curl ca-certificates wget libicu-dev libssl-dev \
        default-jdk-headless maven && \
    # Node.js 20
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    # .NET SDK 8.0
    wget -q https://dot.net/v1/dotnet-install.sh -O /tmp/dotnet-install.sh && \
    chmod +x /tmp/dotnet-install.sh && \
    /tmp/dotnet-install.sh --channel 8.0 --install-dir /usr/share/dotnet && \
    ln -s /usr/share/dotnet/dotnet /usr/local/bin/dotnet && \
    rm /tmp/dotnet-install.sh && \
    # Go 1.22 (detect architecture)
    ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "arm64" ]; then GOARCH="arm64"; else GOARCH="amd64"; fi && \
    curl -fsSL "https://go.dev/dl/go1.22.5.linux-${GOARCH}.tar.gz" | tar -C /usr/local -xzf - && \
    # Cleanup
    rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    DOTNET_NOLOGO=1 \
    JAVA_HOME="/usr/lib/jvm/default-java" \
    PATH="/usr/local/go/bin:${PATH}"

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Create directories for repos and outputs
RUN mkdir -p /tmp/repos /app/outputs

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]

# ── Test stage ──────────────────────────────────────────
FROM base AS test

COPY tests ./tests

CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]
