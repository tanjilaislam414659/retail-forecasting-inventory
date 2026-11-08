# Official library/python manifest resolved 2026-11-04; see deployment/base-image.json.
FROM python:3.13.18-slim-trixie@sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1 AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1 SOURCE_DATE_EPOCH=1793491200
WORKDIR /build
COPY LICENSE DATA-LICENSE.md ./
COPY licenses/CC-BY-4.0-NOTICE.txt ./licenses/CC-BY-4.0-NOTICE.txt
COPY deployment/requirements-build-linux.lock /locks/build.lock
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r /locks/build.lock
COPY packaging/runtime/pyproject.toml ./pyproject.toml
COPY deployment/README.md ./README.md
COPY src/retail_forecasting/__init__.py src/retail_forecasting/baselines.py src/retail_forecasting/uncertainty.py ./src/retail_forecasting/
COPY src/retail_forecasting/service/ ./src/retail_forecasting/service/
COPY src/retail_forecasting/deployment/ ./src/retail_forecasting/deployment/
RUN python -m build --no-isolation --wheel --outdir /wheels .

FROM python:3.13.18-slim-trixie@sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1 AS runtime
LABEL org.opencontainers.image.title="Retail forecasting historical demo" org.opencontainers.image.version="runtime-0.1.0" org.opencontainers.image.description="Frozen weekday mean; experimental daily intervals; runtime data mounted separately"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 HOME=/tmp
WORKDIR /app
COPY deployment/requirements-runtime-linux.lock /locks/runtime.lock
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r /locks/runtime.lock
COPY --from=builder /wheels/ /wheels/
RUN python -m pip install --no-cache-dir --no-deps /wheels/*.whl && rm -r /wheels
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 CMD ["python", "-m", "retail_forecasting.deployment.healthcheck"]
ENTRYPOINT ["python", "-m", "retail_forecasting.deployment"]
CMD ["--root", "/runtime", "--host", "0.0.0.0", "--port", "8000"]
