"""The built UI is a single-page app: client routes reload and deep-link to index.html."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from controlm_chain_admin.web.app import _client_route, create_app
from controlm_chain_admin.web.settings import Settings
from tests.web.conftest import TOKEN


def _client(repo_root: Path, static: Path) -> TestClient:
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>ui</title>", encoding="utf-8")
    (static / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    settings = Settings(
        repo=repo_root, open_browser=False, token=TOKEN, allowed_hosts=["testserver"]
    )
    return TestClient(create_app(settings, static_dir=static))


def test_client_routes_serve_the_app(repo_root: Path, tmp_path: Path) -> None:
    client = _client(repo_root, tmp_path / "static")

    for path in ("/", "/compare?base=develop", "/validate", "/folders/P77_CHAIN/jobs/P77_B"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "<title>ui</title>" in response.text

    assert client.get("/assets/app.js").text == "console.log(1)"


def test_missing_files_and_api_paths_stay_404(repo_root: Path, tmp_path: Path) -> None:
    client = _client(repo_root, tmp_path / "static")

    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/favicon.ico").status_code == 404
    response = client.get("/api/nothing-here")
    assert response.status_code == 404 and "<title>" not in response.text
    assert client.get("/api/repo").status_code == 200


def test_without_a_built_ui_the_root_explains_how_to_get_it(
    repo_root: Path, tmp_path: Path
) -> None:
    settings = Settings(
        repo=repo_root, open_browser=False, token=TOKEN, allowed_hosts=["testserver"]
    )
    client = TestClient(create_app(settings, static_dir=tmp_path / "nothing"))

    assert "web UI is not built" in client.get("/").text


def test_client_routes_are_recognised_with_windows_separators() -> None:
    # StaticFiles hands the path over with os.sep: backslashes on Windows
    assert _client_route("folders/P77_CHAIN") and _client_route("folders\\P77_CHAIN")
    assert not _client_route("api/nothing-here") and not _client_route("api\\nothing-here")
    assert not _client_route("assets\\missing.js") and not _client_route("favicon.ico")
