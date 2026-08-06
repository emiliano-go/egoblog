---
title: "DBWarden vs Django Migrations: Bringing makemigrations to SQLAlchemy"
date: 2026-08-05
description: "Django proved that models should drive migrations. DBWarden brings that workflow to SQLAlchemy, with plain SQL artifacts and a rollback contract. A detailed comparison from DBWarden's creator, including where Django's system is still ahead."
summary: "Django migrations and DBWarden agree that models should drive schema changes. This post explains how each one does it, where the artifacts differ, and why a FastAPI developer missing makemigrations is exactly who DBWarden was built for."
keywords: ["django migrations alternative", "makemigrations for sqlalchemy", "sqlalchemy migrations", "dbwarden vs django", "fastapi database migrations", "declarative database migrations python"]
---

Same disclaimer as the rest of this series: I built [DBWarden](https://github.com/dbwarden-org/dbwarden), so I am **biased**. And this post carries a debt on top of the bias. Django's migration system is, as far as I'm concerned, the reason a whole generation of Python developers expects schema changes to flow **from models**. Django normalized the idea. If you've ever typed `makemigrations` and felt that small satisfaction of the framework just handling it, you already believe most of what DBWarden believes.

So this is not a takedown. It's a family portrait. Django migrations and DBWarden sit on the same branch of the tree: both are model-driven, both generate changes instead of asking you to author them. The differences are in the **artifacts**, the **coupling**, and the **guarantees**. And as with the other posts in this series, I'll explain each piece properly before comparing, because you probably know one tool much better than the other.

One scoping note up front. If you're building a Django application, use Django migrations. Full stop, no asterisks. DBWarden is for **SQLAlchemy**, which means FastAPI, Flask, Litestar, plain scripts, data pipelines, and every Python service that isn't Django. The comparison matters because so many of us learned migrations inside Django and then moved to SQLAlchemy stacks, looked around, and missed what we left behind.

## What Django migrations are

For readers coming from the SQLAlchemy side who never used Django, here's the system, properly. A little history helps too. Django didn't always have migrations; for years the community relied on a third-party tool called South, and its ideas were folded into Django itself in version 1.7. That lineage matters because it means Django's system was designed from a decade of real-world lessons about what model-driven migrations need: state reconstruction, dependency ordering, an interactive rename questioner. It's a mature design.

Django models are Python classes declaring fields, and they are the **canonical description** of your schema:

```python
from django.db import models

class User(models.Model):
    email = models.EmailField(unique=True)
    bio = models.TextField(blank=True, default="")

    class Meta:
        db_table = "users"
```

When you change a model, you run `python manage.py makemigrations`. Django compares your models against its idea of the current schema and writes a **migration file**: a Python module containing operation objects.

```python
class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_user_last_login")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="bio",
            field=models.TextField(blank=True, default=""),
        ),
    ]
```

Then `python manage.py migrate` applies pending migrations, recording them in a `django_migrations` table. You can migrate backwards by naming an earlier migration, view the SQL a migration would run with `sqlmigrate`, list state with `showmigrations`, and compress a long chain with `squashmigrations`.

Two design details matter for this comparison, and they're clever, so let's give them their due.

**First: the state is rebuilt from the migration files themselves.** When `makemigrations` runs, Django doesn't inspect your database. It replays your entire migration history in memory, reconstructs what the models *should* look like at the end of it, and diffs your actual models against that reconstruction. Elegant consequence: generating migrations needs no database connection at all. Important consequence: the migration chain, not the database, is what your models get compared against. Hold that thought.

**Second: the interactive questioner.** Rename a field and `makemigrations` asks you, in the terminal: "Did you rename user.name to user.full_name?". Ambiguity gets resolved by a human at generation time. It's a genuinely good piece of design that most tools never copied.

And then there's the feature everyone remembers: **`RunPython`**. A migration can carry arbitrary Python that runs inside the migration sequence, with access to historical versions of your models. Backfills, data transformations, splitting a column into two: Django lets schema and data changes interleave in one ordered history. It's the system's superpower, and I'll come back to it in the fairness section.

## What DBWarden is

DBWarden gives the same model-driven workflow to SQLAlchemy. Your models are the schema definition; the tool derives the rest: migration SQL, rollbacks, snapshots, and safety checks.

Configuration is one `dbwarden.py` file declaring your databases:

```python
from dbwarden import database_config

primary = database_config(
    database_name="primary",
    default=True,
    database_type="postgresql",
    database_url_sync="postgresql://user:pass@localhost:5432/myapp",
    database_url_async="postgresql+asyncpg://user:pass@localhost:5432/myapp",
)
```

Models are normal SQLAlchemy models, extended by an optional, typed `class Meta` that will feel immediately familiar to Django hands:

```python
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import declarative_base
from dbwarden.databases import TableMeta, IndexSpec

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    bio = Column(Text, nullable=True)

    class Meta(TableMeta):
        comment = "Core user accounts"
        indexes = [
            IndexSpec(name="ix_users_bio", columns=["bio"]),
        ]
```

Yes, the resemblance to Django's `class Meta` is intentional. It's a good idea and I stole it openly. Django proved that "the stuff about the table that isn't a column" deserves a structured home on the model, instead of being scattered across config files and raw SQL. DBWarden's version is **typed and validated at import time**: a metaclass checks every attribute, so misspelling one gets you a `DBWardenConfigError` naming it the moment the module loads, not silently wrong DDL three deploys later. And it goes deeper than Django's, because it has to cover more ground: backend-specific subclasses like `PGTableMeta` expose PostgreSQL partitioning, row-level security, fillfactor, and tablespaces; `MyTableMeta` covers MySQL engines, charsets, and row formats; `CHTableMeta` covers ClickHouse engine specs. Column-level Meta classes exist too, so a comment or a storage option lives next to the column it describes. The index story alone covers partial indexes with `WHERE` clauses, covering indexes with `INCLUDE` columns, `USING` access methods, `NULLS NOT DISTINCT`, per-column sort order, and storage parameters, all as typed `IndexSpec` fields rather than strings you hope are spelled right.

The workflow rhymes with Django's on purpose:

```bash
dbwarden init
dbwarden make-migrations "add bio to users"
dbwarden migrate
dbwarden status
```

The lineage here is specific, so let me be precise about it. `make-migrations` is Django's `makemigrations` with a hyphen, and `migrate` is the same word doing the same job. Those two are deliberate. The rest of the CLI is not Django's: `init`, `status`, `history`, and `rollback` follow the conventions you'd recognize from Alembic and from general command-line tooling, not from `startproject` and `showmigrations`. So the workflow rhymes at the point where you generate and apply, which is the part you type every day, and diverges everywhere else.

And the artifact that comes out is where the two systems really part ways, so let's get into the actual differences.

## The artifact: Python operations vs plain SQL

**What this piece is:** the file that gets generated, reviewed, committed, and executed.

**Django's artifact** is Python: a list of operation objects (`AddField`, `AlterField`, `RunPython`) that Django's engine translates into SQL for your backend at execution time. You can preview the SQL with `sqlmigrate`, but the SQL is a *rendering*, produced on demand. The thing in your repo, the thing your reviewer reads, is the operations. Executing a migration means running Django.

**DBWarden's artifact** is the SQL itself:

```sql
-- upgrade
ALTER TABLE users ADD COLUMN bio TEXT;

-- rollback
ALTER TABLE users DROP COLUMN bio;
```

What you review is what will run, byte for byte. Your DBA can read it without knowing Python. Your deploy pipeline can execute it with psql if it wants to; the `dbwarden migrate` runner is convenient, not required. And on PostgreSQL the generated SQL carries operational defaults like `CREATE INDEX CONCURRENTLY`, because index builds that lock production tables shouldn't require remembering a keyword.

Django's abstraction has real benefits: backend portability of the operation objects, and the ability to embed Python (again: `RunPython`). The cost is a layer between review and reality. You approve an `AlterField` and trust the rendering. Most of the time that trust is fine. The times it isn't are the times you learn to read `sqlmigrate` output very carefully.

## Source of truth and drift: what gets compared against what

**What this piece is:** the reference point. When the tool generates a change, what does it diff your models against? The answer decides when you find out about drift.

**Django** diffs models against the state **reconstructed from the migration chain**. The database is not consulted at generation time. This is what makes `makemigrations` work offline, and it's elegant. But it means the migration history is the effective source of truth for what the schema "is", and the actual database is trusted to match it. If someone alters production by hand, Django's tooling has no moment where it would notice. Models agree with the chain, the chain believes it was applied, and the database quietly disagrees with both until a migration fails or a query breaks.

**DBWarden** diffs models against **actual state**: the live database, or the checksummed schema snapshots it writes to `.dbwarden/schemas/` after every migration, or an exported model-state file. The models are the authority, and reality is the thing being measured. Out-of-band changes surface as unexpected diff entries the very next time anyone runs `make-migrations`. There's also `dbwarden diff` as a dedicated read-only comparison (Rich table, JSON, or raw SQL output) and `dbwarden check-db` for connectivity and schema validation when you're suspicious.

Neither design is careless; they optimize for different failure modes. Django optimizes for a world where all changes flow through migrations, and in a disciplined Django team that's largely true. DBWarden assumes the world where hotfixes happen, because I've lived in that world, and I wanted the tool that notices.

## Rollback: reverse operations vs a contract

**What this piece is:** going backwards, on purpose, under pressure.

**Django's answer:** most schema operations know their own reverse, so `migrate accounts 0003` walks back automatically. Good design. The gaps appear at the edges: `RunPython` needs an explicitly provided reverse function or the migration is irreversible, irreversibility surfaces as an `IrreversibleError` when you *attempt* the rollback, and nothing in code review shows you the rollback path, because it doesn't exist as an artifact. It's computed when needed.

**DBWarden's answer:** rollback is part of the generated file. Every migration carries an executable `-- rollback` section, produced together with the upgrade, reviewed in the same PR. Placeholder rollback is **refused by default**: if executable rollback SQL can't be generated, generation fails unless the migration explicitly declares itself irreversible with a `-- dbwarden: irreversible` marker. Your reviewer sees the escape route, or sees the declared absence of one, before merge. At incident time, `dbwarden rollback` and `dbwarden downgrade` execute exactly the SQL that sat in the repo.

The distinction is *when you learn* a change can't be undone. Django tells you when you try. DBWarden tells you when you generate. I've been on the wrong end of the first timing, and it's why the second one exists.

## Renames: the questioner vs explicit flags

Renames deserve their own section because they're where diff-based tools destroy data.

**Django** detects a likely rename and asks you interactively at generation time. Human answers, correct migration gets written. The limitation is the interactivity itself: in scripts and CI there's no one to answer, and the heuristic needs a plausible before-and-after to even ask.

**DBWarden** makes renames a declaration instead of a dialogue:

```bash
dbwarden make-migrations "rename name" --rename users.name:full_name
dbwarden make-migrations "rename orders" --rename-table order:orders
```

You get `RENAME` DDL, never a drop-and-create, and the intent is recorded in your shell history and your migration description rather than in an answered prompt nobody can audit later. Snapshot comparison helps flag rename candidates too. Same goal as Django's questioner, different medium: explicit flags work in automation and leave a trace.

## Applying and tracking: migrate vs migrate

**What this piece is:** execution and bookkeeping. Running what's pending, knowing what ran.

**Django** records applied migrations in the `django_migrations` table. `python manage.py migrate` applies everything pending across all apps, resolving cross-app dependencies into a valid order. `showmigrations` displays the checklist. Targeting an earlier migration walks backwards. `--fake` marks migrations as applied without running them, which is how you adopt the system on a database that already has the schema. `--plan` previews what would run. It's a complete, polished toolkit, refined over a decade of releases.

**DBWarden** keeps the same vocabulary where it can, because familiarity is a feature. `dbwarden migrate` applies pending migrations in version order and records them in its migration table. `dbwarden status` is your checklist, `dbwarden history` the audit trail. `--baseline` is the `--fake` equivalent for onboarding existing databases, `--dry-run` is the preview, and `--count` or `--to-version` control how far to go. `--all` runs every configured database sequentially, which has no Django equivalent because Django migrates one database's worth of apps at a time.

DBWarden adds one concept Django doesn't have: **migration types**. Besides normal versioned migrations, `runs_always` migrations execute on every migrate run, and `runs_on_change` migrations re-execute whenever their file content changes. Grants, permission refreshes, and idempotent maintenance SQL usually end up in a Django `RunPython` that checks its own state, or in a cron job. Here they're just files with a different prefix, tracked like everything else.

## Coupling: a framework feature vs a standalone tool

**What this piece is:** what you must adopt to use each system.

**Django migrations require Django.** Not just the ORM: the app registry, the settings module, the management commands. That's not a flaw; it's the point. Django is an integrated framework and its migration system is one of the rewards for buying in. But it also means the system is unavailable to everyone outside. There's no practical way to bring `makemigrations` to a FastAPI service on SQLAlchemy.

**DBWarden requires SQLAlchemy**, and nothing else. No framework, no app structure, no settings module. FastAPI, Flask, Litestar, a queue worker, a cron script: if it has SQLAlchemy models, it can have this workflow. There's even an official `dbwarden-fastapi` plugin providing session dependencies and health endpoints for the most common pairing, and the config declares both sync and async database URLs because modern SQLAlchemy stacks are usually async at runtime even when their tooling isn't. This is the gap DBWarden exists to fill. The number of people who left Django for FastAPI and then discovered that "migrations" now meant maintaining revision scripts by hand is large. I was one of them. The workflow I missed wasn't complicated. Change the model, generate, review, apply. It just didn't exist outside the framework.

Standalone also changes the **local development** story. Django assumes you run the same database engine locally that you run in production, or at least it leaves the mismatch to you. DBWarden has dev mode: declare a `dev_database_type` of SQLite in your config and develop locally against your PostgreSQL production schema, with automatic SQL translation between the dialects. No local Postgres container just to hack on a side feature. When the translation can't be faithful, it tells you instead of guessing.

**Multi-database** is also broader than Django's story. Django can route between several relational databases, but its migration system targets Django-supported backends. DBWarden declares multiple databases in one project with full isolation, and treats **ClickHouse** as a first-class backend: MergeTree engine families, codecs, projections, and materialized views declared in `class Meta` (`CHTableMeta`), with the same migration workflow as your PostgreSQL database. MySQL and MariaDB get their own typed metadata too. Your OLTP schema and your analytics schema, one tool.

## A day in the life: the same change in both worlds

Adding that `bio` column, end to end.

**Django:**

1. Add `bio = models.TextField(blank=True, default="")` to the model.
2. Run `python manage.py makemigrations`.
3. Skim the generated `0004_user_bio.py`, maybe run `sqlmigrate` to see the SQL.
4. Commit. Deploy runs `python manage.py migrate`.

**DBWarden:**

1. Add `bio = Column(Text, nullable=True)` to the model.
2. Run `dbwarden make-migrations "add bio"`.
3. Read the `.sql` file: upgrade and rollback, together, exactly as they'll execute.
4. Commit. Deploy runs `dbwarden migrate`, or anything else that can execute SQL.

The flows are nearly identical, and that's the compliment: DBWarden is deliberately the same *shape* as the workflow Django proved out. The differences live in what you reviewed in step 3 (operations vs final SQL, with the rollback visible), and in what step 4 requires (a Django process vs anything).

Now stretch the example one step: two weeks later, product wants `bio` renamed to `about`. In Django, `makemigrations` notices the disappearance and the appearance, asks you "Did you rename user.bio to user.about?", and writes a `RenameField`. In DBWarden, you pass `--rename users.bio:about` and get a `RENAME COLUMN` statement plus its reverse in the rollback section. Same outcome, different interface: a question answered in a terminal versus a flag recorded in the migration's provenance. And in both systems, the naive path (delete the field, add a new one, don't tell the tool) produces a data-destroying drop-and-create, which is why both systems built an answer here at all.

