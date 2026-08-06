---
title: "ClickHouse Schema Management in Python"
date: 2026-08-05
description: "ClickHouse has no built-in migration tooling, so most teams hand-write MergeTree DDL forever. DBWarden lets you declare engines, codecs, materialized views, projections, dictionaries, and RBAC in your SQLAlchemy models and generates the SQL for you."
summary: "Every ClickHouse migration tool I found makes you hand-write the DDL or learn a separate schema language. I wanted to declare MergeTree specifics in the models I already had, so I built that. Here is what it looks like, and where the other tools still win."
keywords: ["clickhouse schema migration", "clickhouse migrations python", "clickhouse mergetree schema management", "clickhouse materialized view migration", "sqlalchemy clickhouse", "clickhouse ddl automation", "clickhouse migration tool"]
---

ClickHouse ships with no migration tooling. None. The database is extraordinary at what it does, and then you go to change a column and discover you're on your own.

So teams do what teams do. They write a `migrations/` folder full of `.sql` files. They wire up a runner. And from that day forward, every `MergeTree` clause, every codec, every materialized view definition gets typed by hand, reviewed by hand, and kept in sync with the application by hand.

I built [DBWarden](https://github.com/dbwarden-org/dbwarden) partly because I got tired of that. This post is about the ClickHouse side of it: what makes ClickHouse schema management genuinely harder than PostgreSQL, what tools exist today, and what it looks like when your models carry the ClickHouse specifics instead of your SQL files.

Usual disclaimer: I wrote the tool, so I'm **biased**. I'll be specific about where the alternatives are the better call.

## Why ClickHouse schema management is its own problem

If you've only done migrations against PostgreSQL or MySQL, ClickHouse breaks assumptions you didn't know you had.

**The engine is part of the schema.** A ClickHouse table isn't just columns. It's an engine, and the engine choice changes the semantics of the data. `MergeTree` stores rows. `ReplacingMergeTree` deduplicates on merge. `SummingMergeTree` collapses numeric columns. `AggregatingMergeTree` stores aggregate states rather than values. `CollapsingMergeTree` and `VersionedCollapsingMergeTree` implement cancel-and-replace semantics with a sign column. Picking one is a data-modeling decision, and it lives in the DDL.

**Sorting is structural, not an index.** `ORDER BY` in ClickHouse defines physical layout. It is not a `CREATE INDEX` you can drop and rebuild. You can **extend** a sorting key in some cases. You cannot freely change it. Getting it wrong means recreating the table and copying the data.

**Half the objects aren't tables.** A real ClickHouse deployment has materialized views doing continuous aggregation, projections giving alternate sort orders inside a table, data-skipping indexes, dictionaries for fast joins against external sources, and named collections holding credentials. Every one of those is a schema object with its own lifecycle.

**Compression is per column and it matters.** `CODEC(ZSTD(5))` on a wide string column, `DoubleDelta` on a monotonic timestamp. These aren't micro-optimizations at analytics scale. They're the difference between an affordable cluster and an expensive one. And because they're per column, a table with thirty columns has thirty small decisions encoded in its DDL, every one of which somebody has to keep straight.

**TTL is schema, not a cleanup job.** ClickHouse expires data through TTL expressions declared on the table or on individual columns. Retention policy stops being a cron job somebody wrote and becomes part of the table definition, which is better, but it also means retention changes are schema migrations and need the same review as everything else.

**Lots of changes are simply illegal.** In PostgreSQL, most things are an `ALTER` away. In ClickHouse, a surprising number of changes are `CREATE`-time commitments. Change them and you're rebuilding the table, moving the data, and swapping it in.

**And it's usually clustered.** DDL needs `ON CLUSTER`, replicated engines need consistent paths across replicas, and getting that wrong produces a schema that's subtly different on node three.

None of that is a complaint about ClickHouse. These are the tradeoffs that make it fast. But they mean "just write the SQL by hand" is a much worse plan here than it is for Postgres, because there's more to get wrong and the failure mode is a table rebuild rather than a quick `ALTER`.

## What already exists

Let me be fair about the landscape, because "nothing exists" would be false and you'd catch me at it.

**SQL migration runners.** [golang-migrate](https://github.com/golang-migrate/migrate/tree/master/database/clickhouse), goose, dbmate, `clickhouse-migrations`, PyClickHouseMigrator. These are ordered `.sql` files plus a runner that tracks which ones ran. They work. They're predictable, they stay close to the SQL, and for a lot of teams that's genuinely the right answer. Their model is simple enough to reason about at 3 AM, which counts for a great deal.

What they don't do is write the SQL. Every `MergeTree` clause is yours. There's no diffing, no drift detection, no relationship between your application's understanding of the schema and the database's.

**[Atlas](https://atlasgo.io/guides/clickhouse).** Declarative, with real ClickHouse support. You describe the desired schema, Atlas plans the diff. It's a good tool and I've said so [at length elsewhere](/works/dbwarden-vs-atlas/). The tradeoff for a Python team is that the schema lives in Atlas's own representation, HCL or SQL, as a separate artifact from your application.

**Bytebase** and similar platforms add governance: who changed what, approval flows, environment tracking. Different layer of the problem, and complementary to any of the above.

So the gap isn't "no tooling." It's narrower and more specific: **nothing lets a Python team declare ClickHouse-specific structure in the models they already maintain.** If you're running SQLAlchemy and ClickHouse, your options have been hand-written SQL or a separate schema language. That's the gap I went after.

## The basic shape

Here's a ClickHouse table in DBWarden. It's a normal SQLAlchemy model with a `class Meta` carrying the ClickHouse specifics.

```python
from datetime import date
from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from dbwarden.databases.clickhouse import CHTableMeta, ch_table, merge_tree

class Base(DeclarativeBase):
    pass

class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_date: Mapped[date] = mapped_column()
    amount: Mapped[float] = mapped_column()

    class Meta(CHTableMeta):
        ch = ch_table(
            engine=merge_tree(),
            order_by=["event_date", "id"],
            partition_by=func.toYYYYMM(Event.event_date),
        )
```

The engine, sort order, and partition expression are **declared**, not written as DDL. `dbwarden make-migrations` diffs that against the live database and emits the `CREATE TABLE` with the right engine clause. `dbwarden migrate` applies it.

The `class Meta` block is typed and validated at import time. Misspell an attribute and you get a `DBWardenConfigError` when the module loads, naming the bad attribute, rather than mysterious DDL three deploys later. That matters more in ClickHouse than elsewhere, because a typo'd engine setting can silently produce a table with different merge semantics.

The engine factories cover the family: `merge_tree`, `replacing_merge_tree`, `summing_merge_tree`, `aggregating_merge_tree`, `collapsing_merge_tree`, `versioned_collapsing_merge_tree`, `graphite_merge_tree`, and `replicated_merge_tree`. Special engines too: `distributed`, `buffer`, `join_engine`, `set_engine`, `memory`, `null`, `merge`, `dictionary_engine`, and the Log family. Integration engines are there as well, which I'll come back to.

## Codecs and column TTL

Compression settings and per-column TTL live on the column, where they belong:

```python
from datetime import datetime
from dbwarden.databases.clickhouse import CHColumnMeta, CHTableMeta, ch, ch_table, merge_tree

class SensorReading(Base):
    __tablename__ = "sensor_readings"

    sensor_id: Mapped[str] = mapped_column()
    ts: Mapped[datetime] = mapped_column()
    temp: Mapped[float] = mapped_column()
    humidity: Mapped[float] = mapped_column()

    class Meta(CHTableMeta):
        ch = ch_table(
            engine=merge_tree(),
            order_by=["sensor_id", "ts"],
        )

        class temp(CHColumnMeta):
            ch = ch.field(codec="ZSTD(5)")

        class ts(CHColumnMeta):
            ch = ch.field(codec="DoubleDelta", ttl="ts + toIntervalDay(90)")

        class humidity(CHColumnMeta):
            ch = ch.field(ttl="ts + toIntervalDay(30)")
```

Inner classes named after columns. `DoubleDelta` on the timestamp because it's monotonic, `ZSTD(5)` on the value column, different retention per column. When you change a codec, DBWarden generates the `MODIFY COLUMN` statement. When you change a TTL, same.

The thing I like about this: the compression strategy sits **next to the column it compresses**, in the file your application already imports. Not in a migration from eleven months ago that nobody remembers.

## Materialized views, which are the actual hard part

Materialized views are where ClickHouse schema management gets genuinely difficult, and where hand-written SQL hurts most. A ClickHouse MV is a trigger that fires on insert and writes into a target table. There are two shapes: the MV creates and owns an inner table, or it writes `TO` a table you defined separately. Changing the target is a different operation from changing the query, and changing the query is sometimes `MODIFY QUERY` and sometimes a full recreate.

DBWarden models both shapes. Here's the one where the class **is** the target and the view is generated for you:

```python
from dbwarden.databases.clickhouse import CHViewMeta, MaterializedView, materialized_view, merge_tree

class EventDaily(MaterializedView):
    __tablename__ = "event_daily"

    date: Mapped[date] = mapped_column(primary_key=True)
    total: Mapped[float] = mapped_column()
    cnt: Mapped[int] = mapped_column()

    class Meta(CHViewMeta):
        ch = materialized_view(
            select="SELECT event_date AS date, sum(amount) AS total, "
                   "count(*) AS cnt FROM events GROUP BY event_date",
            engine=merge_tree(),
            order_by=["date"],
        )
```

You declare the target's columns and engine, plus the `SELECT` that feeds it. DBWarden emits both the target table and the `CREATE MATERIALIZED VIEW`, and keeps them consistent. Refreshable materialized views (ClickHouse 24.3 and up) are supported too.

For `AggregatingMergeTree` pipelines, there's a dedicated construct, because writing aggregate-state SQL by hand is genuinely unpleasant:

```python
from dbwarden.databases.clickhouse import AggregatingView, CHViewMeta, agg, aggregating_view

class EventAggregated(AggregatingView):
    __tablename__ = "event_aggregated"

    class Meta(CHViewMeta):
        ch = aggregating_view(
            source=EventDaily,
            group_by=[EventDaily.date],
            aggregates=[
                agg.sum(EventDaily.total, "Float64").as_("state"),
            ],
            order_by=[EventDaily.date],
        )
```

The aggregate columns get **derived from the source model**. You say "sum this column, grouped by that one," and the `AggregateFunction` column types and `sumState(...)` expressions are generated. If you've ever hand-maintained a three-level rollup of raw table into daily MV into monthly aggregate, you know the specific pain of keeping the state types aligned across all three by hand.

## Projections, skip indexes, dictionaries

**Projections** give a table an alternate physical sort order, so one table can serve queries that want different orderings. **Skip indexes** let ClickHouse skip granules that can't match. Both are declared as table metadata, and both support `MATERIALIZE` as an explicit data operation for existing rows, which is important because adding a projection doesn't retroactively build it.

**Dictionaries** are ClickHouse's in-memory lookup structures, with a source (another table, a database, an HTTP endpoint), a layout (`flat`, `hashed`, `complex_key_hashed`, and so on), and a lifetime controlling refresh. DBWarden declares source, layout, and lifetime as structured config rather than as a wall of `CREATE DICTIONARY` SQL.

**Integration engines** get the same treatment. Kafka, S3, S3Queue, RabbitMQ, NATS, Redis, MongoDB, MySQL, PostgreSQL, HDFS, URL, and File all have typed settings objects. A Kafka ingestion table plus the materialized view that drains it into a `MergeTree` is a very common ClickHouse pattern, and it's the kind of thing that's easy to get subtly wrong when it's a hand-typed settings blob.

**Named collections** hold credentials for those integrations. These are deliberately **declare-only**: DBWarden manages their existence but never diffs their values, because reading secrets back out to compare them is not a behavior I want in a migration tool. Note that named collections ship in the `dbwarden-ch-rbac` plugin rather than core, alongside the RBAC objects below.

## RBAC as configuration

ClickHouse RBAC covers roles, users, row policies, quotas, settings profiles, and grants. In most projects this lives in a wiki page and a shell script somebody ran once.

DBWarden declares it in your database config. Be clear on where this lives, though: the `ch_*` config keys below and the handlers that emit their DDL both belong to the **`dbwarden-ch-rbac` plugin**, not core. Install it with `dbwarden plugin add dbwarden-ch-rbac`. Without it, declaring these keys raises `DBWardenConfigError` when your config loads, naming the plugin to install, rather than quietly producing nothing.

```python
from dbwarden import database_config
from dbwarden.databases.clickhouse import ChGrantSpec, ChRoleSpec, ChUserSpec

analytics = database_config(
    database_name="analytics",
    database_type="clickhouse",
    database_url_sync="clickhouse://localhost:9000",
    ch_roles=[ChRoleSpec("analyst"), ChRoleSpec("engineer")],
    ch_users=[
        ChUserSpec(name="bob", default_role="analyst"),
    ],
    ch_grants=[
        ChGrantSpec(privileges=["SELECT"], on="analytics.*", to="analyst"),
    ],
)
```

Roles and grants become part of the reviewed, versioned migration flow. Adding a role is a diff. Dropping a user is a diff, and a gated one. Access control stops being tribal knowledge.

That plugin split is deliberate and worth understanding, because it applies across the project. Core owns tables, columns, engines, materialized views, projections, skip indexes, and dictionaries. Plugins own RBAC on both ClickHouse and PostgreSQL, PostgreSQL types and sequences, PostgreSQL functions and triggers and extensions, seed data, and the Testcontainers sandbox providers. So the ClickHouse table modeling in this post is core, and the access-control section is a plugin away.

A plugin owns its config keys, not just its handlers, and core validates every keyword you pass to `database_config()` against the plugins actually installed. A key belonging to a missing plugin fails with an install hint; a key no plugin owns fails as an unknown argument, so a typo like `ch_role` never silently does nothing. Both happen at config load, which is the moment you can still fix it cheaply.

## The feature I actually care about: knowing what you can't change

Everything above is convenience. This part is the reason I think a ClickHouse-aware tool earns its place.

ClickHouse changes fall into very different risk categories, and the DDL doesn't warn you. DBWarden classifies every generated operation into three levels:

- **INFO**, applied automatically. `ADD COLUMN`, `ADD INDEX`, `ADD PROJECTION`, settings changes, TTL changes.
- **WARN**, applied but logged loudly. `DROP COLUMN`, `DROP TABLE`, `DROP INDEX`, mutations, partition drop and replace.
- **CRITICAL**, **skipped unless you pass `--force`**. Engine changes, `ORDER BY` non-extensions, `PRIMARY KEY` changes, materialized view `TO` target changes, incompatible type changes, and `LowCardinality` or `Nullable` toggles.

That last category is the one that ruins weeks. Changing `ORDER BY` from `(a, b)` to `(c)` is not an `ALTER`. It's a table rebuild. DBWarden refuses it by default and tells you why:

```
CRITICAL: Changing ORDER BY from (a, b) to (c) requires --force
```

And when you do force it, you get the whole recreate pipeline written out, so you can see exactly what will happen to your data before it happens:

```
DETACH TABLE events
CREATE TABLE events_new ...
INSERT INTO events_new SELECT * FROM events
RENAME TABLE ...
```

Compare that to a hand-written migration. You write `ALTER TABLE events MODIFY ORDER BY (c)`, ClickHouse rejects it, and now you're improvising a data migration at whatever hour you discovered it. The tool knowing which changes are structural is worth more than all the declaration syntax above it.

There's a `--dry-run` to preview and a `--sandbox` to replay first. On the sandbox flag, be precise about what you get: core ships an in-memory SQLite provider, which for ClickHouse is close to useless. Install the `dbwarden-sandbox` plugin and you get Testcontainers-backed real ClickHouse replay, which is the version worth trusting.

## A day in the life

Abstract feature lists are easy to nod along to. Here are two real changes, done both ways.

**Change one: add a column.** The easy case, and the one every tool handles.

With a SQL runner you create `0007_add_user_agent.sql`, type `ALTER TABLE events ADD COLUMN user_agent String`, and remember to also update whatever your application believes the schema is. Two places, by hand, kept in sync by discipline.

With DBWarden you add `user_agent: Mapped[str] = mapped_column()` to the model and run `make-migrations`. You get:

```
ALTER TABLE events ADD COLUMN user_agent String   (INFO)
```

Classified `INFO`, applied automatically, and the model that generated it is the same model your application imports. One place.

**Change two: change the sorting key.** The case that separates the tools.

With a SQL runner you write `ALTER TABLE events MODIFY ORDER BY (c)`, it fails, and now you're learning about ClickHouse's structural constraints during a deploy. What follows is an improvised rebuild: create a new table with the right sort order, copy the data across, swap the names, hope nothing wrote to the old table mid-copy.

With DBWarden you change `order_by` in the model, run `make-migrations`, and get stopped:

```
CRITICAL: Changing ORDER BY from (a, b) to (c) requires --force
```

No SQL generated, nothing applied. When you pass `--force`, the generated migration contains the full rebuild rather than a statement ClickHouse will reject:

```
DETACH TABLE events
CREATE TABLE events_new ...
INSERT INTO events_new SELECT * FROM events
RENAME TABLE ...
```

The difference isn't convenience. It's *when* you find out. One tool tells you at generation time on your laptop, with the rebuild written out for review. The other tells you at apply time, in whatever environment you were deploying to.

## Drift, and knowing your cluster still matches your models

There's a failure mode specific to analytics databases: somebody adds a column directly on the cluster to unblock a dashboard, and it's never mentioned again. Six months later nobody knows which of the forty tables match their definitions.

Because DBWarden diffs models against **live state**, that drift surfaces the next time anyone generates a migration. Unexpected entries appear in the diff, on someone's laptop, before any deploy. There's also `dbwarden diff` as a read-only comparison you can run whenever you're suspicious, and it outputs as a Rich table, JSON, or raw SQL depending on whether a human or a pipeline is reading it.

Snapshots make that cheap. After every migration a checksummed JSON snapshot of the schema lands in `.dbwarden/schemas/`, so most comparisons don't require interrogating the cluster at all.

## Adopting it on a database that already exists

Nobody starts fresh. You have ClickHouse tables in production right now, defined by SQL files of uncertain provenance.

```bash
dbwarden generate-models --database analytics
```

This reverse-engineers the live database into SQLAlchemy models with the `class Meta` blocks filled in: engines, sort keys, partition expressions, codecs, TTLs, materialized views, projections. `--base` points it at your project's existing declarative base rather than generating its own.

The round-trip is verified rather than assumed. The project's audit harness runs 39 cases against ClickHouse 24.3 and 26.6 and reports zero drift, with a single canonicalizer code path and no version branching between them. Which is to say: models generated from a live database regenerate that same database. I mention the number because "supports ClickHouse" is a claim every tool makes, and the useful question is always what was measured.

From there you generate a baseline migration and mark it applied with `dbwarden migrate --baseline`, and your existing schema is now under management without anything being rebuilt.

## Clusters, which are not covered

One limitation to state plainly, because it's the kind you don't want to discover on a three-node deployment: cluster-aware DDL is **not supported**. Generated statements do not carry `ON CLUSTER`, and there's no configuration that makes them. If your ClickHouse is clustered, keep whatever you use for propagating DDL across nodes today.

Everything else in this post works against a clustered instance the same as a single node, since the table, view, and projection definitions themselves don't change. It's specifically the cluster-wide propagation of the generated DDL that isn't there.

## Where the other tools fit better

I mean this section.

**You're not a Python shop.** DBWarden requires SQLAlchemy, Python 3.12+. If your ClickHouse is fed by Go services, use golang-migrate or Atlas. This isn't a candidate for you and I'd rather say so than waste your afternoon.

**Your ClickHouse schema is small and stable.** If it's six tables that change twice a year, a `migrations/` folder and dbmate is genuinely less machinery than adopting a schema tool. Simplicity has real operational value. Don't buy a diff engine to manage six tables.

**You want to hand-tune every statement.** Some teams want to write the exact DDL, in the exact order, with the exact settings. That's a legitimate preference, especially with unusual cluster topologies, and a SQL runner respects it. DBWarden generates SQL from models; that's the trade.

**You need governance more than generation.** If your actual problem is approvals and audit trails across environments, Bytebase solves that and DBWarden doesn't try to.

**You want one tool across many databases and languages.** Atlas covers more backends and every ecosystem. DBWarden covers PostgreSQL, MySQL, ClickHouse, MariaDB, and SQLite for local development, from Python only.

## Where I think it genuinely wins

**You run ClickHouse next to an OLTP database.** This is the common case and the strongest argument. Postgres for the application, ClickHouse for analytics. Normally that's two schema workflows: Alembic on one side, hand-written SQL on the other. DBWarden covers both with the same models, same commands, same migration files, same review process.

**Your ClickHouse schema is genuinely complex.** Materialized view chains, aggregate states, projections, dictionaries, Kafka ingestion. The more ClickHouse-specific structure you have, the more the typed declarations pay off against hand-written DDL.

**You've been bitten by an illegal change.** If you've ever discovered mid-deploy that a sorting key can't be altered, the safety classification alone is the pitch.

**You want CI without a ClickHouse container.** Export model state once with `dbwarden export-models`, commit it, and generate migrations with `make-migrations --offline` on any machine. No ClickHouse service in the pipeline just to plan a schema change. Anyone who has waited on a ClickHouse container to become healthy in CI, only to discover the job was checking whether a column name changed, will recognize why I built this.

**Your ClickHouse knowledge is unevenly distributed across the team.** This one is less about features and more about how teams actually work. Usually one or two people genuinely understand MergeTree, and everyone else copies an existing table definition and edits it. Typed declarations plus import-time validation plus a safety classifier turn a lot of that tribal knowledge into something the tooling enforces. The person who doesn't know that sorting keys are structural gets stopped by the tool instead of by an incident.

## Common questions

**Does this replace my ClickHouse SQL knowledge?** No, and it shouldn't. You still need to know why `ReplacingMergeTree` deduplicates on merge rather than on insert, and why your sorting key determines query performance. What changes is that you stop *typing* the DDL and start declaring the decisions. The generated SQL is right there in the migration file, so if anything you end up reading more ClickHouse DDL than before, just not writing it.

**What if DBWarden generates SQL I don't want?** Read it in the migration file and change the model, or write the migration yourself. `dbwarden new` creates a manual SQL migration that lives in the same versioned sequence as generated ones. The generator handles the common cases; the escape hatch is always there for the odd one.

**Does it handle ClickHouse version differences?** The canonicalizer has **zero version branching**: one code path covers 24.3 through 26.6, verified by the same 39 audit cases against both, with zero drift. That's a deliberate design constraint rather than an accident. Version-specific branches in a schema differ are where subtle bugs accumulate.

**Can it manage both my Postgres and my ClickHouse?** Yes, and this is the strongest reason to use it. Declare both in `dbwarden.py`, assign models per database, and run `dbwarden migrate --all` to apply to each in sequence. Same models, same commands, same reviewable SQL artifacts, same rollback contract. In my experience this is where most of the value lands, because the alternative is genuinely two separate toolchains with two separate review cultures.

**What about the analytics-specific stuff like backfills?** Data operations are modeled: partition operations, mutations, `OPTIMIZE`, and `POPULATE` for materialized views. Materializing a projection on existing data is an explicit operation rather than something you hope happened, which matters because adding a projection does nothing to rows already written.

**Is ClickHouse support actually complete, or is it a checkbox?** Fair question, and the honest answer is to look at what's measured rather than what's claimed. The round-trip audit is 39 cases across two ClickHouse versions with zero drift, and the docs list deliberate exclusions explicitly rather than staying quiet about them. Replicated databases are extraction-only, which is documented as a gap. I'd rather point you at the gaps than have you find them.

**What does adopting it cost?** Python 3.12+ and SQLAlchemy 2.0+ as hard floors. A new mental model where models are authoritative and migration files are artifacts. And the honest one: if your ClickHouse schema is small and stable, this is more machinery than your problem needs.

## The short version

ClickHouse gives you no migration story, so the ecosystem filled the gap with SQL runners, and SQL runners mean hand-writing DDL forever. Atlas offers a declarative path if you'll maintain schema files separately from your application.

What didn't exist, as far as I could find, was the option to declare ClickHouse's specifics in the models a Python team already owns: engine families, codecs, TTLs, materialized views, aggregate states, projections, dictionaries, and RBAC. All typed, all validated at import, all diffed into reviewable SQL with the structural changes flagged before they detonate.

That's the thing I wanted, so that's the thing I built.

---

The [ClickHouse documentation](https://dbwarden.emiliano-go.com/databases/clickhouse/) covers all of it in more depth than a blog post can. If you'd rather start from the comparison angle, there's [DBWarden vs Alembic](/works/dbwarden-vs-alembic/) on declarative versus imperative, [DBWarden vs Atlas](/works/dbwarden-vs-atlas/) on two declarative tools, and [DBWarden vs Django migrations](/works/dbwarden-vs-django-migrations/).
