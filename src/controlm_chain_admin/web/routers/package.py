"""GET /api/package and /api/package/xml — the Control-M import file of a comparison."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from controlm_chain_admin.core.package import Package, build_package
from controlm_chain_admin.core.repo import ChainRepo
from controlm_chain_admin.web.deps import get_repo
from controlm_chain_admin.web.routers.history import COMMITS, cached, parse_commits
from controlm_chain_admin.web.schemas import ErrorOut, PackageOut

router = APIRouter(prefix="/api", tags=["package"])
ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorOut, "description": "Unknown environment, or an item nobody has"},
    409: {"model": ErrorOut, "description": "A selected commit needs one that was left out"},
    422: {
        "model": ErrorOut,
        "description": "Unknown ref or commit, a constant without a value, or nothing to package",
    },
}


def _package(
    request: Request,
    repo: ChainRepo = Depends(get_repo),
    base: str = Query(description="base ref, e.g. develop"),
    head: str = Query("WORKTREE", description="head ref, or WORKTREE for uncommitted changes"),
    env: str | None = Query(
        None,
        description="target environment, e.g. uat; between the branches of two environments "
        "it is the base's and may be left out, like between two branches of one environment",
    ),
    take: list[str] | None = Query(
        None,
        description="package only these items of the comparison (repeat the parameter): the "
        "base with the items on it; no branch is changed",
    ),
    prefer: list[str] | None = Query(
        None,
        description="between two environments: the entries of the map that win where it gives "
        "several answers for a value (repeat the parameter)",
    ),
    merge_base: bool = Query(True, description="compare from the merge base (pull-request style)"),
    commits: str | None = COMMITS,
    jobnames: str = Query("original", description="original (as in Control-M) | deduped"),
    names: str = Query("original", description="condition names: original | standard"),
) -> Package:
    selection = parse_commits(commits)
    chosen = None if take is None else tuple(take)
    options = (
        env, merge_base, None if selection is None else tuple(selection), jobnames, names,
        chosen, tuple(prefer or ()),
    )  # fmt: skip
    return cached(
        request,
        "package_cache",
        repo,
        (base, head),
        options,
        lambda: build_package(
            repo.root, base, head, env=env, commits=selection, use_merge_base=merge_base,
            names=names, jobnames=jobnames, take=chosen, prefer=tuple(prefer or ()),
        ),
    )  # fmt: skip


@router.get(
    "/package",
    response_model=PackageOut,
    responses=ERRORS,
    summary="Folders of the import package, and why",
)
def package_preview(package: Package = Depends(_package)) -> PackageOut:
    return PackageOut.model_validate(package.to_json())


@router.get(
    "/package/xml",
    response_class=Response,
    responses={
        **ERRORS,
        200: {"content": {"application/xml": {}}, "description": "The XML file to import"},
    },
    summary="Download the import package",
)
def package_xml(package: Package = Depends(_package)) -> Response:
    return Response(
        content=package.require_xml(),
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{package.filename}"'},
    )
