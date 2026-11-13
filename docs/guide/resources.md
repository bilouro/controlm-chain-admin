---
description: "See the CONTROL and QUANTITATIVE resources of Control-M jobs by resource, and give one to several jobs at once."
---

# Resources

A job may **hold** a resource while it runs (`CONTROL`: exclusively, `E`, or shared, `S`) or
**take** a number of units of one (`QUANTITATIVE`). Control-M shows them one job at a time;
here they are seen by resource too.

```bash
ctmchain resources                    # every resource, who uses it and how
ctmchain resources --name RQ_         # only those whose name has this text
```

```text
QUANTITATIVE  RQ_AM  1 job  QUANT=1 ONFAIL=R ONOK=R
    P77_INGEST_DAILY/P77_INGEST_INIT
```

Names are kept without the letter of the environment: `URQ_AM` in UAT and `PRQ_AM` in
production are both `RQ_AM` here, and the export puts the letter back.

## Give a resource to one job, or to several

```bash
ctmchain set-resource RQ_AM P77_CHAIN/P77_A P77_CHAIN/P77_B            # preview
ctmchain set-resource RQ_AM P77_CHAIN/P77_A P77_CHAIN/P77_B --apply
```

A resource another job uses comes **with the attributes it has there**, so that every job
asks for the same thing. One nobody uses yet needs its kind:

```bash
ctmchain set-resource RC_SHARED P77_CHAIN/P77_A --kind control --apply
```

A new `CONTROL` is held exclusively and a new `QUANTITATIVE` takes one unit; both are
released at the end. To change that, or what a job already has:

```bash
ctmchain set-resource RC_SHARED P77_CHAIN/P77_B --set TYPE=S --apply
ctmchain set-resource RQ_AM P77_INGEST_DAILY/P77_INGEST_INIT --set QUANT=2 --apply
```

## Rename and remove

```bash
ctmchain rename-resource P77_CHAIN/P77_A RQ_AM RQ_PM --apply
ctmchain remove-resource RQ_AM P77_CHAIN/P77_B --apply
```

## In the web UI

- The page of a job, and of a folder, has a **Resources** tab: what it holds and takes,
  with *Add* (the names in use are offered), how it is held or how many units, *Rename* and
  *Remove*.
- The **Resources** page lists every resource with the jobs that use it, and *Add to
  jobs…* gives it to several at once.

Every change is previewed and reviewed like any other edit. It then travels like any
change: `compare`, `take`, `package`, or a delivery.
