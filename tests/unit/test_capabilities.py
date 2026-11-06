"""The capabilities file: what can be asked in plain words, and how each turns into changes."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.capabilities import (
    changes_of,
    load_catalogue,
    plan,
    preview_steps,
    render_menu,
)
from controlm_chain_admin.core.constants import Selector, define_constant
from controlm_chain_admin.core.errors import InvalidChange
from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.overrides import Override, write_overrides
from controlm_chain_admin.core.refactor import OPERATIONS, apply, fingerprint, set_variable
from controlm_chain_admin.core.repo import ChainRepo, init_repo, load_repo, read_json, write_json
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.samples import SAMPLE_EXPORT

APP = "P77_RISK_ENGINE"
CATALOGUE = load_catalogue()


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    """The synthetic chain, with a constant and an exception the examples need."""
    root = tmp_path / "repo"
    repo = init_repo(root, APP, ("test", "uat", "bench", "prod"), prefixes=("P77", "RQ_", "RC_"))
    import_xml(repo, SAMPLE_EXPORT, env="uat")
    import_xml(repo, ANOMALY_EXPORT, env="uat")
    repo = define_constant(repo, "node.batch", Selector("NODEID"),
                           {"uat": "UP77_BATCH", "prod": "PP77_BATCH"})  # fmt: skip
    import_xml(repo, SAMPLE_EXPORT, env="uat")  # the values become the constant
    write_overrides(repo, "prod", {"P77_CHAIN/P77_B": Override(attributes={"TASKTYPE": "Dummy"})})
    return load_repo(root)


def test_every_operation_is_a_capability_or_left_out_on_purpose() -> None:
    covered = {capability.op for capability in CATALOGUE.capabilities}

    assert set(OPERATIONS) - covered == set(CATALOGUE.not_by_prompt)
    assert covered <= set(OPERATIONS)


def test_capability_ids_are_unique_and_every_one_has_a_group_a_title_and_an_example() -> None:
    ids = [capability.id for capability in CATALOGUE.capabilities]

    assert len(ids) == len(set(ids))
    for capability in CATALOGUE.capabilities:
        assert capability.group in CATALOGUE.groups, capability.id
        assert capability.title and capability.when and capability.example_say, capability.id


@pytest.mark.parametrize("capability", [c.id for c in CATALOGUE.capabilities])
def test_every_example_previews_a_change_on_the_synthetic_chain(
    repo: ChainRepo, capability: str
) -> None:
    example = CATALOGUE.get(capability).example

    change = plan(repo, [{"do": capability, "params": example}])

    assert change.edits, change.summary


def test_a_capability_for_several_nodes_is_one_change_of_each() -> None:
    params = {"nodes": ["P77_CHAIN/P77_B", "P77_CHAIN/P77_C"], "changes": {"MAXWAIT": "3"}}
    steps = [{"do": "change-fields", "params": params}]

    operations = CATALOGUE.operations(steps)

    assert operations == [
        {
            "op": "set-attributes",
            "params": {"node": f"P77_CHAIN/{job}", "changes": {"MAXWAIT": "3"}},
        }
        for job in ("P77_B", "P77_C")
    ]


def test_steps_run_in_order_in_one_change(repo: ChainRepo) -> None:
    steps = [
        {"do": "rename-job", "params": {"node": "P77_CHAIN/P77_E", "new_name": "P77_EAST"}},
        {"do": "change-fields", "params": {"nodes": ["P77_CHAIN/P77_EAST"],
                                           "changes": {"DESCRIPTION": "Renamed"}}},
    ]  # fmt: skip

    change = plan(repo, steps)
    apply(repo, change)

    assert change.summary.startswith("2 changes:")
    job = read_json(repo.job_file("P77_CHAIN", "P77_EAST"))
    assert job["DESCRIPTION"] == "Renamed"


@pytest.mark.parametrize(
    ("step", "message"),
    [
        ({"do": "change-fields", "params": {"changes": {"A": "1"}}},
         "change-fields: nodes is missing"),
        ({"do": "change-fields", "params": {"nodes": "P77_CHAIN/P77_B", "changes": {}}},
         "change-fields: nodes must be a list of text"),
        ({"do": "change-fields", "params": {"nodes": ["X/"], "changes": {}, "colour": "red"}},
         "change-fields: unknown parameter colour"),
        ({"do": "set-variable", "params": {"nodes": ["X/"], "name": "%%A", "value": 3}},
         "set-variable: value must be text or null"),
        ({"do": "paint", "params": {}}, "unknown capability 'paint'; known: change-fields"),
        ({"params": {}}, "step 1: say what to do"),
    ],
)  # fmt: skip
def test_wrong_steps_say_what_the_capability_expects(step: dict, message: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(InvalidChange) as caught:
        CATALOGUE.operations([step])

    assert message in str(caught.value)


def test_no_step_is_refused(repo: ChainRepo) -> None:
    with pytest.raises(InvalidChange, match="nothing to do"):
        plan(repo, [])


def test_the_menu_lists_the_groups_the_capabilities_and_how_to_ask() -> None:
    text = render_menu(CATALOGUE)

    assert text.startswith("What you can ask")
    assert "Fields\n" in text and "Conditions\n" in text
    assert "  change-fields: Change fields of jobs or folders" in text
    assert '    e.g. "Set MAXWAIT to 3 on P77_B"' in text
    assert "Questions\n" in text and "  find:" in text


def test_the_menu_of_one_capability_has_its_parameters_and_rules() -> None:
    text = render_menu(CATALOGUE, "change-fields")

    assert text.startswith("change-fields (set-attributes): Change fields of jobs or folders")
    assert "  nodes (required): list of text" in text
    assert "  changes (required): attribute -> text or null" in text
    assert "JOBNAME is changed with rename-job" in text
    assert '"nodes": ["P77_CHAIN/P77_B"]' in text


def test_the_menu_of_an_unknown_capability_is_refused() -> None:
    with pytest.raises(InvalidChange, match="unknown capability 'paint'"):
        render_menu(CATALOGUE, "paint")


def test_set_variable_adds_changes_and_removes_one_variable(repo: ChainRepo) -> None:
    node = "P77_INGEST_DAILY/P77_INGEST_LOAD"

    apply(repo, set_variable(repo, node, "%%RETRIES", "3"))
    apply(repo, set_variable(repo, node, "%%RETRIES", "4"))
    after_change = read_json(repo.job_file("P77_INGEST_DAILY", "P77_INGEST_LOAD"))["VARIABLE"]
    apply(repo, set_variable(repo, node, "%%RETRIES", None))
    after_removal = read_json(repo.job_file("P77_INGEST_DAILY", "P77_INGEST_LOAD")).get("VARIABLE")

    assert {"NAME": "%%RETRIES", "VALUE": "4"} in after_change
    assert [v for v in after_change if v["NAME"] == "%%RETRIES"] == [
        {"NAME": "%%RETRIES", "VALUE": "4"}
    ]
    assert all(v["NAME"] != "%%RETRIES" for v in after_removal or [])


def test_set_variable_refuses_to_remove_what_is_not_there(repo: ChainRepo) -> None:
    with pytest.raises(InvalidChange, match="P77_INGEST_DAILY/P77_INGEST_LOAD has no %%NOPE"):
        set_variable(repo, "P77_INGEST_DAILY/P77_INGEST_LOAD", "%%NOPE", None)


def test_the_changes_of_a_change_set_say_where_which_field_before_and_after(
    repo: ChainRepo,
) -> None:
    steps = [
        {"do": "set-variable", "params": {"nodes": ["P77_INGEST_DAILY/P77_INGEST_LOAD"],
                                          "name": "%%RETRIES", "value": "3"}},
        {"do": "insert-job", "params": {"node": "P77_INGEST_DAILY/P77_INGEST_CHECK",
                                        "after": "P77_INGEST_DAILY/P77_INGEST_INIT",
                                        "before": "P77_INGEST_DAILY/P77_INGEST_LOAD"}},
    ]  # fmt: skip

    rows = changes_of(plan(repo, steps))

    load = "P77_INGEST_DAILY/P77_INGEST_LOAD"
    assert {"where": load, "field": "%%RETRIES", "before": None, "after": "3"} in rows
    created = {"where": "P77_INGEST_DAILY/P77_INGEST_CHECK", "field": None, "before": None,
               "after": "created"}  # fmt: skip
    assert created in rows
    incond = next(r for r in rows if r["where"] == load and r["field"] == "INCOND")
    assert "P77_INGEST_CHECK" in incond["after"]


def test_a_preview_of_steps_has_the_id_apply_checks_and_what_changes(
    repo: ChainRepo,
) -> None:
    steps = [{"do": "change-fields",
              "params": {"nodes": ["P77_CHAIN/P77_B"], "changes": {"MAXWAIT": "3"}}}]  # fmt: skip

    preview = preview_steps(repo, steps, diff_lines=3)
    change = plan(repo, steps)

    assert preview["preview_id"] == fingerprint(change)[:12]
    assert preview["summary"] == "set MAXWAIT on P77_CHAIN/P77_B" and preview["warnings"] == []
    assert preview["changes"] == changes_of(change)
    assert preview["files"] == ["folders/P77_CHAIN/jobs/P77_B.json"]
    assert preview["diff"].splitlines()[-1].startswith("... ")


def test_a_preview_of_steps_that_change_nothing_has_no_id(repo: ChainRepo) -> None:
    current = read_json(repo.job_file("P77_CHAIN", "P77_B"))["TASKTYPE"]
    params = {"nodes": ["P77_CHAIN/P77_B"], "changes": {"TASKTYPE": current}}
    steps = [{"do": "change-fields", "params": params}]

    preview = preview_steps(repo, steps)

    assert preview["preview_id"] is None and preview["summary"].endswith(": nothing to change")


def test_set_variable_keeps_a_variable_without_a_value_as_it_is(repo: ChainRepo) -> None:
    path = repo.job_file("P77_CHAIN", "P77_B")
    write_json(path, {**read_json(path), "VARIABLE": [{"NAME": "%%BARE"}]})

    change = set_variable(repo, "P77_CHAIN/P77_B", "%%RETRIES", "3")
    rows = changes_of(change)
    apply(repo, change)

    assert read_json(path)["VARIABLE"] == [{"NAME": "%%BARE"}, {"NAME": "%%RETRIES", "VALUE": "3"}]
    assert [row for row in rows if row["where"] == "P77_CHAIN/P77_B"] == [
        {"where": "P77_CHAIN/P77_B", "field": "%%RETRIES", "before": None, "after": "3"}
    ]