## What DBWarden adds beyond the Django playbook

A few capabilities have no Django-side equivalent, because they come from choices Django didn't need to make.

**Impact analysis.** Before a destructive migration ships, `dbwarden check-impact` scans your codebase with AST analysis and reports what still references the doomed column or table, file and line included. Django's rough analog is grepping and hoping. This exists because DBWarden lives inside your Python project and can read it.

**Sandbox and paranoia flags.** `dbwarden migrate --sandbox` replays migrations in a throwaway database first, using an in-memory SQLite provider in core and a real containerized database once the `dbwarden-sandbox` plugin is installed; `--dry-run` previews; `--with-backup` snapshots before applying.

**Offline state for CI.** Like Django, DBWarden can generate without a live database, via `dbwarden export-models` and `make-migrations --offline` against a committed state file. Unlike Django, the reference state is checksummed and explicitly managed, with `recover-model-state` for repair.

**Reverse engineering.** `dbwarden generate-models` converts an existing live database (PostgreSQL, MySQL, ClickHouse, SQLite) into SQLAlchemy models with `class Meta` metadata filled in. Django's `inspectdb` does something similar for Django models; DBWarden's version round-trips, meaning the generated models regenerate the same schema.

**Safe type changes.** `--safe-type-change` expands a column type change into the add-backfill-swap-drop sequence instead of a naive `ALTER`.

