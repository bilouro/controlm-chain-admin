"""/api/envmap — the map of what varies per environment: shown, derived, suggested, edited.

The map lives on its own branch and is written there directly: no checkout changes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from controlm_chain_admin.core import envmap as core
from controlm_chain_admin.core.mapcheck import survey
from controlm_chain_admin.core.repo import ChainRepo
from controlm_chain_admin.web.deps import get_repo, require_token
from controlm_chain_admin.web.schemas import (
    DerivedOut,
    DeriveRequest,
    EnvMapOut,
    ErrorOut,
    FollowersOut,
    MapEntryRequest,
    RenameEntryRequest,
    SuggestionsOut,
)

router = APIRouter(prefix="/api/envmap", tags=["envmap"])
ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorOut, "description": "No such entry, a name taken, an unknown environment"},
    422: {"model": ErrorOut, "description": "A key that cannot be read, or a git error"},
}
WRITE: dict[str, Any] = {
    "responses": {401: {"description": "Missing or wrong session token"}, **ERRORS},
    "dependencies": [Depends(require_token)],
}


def _shown(repo: ChainRepo) -> EnvMapOut:
    return EnvMapOut.model_validate(core.show_map(repo))


def _written(request: Request, repo: ChainRepo, write: Callable[[], object]) -> EnvMapOut:
    with request.app.state.write_lock:
        write()
    return _shown(repo)


def _derived(found: core.Derived, applied: bool) -> DerivedOut:
    return DerivedOut.model_validate({**found.to_json(), "applied": applied})


@router.get(
    "", response_model=EnvMapOut, responses=ERRORS, summary="The letters, the branches, the map"
)
def show(repo: ChainRepo = Depends(get_repo)) -> EnvMapOut:
    return _shown(repo)


@router.get(
    "/derive",
    response_model=DerivedOut,
    responses=ERRORS,
    summary="The entries the environments' branches show and the map lacks (nothing written)",
)
def derive_preview(
    repo: ChainRepo = Depends(get_repo),
    key: list[str] | None = Query(
        None, description="one more attribute whose whole value varies (repeat the parameter)"
    ),
    text: list[str] | None = Query(
        None, description="an attribute whose texts differ in one word (repeat the parameter)"
    ),
    min_nodes: int = Query(2, ge=1, description="nodes that must show the same values"),
) -> DerivedOut:
    return _derived(
        *core.derive_map(repo, keys=key or (), text_keys=text or (), min_nodes=min_nodes)
    )


@router.post(
    "/derive",
    response_model=DerivedOut,
    summary="Add the derived entries to the map (a commit on its branch)",
    **WRITE,
)
def derive_apply(
    body: DeriveRequest, request: Request, repo: ChainRepo = Depends(get_repo)
) -> DerivedOut:
    with request.app.state.write_lock:
        return _derived(
            *core.derive_map(
                repo, keys=body.keys, text_keys=body.text_keys, min_nodes=body.min_nodes,
                apply=True,
            )  # fmt: skip
        )


@router.get(
    "/suggest",
    response_model=SuggestionsOut,
    responses=ERRORS,
    summary="What else varies between the environments, that the map does not explain",
)
def suggest(
    repo: ChainRepo = Depends(get_repo),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> SuggestionsOut:
    found = [item.to_json() for item in core.suggest_map(repo)]
    return SuggestionsOut.model_validate(
        {"total": len(found), "suggestions": found[offset : offset + limit]}
    )


@router.get(
    "/followers",
    response_model=FollowersOut,
    responses=ERRORS,
    summary="How many places of the environments' branches follow each entry of the map",
)
def followers(repo: ChainRepo = Depends(get_repo)) -> FollowersOut:
    seen = survey(repo.root)
    return FollowersOut.model_validate({**seen.to_json(), "unmapped": len(seen.unmapped)})


@router.post("/entries", response_model=EnvMapOut, summary="Add one entry by hand", **WRITE)
def add_entry(
    body: MapEntryRequest, request: Request, repo: ChainRepo = Depends(get_repo)
) -> EnvMapOut:
    return _written(
        request,
        repo,
        lambda: core.add_to_map(repo, body.key, body.values, name=body.name, inline=body.inline),
    )


@router.patch(
    "/entries/{name}",
    response_model=EnvMapOut,
    summary="Give an entry a name that says what it is",
    **WRITE,
)
def rename_entry(
    name: str, body: RenameEntryRequest, request: Request, repo: ChainRepo = Depends(get_repo)
) -> EnvMapOut:
    return _written(request, repo, lambda: core.rename_in_map(repo, name, body.name))


@router.delete("/entries/{name}", response_model=EnvMapOut, summary="Drop one entry", **WRITE)
def remove_entry(name: str, request: Request, repo: ChainRepo = Depends(get_repo)) -> EnvMapOut:
    return _written(request, repo, lambda: core.remove_from_map(repo, name))
