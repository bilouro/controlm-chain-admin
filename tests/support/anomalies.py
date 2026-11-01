# ruff: noqa: E501  (XML lines mirror the real export layout and must not be wrapped)
"""A synthetic export (application P77, UAT letters) with one of each chain anomaly.

Jobs A -> B -> C -> D form a chain; the anomalies are documented inline. Used by the validate,
links and graph tests.
"""

from __future__ import annotations

ANOMALY_EXPORT: bytes = b"""<?xml version="1.0" encoding="utf-8"?>
<!--Exported at 02-01-2026 00:00:00-->
<DEFTABLE xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="Folder.xsd">
    <SMART_FOLDER JOBISN="1" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="UP77_BATCH" JOBNAME="UP77_CHAIN" RUN_AS="aup77proc" TASKTYPE="SMART Table" FOLDER_NAME="UP77_CHAIN" TYPE="2">
        <JOB JOBISN="2" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="UP77_BATCH" MEMNAME="UP77_A" JOBNAME="UP77_A" RUN_AS="aup77proc" TASKTYPE="Command" NODEID="UP77_BATCH" CMDLINE="/opt/p77/bin/a.ksh" PARENT_FOLDER="UP77_CHAIN">
            <OUTCOND NAME="UP77_A-UP77_B_OK" ODATE="ODAT" SIGN="+" />
            <OUTCOND NAME="UP77_A-UP77_C_OK" ODATE="ODAT" SIGN="+" />
        </JOB>
        <JOB JOBISN="3" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="UP77_BATCH" MEMNAME="UP77_B" JOBNAME="UP77_B" RUN_AS="aup77proc" TASKTYPE="Command" NODEID="UP77_BATCH" CMDLINE="/opt/p77/bin/b.ksh" PARENT_FOLDER="UP77_CHAIN">
            <INCOND NAME="UP77_A-UP77_B_OK" ODATE="ODAT" AND_OR="A" />
            <OUTCOND NAME="UP77_A-UP77_B_OK" ODATE="ODAT" SIGN="-" />
            <OUTCOND NAME="UP77_B-UP77_C_OK" ODATE="ODAT" SIGN="+" />
            <ON STMT="*" CODE="NOTOK">
                <DOCOND NAME="UP77_B-UP77_C_OK" ODATE="ODAT" SIGN="+" />
            </ON>
        </JOB>
        <JOB JOBISN="4" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="UP77_BATCH" MEMNAME="UP77_C" JOBNAME="UP77_C" RUN_AS="aup77proc" TASKTYPE="Command" NODEID="UP77_BATCH" CMDLINE="/opt/p77/bin/c.ksh" PARENT_FOLDER="UP77_CHAIN">
            <INCOND NAME="UP77_B-UP77_C_OK" ODATE="ODAT" AND_OR="A" />
            <OUTCOND NAME="UP77_OLDNAME-UP77_D_OK" ODATE="ODAT" SIGN="+" />
        </JOB>
        <JOB JOBISN="5" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="UP77_BATCH" MEMNAME="UP77_D" JOBNAME="UP77_D" RUN_AS="aup77proc" TASKTYPE="Command" NODEID="UP77_BATCH" CMDLINE="/opt/p77/bin/d.ksh" PARENT_FOLDER="UP77_CHAIN">
            <INCOND NAME="UP77_OLDNAME-UP77_D_OK" ODATE="ODAT" AND_OR="A" />
            <OUTCOND NAME="UP77_OLDNAME-UP77_D_OK" ODATE="ODAT" SIGN="-" />
            <OUTCOND NAME="UP77_D-UP77_NOBODY_OK" ODATE="ODAT" SIGN="+" />
        </JOB>
        <JOB JOBISN="6" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="UP77_BATCH" MEMNAME="UP77_E" JOBNAME="UP77_E" RUN_AS="aup77proc" TASKTYPE="Command" NODEID="UP77_BATCH" CMDLINE="/opt/p77/bin/e.ksh" PARENT_FOLDER="UP77_CHAIN">
            <INCOND NAME="UP77_A-UP77_E_OK" ODATE="ODAT" AND_OR="A" />
            <INCOND NAME="UP77_GHOST-UP77_E_OK" ODATE="ODAT" AND_OR="A" />
            <OUTCOND NAME="UP77_A-UP77_E_OK" ODATE="ODAT" SIGN="-" />
            <OUTCOND NAME="UP77_GHOST-UP77_E_OK" ODATE="ODAT" SIGN="-" />
        </JOB>
        <JOB JOBISN="7" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="UP77_BATCH" MEMNAME="UP77_F" JOBNAME="UP77_F" RUN_AS="aup77proc" TASKTYPE="Dummy" NODEID="UP77_BATCH" PARENT_FOLDER="UP77_CHAIN">
            <INCOND NAME="WEIRD_NAME" ODATE="ODAT" AND_OR="A" />
            <OUTCOND NAME="WEIRD_NAME" ODATE="ODAT" SIGN="-" />
        </JOB>
        <JOB JOBISN="8" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="UP77_BATCH" MEMNAME="UP77_F" JOBNAME="UP77_F" RUN_AS="aup77proc" TASKTYPE="Dummy" NODEID="UP77_BATCH" PARENT_FOLDER="UP77_CHAIN" />
        <INCOND NAME="UP77_OTHER-UP77_CHAIN_OK" ODATE="ODAT" AND_OR="A" />
        <OUTCOND NAME="UP77_OTHER-UP77_CHAIN_OK" ODATE="ODAT" SIGN="-" />
        <OUTCOND NAME="UP77_CHAIN-UP77_NEXT_OK" ODATE="ODAT" SIGN="+" />
    </SMART_FOLDER>
</DEFTABLE>
"""

#: What validate must report for ANOMALY_EXPORT (neutral names), by finding code.
EXPECTED_FINDINGS: dict[str, set[str]] = {
    "dangling": {"P77_A-P77_E_OK"},  # P77_A exists but never emits it: broken chain
    "dangling-external": {"P77_GHOST-P77_E_OK", "P77_OTHER-P77_CHAIN_OK"},
    "dangling-unknown": {"WEIRD_NAME"},
    "unconsumed": {"P77_A-P77_C_OK"},  # P77_C exists but never waits for it
    "unconsumed-external": {"P77_D-P77_NOBODY_OK", "P77_CHAIN-P77_NEXT_OK"},
    "never-cleaned": {"P77_B-P77_C_OK"},
    "stale-name": {"P77_OLDNAME-P77_D_OK"},
    "duplicate-jobname": {"P77_F"},
    "non-standard-name": {"WEIRD_NAME"},
}
