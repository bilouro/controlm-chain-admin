"""/api/assistant: conversations with the assistant (``kilo serve``) from the web UI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from controlm_chain_admin.core.errors import AssistantUnavailable
from controlm_chain_admin.core.kilo import project_dir
from controlm_chain_admin.core.repo import ChainRepo
from controlm_chain_admin.web.assistant import NO_ASSISTANT, KiloClient, approvals, conversation
from controlm_chain_admin.web.deps import get_repo, require_token
from controlm_chain_admin.web.schemas import (
    AckOut,
    ApprovalRequest,
    AssistantOut,
    AssistantSessionOut,
    ConversationOut,
    ErrorOut,
    PromptRequest,
)

router = APIRouter(prefix="/api/assistant", tags=["assistant"])
ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "Missing or wrong session token"},
    404: {"model": ErrorOut, "description": "Unknown conversation"},
    503: {"model": ErrorOut, "description": "No assistant, or it does not answer"},
}


def _directory(request: Request, repo: ChainRepo) -> str:
    chosen = request.app.state.settings.assistant_dir
    return str((chosen or project_dir(repo.root)).resolve())


def get_kilo(request: Request, repo: ChainRepo = Depends(get_repo)) -> KiloClient:
    """The client of the configured assistant; none configured: 503 with how to start one."""
    settings = request.app.state.settings
    if not settings.assistant_url:
        raise AssistantUnavailable(NO_ASSISTANT)
    return KiloClient(
        settings.assistant_url, _directory(request, repo), password=settings.assistant_password
    )


@router.get("", response_model=AssistantOut, summary="Is there an assistant, and which")
def status(request: Request, repo: ChainRepo = Depends(get_repo)) -> AssistantOut:
    settings = request.app.state.settings
    found = AssistantOut(
        available=False,
        reason=None,
        agent=settings.assistant_agent,
        model=settings.assistant_model,
        directory=None,
    )
    try:
        get_kilo(request, repo).health()
    except AssistantUnavailable as exc:
        return found.model_copy(update={"reason": str(exc)})
    return found.model_copy(update={"available": True, "directory": _directory(request, repo)})


@router.post(
    "/sessions",
    response_model=AssistantSessionOut,
    responses=ERRORS,
    dependencies=[Depends(require_token)],
    summary="Start a conversation",
)
def start(request: Request, kilo: KiloClient = Depends(get_kilo)) -> AssistantSessionOut:
    return AssistantSessionOut(id=kilo.create_session(request.app.state.settings.assistant_agent))


@router.get(
    "/sessions/{session}",
    response_model=ConversationOut,
    responses=ERRORS,
    summary="A conversation: its messages and what waits for approval",
)
def read(
    session: str, repo: ChainRepo = Depends(get_repo), kilo: KiloClient = Depends(get_kilo)
) -> ConversationOut:
    messages = conversation(kilo.messages(session))
    return ConversationOut.model_validate(
        {
            "id": session,
            "busy": kilo.busy(session),
            "messages": messages,
            "approvals": approvals(repo, kilo.permissions(session)),
        }
    )


@router.post(
    "/sessions/{session}/messages",
    response_model=AckOut,
    responses=ERRORS,
    dependencies=[Depends(require_token)],
    summary="Ask the assistant",
)
def ask(
    session: str, body: PromptRequest, request: Request, kilo: KiloClient = Depends(get_kilo)
) -> AckOut:
    settings = request.app.state.settings
    kilo.send(session, body.text, agent=settings.assistant_agent, model=settings.assistant_model)
    return AckOut()


@router.post(
    "/sessions/{session}/approvals/{approval}",
    response_model=AckOut,
    responses=ERRORS,
    dependencies=[Depends(require_token)],
    summary="Allow or refuse what the assistant waits to do",
)
def answer(
    session: str, approval: str, body: ApprovalRequest, kilo: KiloClient = Depends(get_kilo)
) -> AckOut:
    kilo.reply(approval, approve=body.approve)
    return AckOut()


@router.post(
    "/sessions/{session}/stop",
    response_model=AckOut,
    responses=ERRORS,
    dependencies=[Depends(require_token)],
    summary="Interrupt the assistant",
)
def stop(session: str, kilo: KiloClient = Depends(get_kilo)) -> AckOut:
    kilo.stop(session)
    return AckOut()
