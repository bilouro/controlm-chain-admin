"""/api/assistant: conversations with an assistant (kilo serve) from the web UI."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from controlm_chain_admin.core.capabilities import preview_steps
from controlm_chain_admin.core.repo import load_repo
from controlm_chain_admin.web.app import create_app
from controlm_chain_admin.web.settings import Settings
from tests.support.fake_kilo import FakeKilo
from tests.web.conftest import TOKEN

HEADERS = {"X-Ctmchain-Token": TOKEN}
STEPS = [
    {"do": "change-fields", "params": {"nodes": ["P77_CHAIN/P77_B"], "changes": {"MAXWAIT": "3"}}}
]


@pytest.fixture
def kilo() -> Iterator[FakeKilo]:
    fake = FakeKilo().start()
    yield fake
    fake.stop()


def _client(repo_root: Path, **assistant: Any) -> TestClient:
    settings = Settings(
        repo=repo_root, open_browser=False, token=TOKEN, allowed_hosts=["testserver"], **assistant
    )
    return TestClient(create_app(settings))


@pytest.fixture
def chat(repo_root: Path, kilo: FakeKilo) -> Iterator[TestClient]:
    with _client(repo_root, assistant_url=kilo.url, assistant_model="openai/gpt-5-mini") as client:
        yield client


def _session(chat: TestClient) -> str:
    response = chat.post("/api/assistant/sessions", headers=HEADERS)
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


def test_without_an_assistant_the_page_says_how_to_start_one(client: TestClient) -> None:
    body = client.get("/api/assistant").json()

    assert body["available"] is False
    assert "ctmchain serve --assistant" in body["reason"]


def test_an_assistant_that_does_not_answer_is_unavailable(repo_root: Path) -> None:
    with _client(repo_root, assistant_url="http://127.0.0.1:9") as client:
        body = client.get("/api/assistant").json()

    assert body["available"] is False and "does not answer" in body["reason"]


def test_the_assistant_with_its_agent_model_and_project(chat: TestClient, repo_root: Path) -> None:
    body = chat.get("/api/assistant").json()

    assert body == {
        "available": True,
        "reason": None,
        "agent": "controlm",
        "model": "openai/gpt-5-mini",
        "directory": str(repo_root.resolve()),
    }


def test_a_conversation_starts_in_the_kilo_project_and_sends_the_prompt(
    chat: TestClient, kilo: FakeKilo, repo_root: Path
) -> None:
    session = _session(chat)

    sent = chat.post(
        f"/api/assistant/sessions/{session}/messages",
        json={"text": "Set MAXWAIT to 3 on P77_B"},
        headers=HEADERS,
    )
    conversation = chat.get(f"/api/assistant/sessions/{session}").json()

    assert sent.status_code == 200, sent.text
    assert kilo.directories == [str(repo_root.resolve())]
    assert kilo.sessions[session]["agent"] == "controlm"
    (prompt,) = kilo.prompts
    assert prompt["agent"] == "controlm"
    assert prompt["model"] == {"providerID": "openai", "modelID": "gpt-5-mini"}
    assert prompt["parts"] == [{"type": "text", "text": "Set MAXWAIT to 3 on P77_B"}]
    assert conversation["id"] == session and conversation["busy"] is True
    (message,) = conversation["messages"]
    assert message["role"] == "user"
    assert [(p["kind"], p["text"]) for p in message["parts"]] == [
        ("text", "Set MAXWAIT to 3 on P77_B")
    ]


def test_without_a_model_kilo_chooses_its_own(repo_root: Path, kilo: FakeKilo) -> None:
    with _client(repo_root, assistant_url=kilo.url) as client:
        session = _session(client)
        client.post(
            f"/api/assistant/sessions/{session}/messages", json={"text": "hi"}, headers=HEADERS
        )

    assert "model" not in kilo.prompts[0]


def test_the_messages_keep_the_text_the_tools_and_the_errors_only(
    chat: TestClient, kilo: FakeKilo
) -> None:
    session = _session(chat)
    kilo.say(
        session,
        {"type": "step-start"},
        {"type": "reasoning", "text": "thinking"},
        {"type": "tool", "tool": "ctmchain_find",
         "state": {"status": "completed", "input": {"text": "P77_B"}, "output": "x" * 5000}},
        {"type": "tool", "tool": "ctmchain_show",
         "state": {"status": "error", "input": {"node": "P77_CHAIN/NOPE"}, "error": "unknown job"}},
        {"type": "text", "text": "Found it."},
        {"type": "text", "text": "a reminder", "synthetic": True},
        {"type": "step-finish"},
    )  # fmt: skip
    kilo.say(session, error={"name": "ProviderAuthError", "data": {"message": "bad key"}})

    first, second = chat.get(f"/api/assistant/sessions/{session}").json()["messages"]

    find, show, text = first["parts"]
    assert first["role"] == "assistant"
    assert (find["kind"], find["tool"], find["status"]) == ("tool", "find", "completed")
    assert find["input"] == {"text": "P77_B"}
    assert len(find["output"]) < 2100 and find["output"].endswith("more characters)")
    assert (show["status"], show["output"]) == ("error", "unknown job")
    assert (text["kind"], text["text"]) == ("text", "Found it.")
    assert [(p["kind"], p["text"]) for p in second["parts"]] == [
        ("error", "ProviderAuthError: bad key")
    ]


def test_an_approval_shows_the_change_as_this_repository_previews_it(
    chat: TestClient, kilo: FakeKilo, repo_root: Path
) -> None:
    session, other = _session(chat), _session(chat)
    expected = preview_steps(load_repo(repo_root), STEPS)
    request = kilo.ask(
        session,
        "ctmchain_apply",
        {"mcpInput": {"steps": STEPS, "preview_id": expected["preview_id"]}},
    )
    kilo.ask(other, "ctmchain_apply", {"mcpInput": {"steps": STEPS, "preview_id": "x"}})

    (approval,) = chat.get(f"/api/assistant/sessions/{session}").json()["approvals"]

    assert approval["id"] == request and approval["tool"] == "apply"
    assert approval["input"]["preview_id"] == expected["preview_id"]
    assert approval["preview"]["summary"] == "set MAXWAIT on P77_CHAIN/P77_B"
    assert approval["preview"]["changes"] == expected["changes"]
    assert approval["preview"]["diff"] == expected["diff"]
    assert approval["problem"] is None


def test_an_approval_of_another_change_than_previewed_says_so(
    chat: TestClient, kilo: FakeKilo
) -> None:
    session = _session(chat)
    kilo.ask(session, "ctmchain_apply", {"mcpInput": {"steps": STEPS, "preview_id": "0" * 12}})
    bad = [{"do": "change-fields", "params": {"changes": {"MAXWAIT": "3"}}}]
    kilo.ask(session, "ctmchain_apply", {"mcpInput": {"steps": bad, "preview_id": "0" * 12}})
    kilo.ask(session, "bash", {"command": "ls"})

    moved, wrong, other = chat.get(f"/api/assistant/sessions/{session}").json()["approvals"]

    assert moved["preview"] is not None
    assert "not the change the assistant previewed" in moved["problem"]
    assert wrong["preview"] is None and "nodes is missing" in wrong["problem"]
    assert other["tool"] == "bash" and other["preview"] is None and other["problem"] is None
    assert other["input"] == {"command": "ls"}


def test_approving_and_rejecting_answer_the_assistant(chat: TestClient, kilo: FakeKilo) -> None:
    session = _session(chat)
    yes = kilo.ask(session, "ctmchain_apply", {"mcpInput": {"steps": STEPS}})
    no = kilo.ask(session, "ctmchain_apply", {"mcpInput": {"steps": STEPS}})

    for request, approve in ((yes, True), (no, False)):
        response = chat.post(
            f"/api/assistant/sessions/{session}/approvals/{request}",
            json={"approve": approve},
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text

    assert kilo.replies == [(yes, "once"), (no, "reject")]


def test_stop_interrupts_the_assistant(chat: TestClient, kilo: FakeKilo) -> None:
    session = _session(chat)

    response = chat.post(f"/api/assistant/sessions/{session}/stop", headers=HEADERS)

    assert response.status_code == 200 and kilo.aborted == [session]


def test_every_change_of_a_conversation_needs_the_token(chat: TestClient, kilo: FakeKilo) -> None:
    session = _session(chat)
    posts = [
        ("/api/assistant/sessions", None),
        (f"/api/assistant/sessions/{session}/messages", {"text": "hi"}),
        (f"/api/assistant/sessions/{session}/approvals/per_1", {"approve": True}),
        (f"/api/assistant/sessions/{session}/stop", None),
    ]

    statuses = [chat.post(path, json=body).status_code for path, body in posts]

    assert statuses == [401, 401, 401, 401] and kilo.prompts == []


def test_an_assistant_that_went_away_is_a_503_with_the_common_shape(
    chat: TestClient, kilo: FakeKilo
) -> None:
    session = _session(chat)
    kilo.stop()

    response = chat.post(
        f"/api/assistant/sessions/{session}/messages", json={"text": "hi"}, headers=HEADERS
    )

    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "AssistantUnavailable" and "does not answer" in body["message"]


def test_an_unknown_conversation_is_404(chat: TestClient) -> None:
    response = chat.get("/api/assistant/sessions/ses_nope")

    assert response.status_code == 404 and "ses_nope" in response.json()["message"]


def test_an_assistant_with_a_password(repo_root: Path) -> None:
    fake = FakeKilo(password="s3cret").start()
    try:
        with _client(repo_root, assistant_url=fake.url, assistant_password="s3cret") as client:
            right = client.get("/api/assistant").json()
        with _client(repo_root, assistant_url=fake.url, assistant_password="wrong") as client:
            wrong = client.get("/api/assistant").json()
    finally:
        fake.stop()

    assert right["available"] is True
    assert wrong["available"] is False and "refused" in wrong["reason"]


@pytest.mark.parametrize(
    ("platform", "on_path", "chosen"),
    [
        # npm puts kilo (a shell script), kilo.cmd and kilo.ps1 side by side on Windows
        ("win32", {"kilo": "C:/npm/kilo", "kilo.cmd": "C:/npm/kilo.cmd"}, "C:/npm/kilo.cmd"),
        ("win32", {"kilo": "C:/npm/kilo", "kilo.exe": "C:/kilo/kilo.exe"}, "C:/kilo/kilo.exe"),
        ("darwin", {"kilo": "/usr/local/bin/kilo", "kilo.cmd": "x"}, "/usr/local/bin/kilo"),
        ("win32", {}, None),
    ],
)
def test_the_kilo_started_is_one_the_system_can_run(
    monkeypatch: pytest.MonkeyPatch, platform: str, on_path: dict[str, str], chosen: str | None
) -> None:
    from controlm_chain_admin.web import assistant

    monkeypatch.delenv("CTMCHAIN_KILO", raising=False)
    monkeypatch.setattr(assistant.sys, "platform", platform)
    monkeypatch.setattr(assistant.shutil, "which", on_path.get)

    assert assistant.kilo_executable() == chosen


def test_ctmchain_kilo_names_the_kilo_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    from controlm_chain_admin.web import assistant

    monkeypatch.setenv("CTMCHAIN_KILO", "D:/tools/kilo.cmd")

    assert assistant.kilo_executable() == "D:/tools/kilo.cmd"
