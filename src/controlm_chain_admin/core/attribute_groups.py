"""Grouping of the many Control-M job attributes for human-oriented views (CLI show, web UI).

The groups are presentation only; the JSON on disk and the export never depend on them.
"""

from __future__ import annotations

from collections.abc import Mapping

GROUP_ORDER: tuple[str, ...] = (
    "identity",
    "execution",
    "scheduling",
    "notifications",
    "metadata",
    "other",
)

_GROUPS: dict[str, tuple[str, ...]] = {
    "identity": (
        "JOBNAME", "MEMNAME", "DESCRIPTION", "APPLICATION", "SUB_APPLICATION", "PARENT_FOLDER",
        "FOLDER_NAME", "TASKTYPE", "APPL_TYPE", "APPL_FORM", "APPL_VER", "PRIORITY", "CRITICAL",
        "DOCLIB", "DOCMEM", "CREATED_BY", "TYPE",
    ),
    "execution": (
        "NODEID", "RUN_AS", "CMDLINE", "MEMLIB", "OVERLIB", "PAR", "OPTION", "SYSDB",
        "USE_INSTREAM_JCL", "INSTREAM_JCL", "CM_VER", "MULTY_AGENT", "PREVENT_NCT2",
        "AUTOARCH", "MAXDAYS", "MAXRUNS", "CONFIRM",
    ),
    "scheduling": (
        "DAYS", "WEEKDAYS", "DAYS_AND_OR", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL",
        "AUG", "SEP", "OCT", "NOV", "DEC", "DAYSCAL", "WEEKSCAL", "CONFCAL", "SHIFT",
        "SHIFTNUM", "RETRO", "MAXWAIT", "TIMEFROM", "TIMETO", "TIMEZONE", "CYCLIC", "INTERVAL",
        "IND_CYCLIC", "CYCLIC_TOLERANCE", "CYCLIC_TYPE", "CYCLIC_TIMES_SEQUENCE",
        "CYCLIC_INTERVAL_SEQUENCE", "MAXRERUN", "RERUNMEM", "DATES", "ACTIVE_FROM",
        "ACTIVE_TILL", "RULE_BASED_CALENDAR_RELATIONSHIP", "ADJUST_COND", "REMOVEATONCE",
        "DAYSKEEPINNOTOK", "FOLDER_ORDER_METHOD",
    ),
    "notifications": ("SHOUT", "DOMAIL", "DOSHOUT"),
    "metadata": (
        "JOBISN", "CREATION_USER", "CREATION_DATE", "CREATION_TIME", "CHANGE_USERID",
        "CHANGE_DATE", "CHANGE_TIME", "VERSION_OPCODE", "IS_CURRENT_VERSION", "VERSION_SERIAL",
        "VERSION_HOST", "DATACENTER", "VERSION", "MODIFIED", "LAST_UPLOAD", "REAL_FOLDER_ID",
        "JOBS_IN_GROUP", "PLATFORM",
    ),
}  # fmt: skip

_GROUP_OF: dict[str, str] = {attr: group for group, attrs in _GROUPS.items() for attr in attrs}


def group_of(attribute: str) -> str:
    """The display group of one attribute (``other`` when unknown)."""
    return _GROUP_OF.get(attribute, "other")


def group_attributes(attrs: Mapping[str, str]) -> dict[str, dict[str, str]]:
    """Split attributes into ordered groups; empty groups are omitted, order inside is kept."""
    grouped: dict[str, dict[str, str]] = {group: {} for group in GROUP_ORDER}
    for key, value in attrs.items():
        grouped[group_of(key)][key] = value
    return {group: values for group, values in grouped.items() if values}
