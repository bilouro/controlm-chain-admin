"""Dump API responses for the synthetic repository into web/src/test/fixtures (MSW handlers).

Run from the repository root with the dev extras installed:

    .venv/bin/python web/scripts/dump_fixtures.py

Only synthetic data (application P77) is involved, so the output is safe to commit.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from tests.support.anomalies import ANOMALY_EXPORT  # noqa: E402
from tests.support.gitrepo import chain_git_repo, commit_all, git  # noqa: E402
from tests.support.samples import SAMPLE_EXPORT  # noqa: E402

from controlm_chain_admin.core.constants import Selector, define_constant  # noqa: E402
from controlm_chain_admin.core.ops import import_xml  # noqa: E402
from controlm_chain_admin.core.refactor import (  # noqa: E402
    apply,
    insert_job,
    link_nodes,
    move_job,
    rename_job,
    rename_link,
    set_attributes,
    set_variables,
    update_relation,
)
from controlm_chain_admin.core.repo import init_repo  # noqa: E402
from controlm_chain_admin.core.workspace import mark_installed, stash, start_release  # noqa: E402
from controlm_chain_admin.web.app import create_app  # noqa: E402
from controlm_chain_admin.web.settings import Settings  # noqa: E402

FIXTURES = ROOT / "web" / "src" / "test" / "fixtures"
ENDPOINTS = {
    "repo.json": "/api/repo",
    "folders.json": "/api/folders",
    "folder-P77_CHAIN.json": "/api/folders/P77_CHAIN",
    "folder-P77_INGEST_DAILY.json": "/api/folders/P77_INGEST_DAILY",
    "job-P77_INGEST_DAILY-P77_INGEST_LOAD.json": "/api/jobs/P77_INGEST_DAILY/P77_INGEST_LOAD",
    "job-P77_CHAIN-P77_B.json": "/api/jobs/P77_CHAIN/P77_B",
    "validate.json": "/api/validate",
    "table.json": "/api/table",
}
PREVIEW = {
    "op": "set-attributes",
    "params": {"node": "P77_CHAIN/P77_B", "changes": {"DESCRIPTION": "Loaded"}},
}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        repo = init_repo(
            root,
            "P77_RISK_ENGINE",
            ("test", "uat", "bench", "prod"),
            prefixes=("P77", "RQ_", "RC_"),
        )
        import_xml(repo, SAMPLE_EXPORT, env="uat")
        import_xml(repo, ANOMALY_EXPORT, env="uat")
        FIXTURES.mkdir(parents=True, exist_ok=True)
        settings = Settings(repo=root, open_browser=False, token="t", allowed_hosts=["testserver"])
        with TestClient(create_app(settings)) as client:
            for filename, path in ENDPOINTS.items():
                response = client.get(path)
                response.raise_for_status()
                body = response.json()
                if filename == "repo.json":
                    body["root"] = "/tmp/repo"  # not deterministic otherwise
                (FIXTURES / filename).write_text(
                    json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )
                print(f"wrote {filename}")
            preview = client.post(
                "/api/changes/preview", json=PREVIEW, headers={"X-Ctmchain-Token": "t"}
            )
            preview.raise_for_status()
            (FIXTURES / "preview.json").write_text(
                json.dumps(preview.json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            print("wrote preview.json")
    dump_compare()
    dump_workspace()
    dump_intake()
    return 0


def dump_intake() -> None:
    """A prod export of the synthetic chain, one job changed, analysed against the repository."""
    from tests.support.envexports import both, constants_repo, job, to_prod

    with tempfile.TemporaryDirectory() as tmp:
        repo = constants_repo(Path(tmp))
        data = job(to_prod(both()), b"PP77_E", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')
        settings = Settings(
            repo=repo.root, open_browser=False, token="t", allowed_hosts=["testserver"]
        )
        with TestClient(create_app(settings)) as client:
            response = client.post(
                "/api/intake", json={"xml": data.decode()}, headers={"X-Ctmchain-Token": "t"}
            )
            response.raise_for_status()
            _write("intake.json", response.json())


def _write(filename: str, body: object) -> None:
    (FIXTURES / filename).write_text(
        json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {filename}")


def dump_workspace() -> None:
    """The trunk (read-only), then a release installed in uat one commit ago, with a stash."""
    for role in ("AUTHOR", "COMMITTER"):  # tags and stashes are made by the code itself
        os.environ.setdefault(f"GIT_{role}_NAME", "Test")
        os.environ.setdefault(f"GIT_{role}_EMAIL", "test@example.com")
    c = "P77_CHAIN"
    with tempfile.TemporaryDirectory() as tmp:
        repo = chain_git_repo(Path(tmp))
        settings = Settings(
            repo=repo.root, open_browser=False, token="t", allowed_hosts=["testserver"]
        )
        with TestClient(create_app(settings)) as client:
            _write("workspace-main.json", client.get("/api/workspace").json())
            start_release(repo, "demo")
            apply(repo, set_attributes(repo, f"{c}/P77_C", {"DESCRIPTION": "Loaded nightly"}))
            commit_all(repo.root, "feat: describe P77_C")
            mark_installed(repo, "uat")
            apply(repo, set_attributes(repo, f"{c}/P77_E", {"DESCRIPTION": "Checked twice"}))
            commit_all(repo.root, "fix: describe P77_E")
            git(repo.root, "branch", "release/next", "main")
            apply(repo, set_attributes(repo, f"{c}/P77_A", {"DESCRIPTION": "Draft"}))
            stash(repo)
            apply(repo, set_attributes(repo, f"{c}/P77_B", {"DESCRIPTION": "Work in progress"}))
            _write("workspace.json", client.get("/api/workspace").json())


def dump_compare() -> None:
    """A synthetic git repository with develop and a feature branch, and its comparison."""
    c = "P77_CHAIN"
    with tempfile.TemporaryDirectory() as tmp:
        repo = chain_git_repo(Path(tmp))
        define_constant(
            repo, "node.batch", Selector("NODEID"), {"uat": "UP77_BATCH", "prod": "PP77_BATCH"}
        )
        commit_all(repo.root, "chore: constants")
        git(repo.root, "branch", "develop")
        git(repo.root, "checkout", "-q", "-b", "feature/demo")
        apply(
            repo,
            set_attributes(repo, f"{c}/P77_C", {"DESCRIPTION": "Loaded nightly", "MAXRERUN": "2"}),
        )
        apply(repo, set_variables(repo, f"{c}/P77_C", [{"NAME": "%%RETRIES", "VALUE": "3"}]))
        commit_all(repo.root, "feat: retries on P77_C")
        apply(repo, rename_job(repo, f"{c}/P77_D", "P77_DELTA"))
        apply(repo, move_job(repo, "P77_INGEST_DAILY/P77_INGEST_LOAD", c))
        refactor = commit_all(repo.root, "refactor: rename P77_D and move the load job")
        apply(repo, insert_job(repo, f"{c}/P77_CHECK", after=f"{c}/P77_A", before=f"{c}/P77_B"))
        apply(repo, update_relation(repo, "P77_B-P77_C_OK", f"{c}/P77_C", and_or="O"))
        apply(repo, link_nodes(repo, f"{c}/P77_E", producer=f"{c}/P77_C"))
        apply(repo, rename_link(repo, "P77_D-P77_NOBODY_OK", "P77_DELTA_DONE"))
        define_constant(repo, "node.batch", Selector("NODEID"), {"prod": "PP77_BATCH_V2"})
        commit_all(repo.root, "feat: quality check before P77_B")
        settings = Settings(
            repo=repo.root, open_browser=False, token="t", allowed_hosts=["testserver"]
        )
        with TestClient(create_app(settings)) as client:
            for filename, path in {
                "git.json": "/api/git",
                "compare.json": "/api/compare?base=develop&head=feature/demo",
                "compare-selected.json": (
                    f"/api/compare?base=develop&head=feature/demo&commits={refactor}"
                ),
                "package.json": "/api/package?base=develop&head=feature/demo&env=uat",
            }.items():
                response = client.get(path)
                response.raise_for_status()
                (FIXTURES / filename).write_text(
                    json.dumps(response.json(), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                print(f"wrote {filename}")
            apply(repo, update_relation(repo, "P77_B-P77_C_OK", f"{c}/P77_C", cleanup=False))
            apply(repo, set_attributes(repo, f"{c}/P77_E", {"DESCRIPTION": "Checked twice"}))
            response = client.get("/api/git/pending")
            response.raise_for_status()
            (FIXTURES / "pending.json").write_text(
                json.dumps(response.json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            print("wrote pending.json")


if __name__ == "__main__":
    raise SystemExit(main())