## The state question: implicit chain vs explicit files

One more structural difference, subtle but worth understanding before you choose.

**Django's schema state is implicit.** It exists only as the sum of the migration chain, recomputed in memory every time. There's no file you can point at and say "this is what Django thinks the schema is". That's tidy, but it has a consequence: the migration files become **load-bearing forever**. Delete one and the reconstruction breaks; every file in the chain must remain importable and correct for the lifetime of the project. Squashing exists precisely to manage the weight of that ever-growing chain.

**DBWarden's schema state is explicit.** Checksummed snapshot files in `.dbwarden/schemas/` record the schema after each migration, and the exported model state file (`.dbwarden/model_state.primary.json`, named after the database) carries the reference point for offline generation. Because the truth lives in the models and the state files, **old migration files are safely deletable**. They're receipts, not structure. The flip side is a real operational rule: the model state file must never be deleted carelessly, and the docs are loud about it. If it goes missing, you restore it from git or regenerate with `export-models`, and `dbwarden recover-model-state` exists for repair. Explicit state means state you can also mishandle. I'll take that trade, because explicit state is state you can inspect, diff, and back up, but it's a trade, and you should know you're making it.

## Where Django migrations fit better

Sincerely, as always.

**You're building a Django app.** Then this entire post was theoretical. Django's migrations are integrated with the admin, the test runner, the app ecosystem, and thousands of third-party packages. Using anything else inside Django would be self-harm. Don't.

