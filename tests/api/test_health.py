"""API tests: health endpoints and the documentation switch."""

from fastapi.testclient import TestClient

import raven
from raven.api.dependencies import get_registry
from raven.api.main import create_app
from tests.api.conftest import make_settings


def test_health_needs_no_sign_in_and_reports_the_status(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "raven-api",
        "version": raven.__version__,
        "environment": "test",
        "registry": "ok",
        "rules_loaded": 3,
        "rarf_version": "1.0",
    }


def test_the_legacy_health_path_still_works(client):
    response = client.get("/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


def test_a_broken_registry_makes_the_health_degraded(app):
    class Broken:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("registry down")

    def broken_registry():
        yield Broken()

    app.dependency_overrides[get_registry] = broken_registry
    with TestClient(app) as test_client:
        response = test_client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded" and response.json()["registry"] == "unavailable"


def test_the_documentation_is_only_available_in_development(tmp_path):
    for env, expected in (("development", 200), ("production", 404), ("test", 404)):
        settings = make_settings(tmp_path / env, env=env)
        application = create_app(settings)
        try:
            with TestClient(application) as test_client:
                assert test_client.get("/docs").status_code == expected
                assert test_client.get("/openapi.json").status_code == expected
        finally:
            application.state.registry_factory.kw["bind"].dispose()


def test_the_registry_is_created_in_the_data_folder(settings, app):
    assert settings.registry_path.is_file()
