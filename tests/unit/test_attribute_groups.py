"""Presentation grouping of job attributes."""

from __future__ import annotations

from controlm_chain_admin.core.attribute_groups import GROUP_ORDER, group_attributes, group_of


def test_known_attributes_land_in_their_group_and_unknown_in_other() -> None:
    assert group_of("JOBNAME") == "identity"
    assert group_of("CMDLINE") == "execution"
    assert group_of("MAXWAIT") == "scheduling"
    assert group_of("JOBISN") == "metadata"
    assert group_of("SOMETHING_NEW") == "other"


def test_group_attributes_keeps_group_order_and_attribute_order_and_drops_empty_groups() -> None:
    attrs = {"CMDLINE": "x", "JOBNAME": "J", "NODEID": "n", "ZZZ": "?", "MEMNAME": "M"}

    grouped = group_attributes(attrs)

    assert list(grouped) == ["identity", "execution", "other"]
    assert list(grouped["identity"]) == ["JOBNAME", "MEMNAME"]
    assert list(grouped["execution"]) == ["CMDLINE", "NODEID"]
    assert grouped["other"] == {"ZZZ": "?"}
    assert set(grouped) <= set(GROUP_ORDER)
