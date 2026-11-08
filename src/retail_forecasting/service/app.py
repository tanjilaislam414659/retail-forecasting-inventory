"""Thin FastAPI transport around a once-loaded inference engine."""

from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
import time
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from retail_forecasting.service import __version__
from retail_forecasting.service.artifacts import ArtifactError, UnsupportedRequest, load_engine
from retail_forecasting.service.schemas import (ErrorResponse, ForecastRequest, ForecastResponse,
    HealthResponse, MetadataResponse, ReadyResponse, ValidationErrorResponse)

LOGGER = logging.getLogger("retail_forecasting.service")


def log_event(**values):
    LOGGER.info(json.dumps({"service_version": __version__, **values}, allow_nan=False))


def create_app(root: Path | None = None, *, loader=load_engine) -> FastAPI:
    # Computing the default path is harmless; importing the app does not load data.
    root = Path(root).resolve() if root is not None else Path(__file__).resolve().parents[3]

    @asynccontextmanager
    async def lifespan(app):
        started = time.perf_counter()
        try:
            app.state.engine = loader(root)
            app.state.artifact_error = None
        except ArtifactError as exc:
            app.state.engine = None
            app.state.artifact_error = exc.code
            log_event(event="artifact_load", outcome="not_ready", error_code=exc.code, artifact=exc.artifact)
        app.state.startup_ms = (time.perf_counter() - started) * 1000
        log_event(event="startup", outcome="ready" if app.state.engine else "not_ready", elapsed_ms=app.state.startup_ms)
        yield
        app.state.engine = None

    app = FastAPI(title="Retail Forecasting — Historical Demo", version=__version__, lifespan=lifespan,
        description="Local 100-SKU / 20-origin historical demonstration. Frozen weekday mean with experimental daily intervals; not a live or production-ready service.")
    app.state.engine = None
    app.state.artifact_error = "lifespan_not_started"
    app.state.startup_ms = 0.

    @app.middleware("http")
    async def request_log(request, call_next):
        request_id = str(uuid4())
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            # Deliberately exclude URL/query/body/headers: they can contain credentials.
            log_event(event="request", request_id=request_id, status=status,
                outcome="success" if status < 400 else ("rejected" if status < 500 else "error"),
                elapsed_ms=(time.perf_counter() - started) * 1000)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Don't echo submitted values (including unexpected credentials) in errors.
        return JSONResponse(status_code=422, content={"detail": [
            {"location": list(error["loc"]), "code": error["type"], "message": error["msg"]}
            for error in exc.errors()]})

    def engine():
        if app.state.engine is None:
            raise HTTPException(503, detail={"code": "service_not_ready", "message": "Required artifacts are unavailable or invalid; inspect /ready and restart after repair."})
        return app.state.engine

    @app.get("/health", response_model=HealthResponse)
    def health():
        """Process liveness; independent of artifact readiness."""
        return HealthResponse(service_version=__version__)

    @app.get("/ready", response_model=ReadyResponse, responses={503: {"model": ReadyResponse}})
    def ready():
        result = ReadyResponse(status="ready" if app.state.engine else "not_ready", service_version=__version__,
            startup_ms=app.state.startup_ms, forecast_release_id=app.state.engine.forecast_release_id if app.state.engine else None,
            error_code=app.state.artifact_error)
        if not app.state.engine:
            return JSONResponse(status_code=503, content=result.model_dump(mode="json"))
        return result

    @app.get("/metadata", response_model=MetadataResponse, responses={503: {"model": ErrorResponse}})
    def metadata():
        return engine().metadata()

    @app.post("/forecast", response_model=ForecastResponse,
        responses={422: {"model": ValidationErrorResponse}, 503: {"model": ErrorResponse}})
    def forecast(request: ForecastRequest):
        """Recompute 28 days from pre-origin history and frozen training quantiles."""
        try:
            return engine().predict(request.sku, request.origin, request.horizon_days)
        except UnsupportedRequest as exc:
            raise HTTPException(422, detail={"code": exc.code, "message": str(exc)}) from exc

    return app


app = create_app()