**`RunPython` data migrations.** Python code interleaved into the migration sequence, with access to historical model states, is something DBWarden does not replicate. DBWarden's `dbwarden new` creates manual migration files, but they're SQL. A lot of backfills express fine in SQL, and SQL backfills are often faster. But "run this Python against the old schema shape" is a Django capability, full stop.

**The interactive questioner.** For a developer at a terminal, being *asked* about a rename is friendlier than knowing the flag. DBWarden chose auditability and automation-friendliness; Django chose conversational UX. Both are defensible, and Django's is more welcoming.

**Squashing.** `squashmigrations` compresses years of history into a compact restatement. DBWarden's model makes old migration files safely deletable (the models and snapshots hold the truth), which addresses the same pain differently, but Django's explicit squash tooling is more established.

**App-scoped migration graphs with dependencies.** Django's per-app chains with cross-app dependency declarations handle a large modular monolith's ordering problems elegantly. DBWarden's per-database versioned sequences are simpler, which is a benefit right up until you need that graph.

## Common questions

**Can I use DBWarden inside a Django project?** Technically nothing stops you from having SQLAlchemy models next to Django, but you shouldn't. Django's migrations are woven into its ORM, its test framework, and its ecosystem. DBWarden is for stacks where SQLAlchemy is the ORM. Using both ORMs in one project is a decision you'd have to justify on other grounds entirely, and I won't help you justify it.

