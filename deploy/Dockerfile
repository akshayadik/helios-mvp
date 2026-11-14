# HELIOS image for the compose deployment (S4.3, design s4_3_compose_design.md C-b).
# One image serves the API and the runner. Dependencies come from poetry.lock,
# installed with hash checking and without dev packages. No data, ledgers,
# .env files or key files are copied in: compose mounts them.
# Build from the repository root: docker compose -f deploy/compose.yaml build

FROM python:3.11-slim@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535 AS deps
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
# Poetry only exports the lock file here; it never reaches the final image.
RUN pip install "poetry==2.5.1" "poetry-plugin-export==1.10.1"
WORKDIR /src
COPY pyproject.toml poetry.lock ./
RUN poetry export --only main --format requirements.txt --output /src/requirements.txt \
 && python -m venv /opt/venv \
 && /opt/venv/bin/pip install --require-hashes --no-deps -r /src/requirements.txt

FROM python:3.11-slim@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535
ARG HELIOS_REVISION=unknown
LABEL org.opencontainers.image.title="helios" \
      org.opencontainers.image.revision="${HELIOS_REVISION}" \
      org.opencontainers.image.source="https://github.com/akshayadik/helios-mvp"
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HELIOS_REVISION=${HELIOS_REVISION}
COPY --from=deps /opt/venv /opt/venv
WORKDIR /app
COPY helios/ helios/
COPY bin/ bin/
COPY keys/deviation_log_ed25519.pub.pem keys/
COPY docs/tracking/price_book.md docs/tracking/
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin helios \
 && mkdir -p /campaign /decisions /secrets /cache && chown helios /campaign /decisions /cache
USER 10001
# The api service overrides nothing; the runner is started with a command.
ENTRYPOINT ["python"]
CMD ["bin/helios_api.py", "--help"]
