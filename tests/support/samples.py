# ruff: noqa: E501  (XML lines mirror the real export layout and must not be wrapped)
"""Synthetic Control-M export snippets used by the public test suite.

Everything here is fictional (application ``P77``). The byte layout mirrors a real
``DEFTABLE`` export: UTF-8, LF line endings, 4-space indentation, ``<X ... />`` for empty
elements, attribute values escaped with ``&amp; &lt; &gt; &quot;``.
"""

from __future__ import annotations

SAMPLE_EXPORT: bytes = b"""<?xml version="1.0" encoding="utf-8"?>
<!--Exported at 01-01-2026 00:00:00-->
<DEFTABLE xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="Folder.xsd">
    <SMART_FOLDER JOBISN="1" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="UP77_BATCH" JOBNAME="UP77_INGEST_DAILY" DESCRIPTION="Daily ingest &amp; load" CREATED_BY="user01" RUN_AS="aup77proc" TASKTYPE="SMART Table" FOLDER_NAME="UP77_INGEST_DAILY" TYPE="2">
        <JOB JOBISN="2" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="UP77_BATCH" MEMNAME="UP77_INGEST_INIT" JOBNAME="UP77_INGEST_INIT" DESCRIPTION="Init &lt;run&gt; &quot;daily&quot;" RUN_AS="aup77proc" TASKTYPE="Command" NODEID="UP77_BATCH" CMDLINE="/opt/p77/bin/init.ksh -d %%ODATE" PARENT_FOLDER="UP77_INGEST_DAILY">
            <QUANTITATIVE NAME="URQ_AM" QUANT="1" ONFAIL="R" ONOK="R" />
            <OUTCOND NAME="UP77_INGEST_INIT-UP77_INGEST_LOAD_OK" ODATE="ODAT" SIGN="+" />
            <RULE_BASED_CALENDARS NAME="UP77_DAILY" />
        </JOB>
        <JOB JOBISN="3" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="UP77_BATCH" MEMNAME="UP77_INGEST_LOAD" JOBNAME="UP77_INGEST_LOAD" DESCRIPTION="Load positions" RUN_AS="aup77proc" TASKTYPE="Command" NODEID="UP77_BATCH" CMDLINE="/opt/p77/bin/load.ksh -d %%ODATE" PARENT_FOLDER="UP77_INGEST_DAILY">
            <INCOND NAME="UP77_INGEST_INIT-UP77_INGEST_LOAD_OK" ODATE="ODAT" AND_OR="A" />
            <OUTCOND NAME="UP77_INGEST_INIT-UP77_INGEST_LOAD_OK" ODATE="ODAT" SIGN="-" />
            <ON STMT="*" CODE="NOTOK">
                <DOSHOUT URGENCY="R" MESSAGE="Alert" DEST="EM" />
                <DOMAIL URGENCY="R" DEST="ops@example.com" SUBJECT="[P77][UAT] Load failed" MESSAGE="Job %%JOBNAME failed" ATTACH_SYSOUT="Y" />
            </ON>
        </JOB>
        <VARIABLE NAME="%%GEIENV" VALUE="u" />
        <INCOND NAME="UP77_PRICING-UP77_INGEST_DAILY_OK" ODATE="ODAT" AND_OR="A" />
        <OUTCOND NAME="UP77_PRICING-UP77_INGEST_DAILY_OK" ODATE="ODAT" SIGN="-" />
    </SMART_FOLDER>
    <SMART_FOLDER JOBISN="1" APPLICATION="OTHER_APP" SUB_APPLICATION="UOTH_TOOLS" JOBNAME="UOTH_HOUSEKEEPING" CREATED_BY="user02" RUN_AS="root" TASKTYPE="SMART Table" FOLDER_NAME="UOTH_HOUSEKEEPING" TYPE="2">
        <JOB JOBISN="2" APPLICATION="OTHER_APP" SUB_APPLICATION="UOTH_TOOLS" MEMNAME="cleanup.ksh" JOBNAME="UOTH_CLEANUP" TASKTYPE="Command" NODEID="srvu-oth-bat1" CMDLINE="/opt/oth/bin/cleanup.ksh" PARENT_FOLDER="UOTH_HOUSEKEEPING" />
    </SMART_FOLDER>
</DEFTABLE>
"""

SAMPLE_APPLICATIONS: tuple[str, ...] = ("P77_RISK_ENGINE", "OTHER_APP")
SAMPLE_FOLDER_NAMES: tuple[str, ...] = ("UP77_INGEST_DAILY", "UOTH_HOUSEKEEPING")