**Is DBWarden "Django migrations for FastAPI"?** As an elevator pitch, honestly, yes. That's the itch. FastAPI's own documentation pairs it with SQLAlchemy, and the migration story has historically been "set up Alembic". DBWarden replaces that with the generated, model-driven flow Django users expect, and the `dbwarden-fastapi` plugin adds session dependencies and health endpoints on top. But the pitch undersells the differences: SQL artifacts instead of Python operation files, the rollback contract, impact analysis, and ClickHouse support have no Django equivalent. It's the same genus, not the same species.

**I'm migrating a Django app to FastAPI. What happens to my schema?** This is a surprisingly common situation and it's well supported. Your database already exists, so let DBWarden read it: `dbwarden generate-models` produces SQLAlchemy models from the live schema, `class Meta` blocks included, with a `--base` flag to use your project's own declarative Base. Then generate a baseline migration and mark it applied with `dbwarden migrate --baseline`. Your `django_migrations` table becomes an archaeological artifact. It hurts nothing; it just stops mattering.

**Does DBWarden understand Django-style app structure?** There's no concept of apps, because SQLAlchemy has no concept of apps. Model discovery is automatic, and `model_paths` in your `database_config` pins down which modules to scan when you want explicit control. In a project with several databases, `model_tables` assigns tables to databases, which covers the main thing Django's app-scoping actually buys at migration time.

