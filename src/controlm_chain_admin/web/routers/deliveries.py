"""/api/deliveries — items kept for later under a name, and one import file from several.

They are kept on the branch of the map, written there directly: no checkout changes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from controlm_chain_admin.core import deliveries as core
from controlm_chain_admin.core.package import Package
from controlm_chain_admin.core.repo import ChainRepo
from controlm_chain_admin.web.deps import get_repo, require_token
from controlm_chain_admin.web.schemas import (
    DeliveriesOut,
    DeliveryRequest,
    ErrorOut,
    PackageOut,
)

router = APIRouter(prefix="/api/deliveries", tags=["deliveries"])
ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorOut, "description": "Unknown environment"},
    422: {
        "model": ErrorOut,
        "description": "No such delivery, a name taken, an unknown ref or item, two deliveries "
        "that disagree, or nothing to package",
    },
}
WRITE: dict[str, Any] = {
    "responses": {401: {"description": "Missing or wrong session token"}, **ERRORS},
    "dependencies": [Depends(require_token)],
}


def _listed(repo: ChainRepo) -> DeliveriesOut:
    return DeliveriesOut.model_validate({"deliveries": core.listed(repo)})


@router.get("", response_model=DeliveriesOut, responses=ERRORS, summary="The deliveries kept")
def deliveries(repo: ChainRepo = Depends(get_repo)) -> DeliveriesOut:
    return _listed(repo)


@router.post(
    "", response_model=DeliveriesOut, summary="Keep items of a ref under a name", **WRITE
)
def keep(
    body: DeliveryRequest, request: Request, repo: ChainRepo = Depends(get_repo)
) -> DeliveriesOut:
    with request.app.state.write_lock:
        core.save_delivery(
            repo, body.name, body.head, body.items, base=body.base, prefer=body.prefer,
            note=body.note,
        )  # fmt: skip
    return _listed(repo)


@router.delete(
    "/{name}", response_model=DeliveriesOut, summary="Forget one delivery", **WRITE
)
def remove(name: str, request: Request, repo: ChainRepo = Depends(get_repo)) -> DeliveriesOut:
    with request.app.state.write_lock:
        core.remove_delivery(repo, name)
    return _listed(repo)


def _package(
    repo: ChainRepo = Depends(get_repo),
    target: str = Query(description="the branch that receives: main, env/bench ..."),
    name: list[str] = Query(description="a delivery to put in the file (repeat the parameter)"),
    env: str | None = Query(None, description="the environment, where the refs do not tell it"),
) -> Package:
    return core.build_delivery(repo.root, target, name, env=env)


@router.get(
    "/package",
    response_model=PackageOut,
    responses=ERRORS,
    summary="What the import file of a target holds with the deliveries chosen",
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
    summary="Download the import file of the deliveries chosen",
)
def package_xml(package: Package = Depends(_package)) -> Response:
    return Response(
        content=package.require_xml(),
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{package.filename}"'},
    )
