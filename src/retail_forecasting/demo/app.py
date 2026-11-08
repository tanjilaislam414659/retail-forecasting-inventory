"""Add a static three-view interface to the unchanged FastAPI app factory."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from retail_forecasting.demo import __version__
from retail_forecasting.demo.reports import load_reports
from retail_forecasting.service.app import create_app
from retail_forecasting.service.artifacts import load_engine


def create_demo_app(root=None, *, loader=load_engine, report_directory=None):
    app = create_app(root, loader=loader)
    package = Path(__file__).parent
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        application.state.demo_reports = load_reports(Path(report_directory) if report_directory is not None else package / "reports")
        async with original_lifespan(application):
            yield

    app.router.lifespan_context = lifespan
    app.mount("/demo/assets", StaticFiles(directory=package / "static"), name="demo-assets")

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(package / "static/index.html", headers={
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
            "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})

    @app.get("/demo/api/evaluation")
    def evaluation():
        reports = app.state.demo_reports
        return {"demo_version": __version__, "validation": reports["validation"], "final_test": reports["final-test"]}

    @app.get("/demo/api/inventory")
    def inventory():
        return {"demo_version": __version__, **app.state.demo_reports["inventory"]}

    return app