**What about testing migrations?** Django's test runner builds the test database from your migrations automatically, which is a quiet, excellent feature. DBWarden's equivalents are explicit: `dbwarden migrate --sandbox` replays migrations in a temporary database, and the `dbwarden-sandbox` plugin provides Testcontainers-based sandbox providers so your test suite can spin up a real PostgreSQL or ClickHouse, apply the migration chain, and verify it converges. Different ergonomics, same assurance.

**Seeds and fixtures?** Django has fixtures and data migrations. DBWarden splits the concern into a dedicated plugin, `dbwarden-seeds`, with code-based and file-based SQL or Python seeds, tracked in their own table, applied with `dbwarden seed apply` or automatically after migrations if you configure `auto_apply_seeds`. Seed data and schema migrations are related but different problems, and keeping them separate keeps both simple.

## So which one?

If you're in Django: **Django migrations**. That's the whole answer, and any tool author who tells you otherwise is selling something.

If you're on SQLAlchemy: you never actually had the Django option. Your real choices are Alembic's revision scripts, Atlas's schema-as-code, or DBWarden. And if what you miss is specifically the Django feeling, models as the single source of truth, migrations as something *generated* rather than authored, a typed `class Meta` for the database details, then DBWarden is the closest thing to `makemigrations` your stack can get, with two upgrades earned along the way: artifacts you can read as plain SQL, and rollbacks enforced as a contract instead of computed on demand.

Django taught us that developers shouldn't hand-write schema changes. It proved the model-driven workflow at a scale nobody can argue with, inside one framework. DBWarden's whole premise is that the lesson was bigger than the framework, and that SQLAlchemy users, which today means most of the Python web world outside Django, deserve it too. If you've spent years typing `makemigrations` and recently found yourself hand-editing a revision script at midnight, wondering how the ecosystem went backwards: it didn't. The workflow just hadn't been ported yet.

---

This closes the series. The other posts: [DBWarden vs Alembic](/works/dbwarden-vs-alembic/) on the imperative-vs-declarative divide, and [DBWarden vs Atlas](/works/dbwarden-vs-atlas/) on two declarative tools with very different shapes. If you're ready to try it, start with the [docs](https://dbwarden.emiliano-go.com/), and if you're coming from Alembic, there's a [step-by-step migration guide](https://dbwarden.emiliano-go.com/getting-started/migrating-from-alembic).
