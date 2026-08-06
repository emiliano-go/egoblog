---
title: "DBWarden vs Alembic: A Declarative Alembic Alternative for SQLAlchemy"
date: 2026-08-05
description: "Looking for an Alembic alternative? DBWarden is a declarative migration tool for SQLAlchemy. Your models are the source of truth, and the output is plain SQL. A detailed, honest comparison from DBWarden's creator."
summary: "I built DBWarden, so I'm biased. This is my honest comparison with Alembic anyway: every piece of the migration workflow, explained side by side, plus a clear list of cases where Alembic is still the right call."
keywords: ["alembic alternative", "sqlalchemy migrations", "declarative database migrations", "dbwarden vs alembic", "sqlalchemy migration tool", "database schema management python", "alembic autogenerate"]
---

First, the disclaimer: I built [DBWarden](https://github.com/dbwarden-org/dbwarden). I am **biased**. But I used Alembic for a long time before writing a single line of DBWarden, and I respect it. It's maintained by the same person behind SQLAlchemy itself, and it earned its place as the default. If this post reads like bashing, I failed. The goal is to show you a real **difference in philosophy**, so you can pick the right tool for your project.

One more thing before we start. You probably know Alembic and have never heard of DBWarden. So this post won't just compare. For every piece of the migration workflow, I'll explain what the piece **is**, how Alembic handles it, and then how DBWarden handles it. By the end you'll understand both tools well enough to choose. That's the whole point.

## The two camps: imperative vs declarative

Every schema management tool answers one question: how do I get my database from the shape it has to the shape I want? There are exactly two philosophies for answering it.

**Imperative** tools have you author *changes*. You write a script that says "add this column, rename that table, create this index". Each script moves the schema from version N to version N+1. The scripts chain together. That chain, the full history of every change ever made, becomes the source of truth for what your database should look like. To know the current schema, you replay the history in your head (or trust the ORM models and hope nobody diverged).

**Declarative** tools have you author the *desired state*. You describe what the schema **should be**, and the tool figures out the changes needed to get there. The description is the source of truth. History is a byproduct.

If you've used Terraform, you know this split already. Nobody writes "create an EC2 instance" scripts chained by hand anymore. You declare the infrastructure you want, and the tool plans the diff. Databases are one of the last places where the imperative approach is still the default. I think that's mostly inertia.

Alembic is imperative. Every change becomes a revision script: a Python file with an `upgrade()` and a `downgrade()` function, linked to its parent by a revision id.

DBWarden is declarative. Your SQLAlchemy models **are** the schema definition. There is no second representation. You change a model, and DBWarden generates the SQL to reconcile the database with it. Rollback included.

That's the core. Now let's walk through the actual workflow, piece by piece.

## Setup: env.py vs dbwarden.py

**What this piece is:** every migration tool needs to know two things. Where your database lives, and where your models live.

**Alembic's answer** is `alembic init`, which scaffolds a directory: an `alembic.ini` file for configuration, an `env.py` script that wires your engine and metadata into the migration context, plus a `versions/` folder and a script template. The `env.py` file is real Python that runs on every command. It's flexible, and that flexibility is genuinely useful when you have exotic setups. But most projects copy an `env.py` from a previous project, tweak the `target_metadata` line, and never look at it again. It's boilerplate you own and occasionally have to debug.

**DBWarden's answer** is a single `dbwarden.py` file in your project root. It's not a script that runs migrations. It's a declaration of your databases:

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

That's the entire configuration. Model discovery is automatic (you can pin it down with `model_paths` if you want control). Then `dbwarden init` sets up the migrations directory and internal state. No template, no `env.py`, no ini file. One config object per database. If you have five databases, you declare five of these, and every command takes a `--database` flag.

## The migration itself: revision scripts vs models

**What this piece is:** the artifact. The thing that gets written, reviewed, committed, and executed when your schema changes.

**Alembic's artifact** is the revision script. A Python file that looks like this:

```python
revision = "ae1027a6acf"
down_revision = "1975ea83b712"

def upgrade():
    op.add_column("users", sa.Column("bio", sa.Text(), nullable=True))

def downgrade():
    op.drop_column("users", "bio")
```

You author this file, or generate it and then edit it. It gets committed. From that moment it is **part of the chain**. The `down_revision` pointer links it to its parent, and Alembic replays the chain in order to build your schema. The revision history is the schema definition. Your models describe the same schema a second time, and keeping the two in agreement is your job.

This is the part I want you to sit with, because it's the entire disagreement between the two tools. You maintain **two representations** of your schema: the models your application uses, and the migration chain your database uses. Every schema change must be made in both. When they drift apart, nothing tells you until something breaks.

**DBWarden's artifact** is different in two ways. First, it's not authored, it's **derived**. Second, it's not Python, it's **SQL**.

Your models are normal SQLAlchemy models. DBWarden adds an optional, fully typed `class Meta` for database-level metadata that SQLAlchemy models can't naturally express:

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

The `class Meta` convention is lifted straight from Django, deliberately. It isn't a SQLAlchemy idiom, but Django proved that the stuff about a table which isn't a column deserves a structured home on the model, and there was no reason to invent a worse name for it.

A detail I care about: `class Meta` is validated at **import time** by a metaclass. If you write `commet = "..."` or `my_engin = "InnoDB"`, you don't get silently wrong DDL three weeks later. You get a `DBWardenConfigError` the moment the module loads, naming the unknown attribute. Typos fail loudly and early.

Then you run:

```bash
dbwarden make-migrations "create users"
```

And the output is a plain `.sql` file with both directions in it:

```sql
-- upgrade
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    bio TEXT
);
COMMENT ON TABLE users IS 'Core user accounts';
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_bio ON users (bio);

-- rollback
DROP TABLE users;
```

You review it, commit it, and apply it with `dbwarden migrate`. Any tool can execute it. Your DBA can read it without knowing Python. There is no migration runtime on the target machine, because there is nothing to run except SQL.

Notice the small things. `CONCURRENTLY` on PostgreSQL index creation is the **default**, because locking a production table to build an index is a mistake you only make once. `IF NOT EXISTS` guards are emitted where they're safe. These defaults exist because I got paged for their absence.

And here's the key structural difference: with DBWarden, migration files are **artifacts, not authority**. The models remain the source of truth forever. The `.sql` files are a record of how the database got here, useful for review and for sequential deploys, but the schema definition never leaves your models.

## Generation: autogenerate vs make-migrations

**What this piece is:** the generator. The thing that looks at your models, looks at your database, and writes the change for you.

**Alembic's generator** is `alembic revision --autogenerate`. It compares your model metadata against the live database and emits a candidate revision script. It's genuinely useful, and if you use Alembic without it you're doing unnecessary manual labor. This is also the point where people say "so Alembic is declarative too". Not quite, and the difference matters. Three reasons.

One: the generated revision is still a **Python script you own**. You review it, you edit it, you commit it, and from that moment it's part of the chain. The generator ran once; the artifact lives forever.

Two: the chain remains the **source of truth**. Your models are just an input to the generator. If the chain and the models disagree, the chain wins, and you find out at deploy time.

Three: autogenerate has [documented limits](https://alembic.sqlalchemy.org/en/latest/autogenerate.html#what-does-autogenerate-detect-and-what-does-it-not-detect). The docs are honest about them, which I appreciate. The big one: renames. Autogenerate can't tell a rename from a drop-and-create. Rename a column and the generated script **drops your data** unless you catch it in review. Some constraint changes go undetected entirely. The tool expects you to review and fix by hand, every time.

**DBWarden's generator** is the tool. There is no non-generated path for schema changes, so the generation had to be trustworthy enough to carry the whole workflow. A few things make that possible.

**Snapshots.** After every migration, DBWarden writes a checksummed JSON snapshot of the full schema to `.dbwarden/schemas/`. Diffs run against snapshots, deterministically. The same models and the same state produce the same SQL, every time, on every machine.

**Explicit renames.** Since a diff can't prove a rename, DBWarden doesn't guess. You declare it:

```bash
dbwarden make-migrations "rename name to full_name" --rename users.name:full_name
```

And you get `ALTER TABLE users RENAME COLUMN name TO full_name`, not a drop and a create. Table renames work the same way with `--rename-table`. Snapshot comparison also helps detect rename candidates. The point is that data-destroying ambiguity is never resolved silently.

**Safe type changes.** `--safe-type-change` generates the boring-but-correct multi-step version of a column type change: add temp column, backfill, swap, drop old. You've written this dance by hand. Now it's a flag.

**Column-level precision.** Type, nullability, default, and comment changes generate targeted `ALTER COLUMN` statements. And before anything is written, `--plan` shows you the migration plan as JSON, and `--sql` prints the raw SQL to stdout. You always get to look before anything exists.

## Going back: downgrade() vs the rollback contract

**What this piece is:** the escape hatch. The thing you run when a migration goes wrong at 2 AM.

**Alembic's answer** is the `downgrade()` function in each revision. The design is right: every change should know how to undo itself. The enforcement is where it gets weak. `downgrade()` is your responsibility. Nothing checks that it exists, works, or stays correct after you edit the script. And we've all seen this in real repos:

```python
def downgrade():
    pass
```

An empty downgrade doesn't fail review, doesn't fail CI, and doesn't fail at deploy. It fails at 2 AM, when you run it and **nothing happens**. The rollback path is the least-tested code in most codebases, and it's the code you run under the most pressure.

**DBWarden's answer** is a contract. Every generated migration carries an executable `-- rollback` section, generated together with the upgrade. Placeholder rollback is **refused by default**: if DBWarden cannot emit executable rollback SQL, generation fails. If a change is genuinely irreversible (some ClickHouse engine changes, PostgreSQL enum value additions), you must say so explicitly, in the migration file:

```sql
-- dbwarden: irreversible
```

That line is visible in code review. Your reviewer sees "this migration cannot be undone" as a declared fact, not as an empty function nobody read. Rollback moves from convention to **contract**.

Operationally you get `dbwarden rollback` and `dbwarden downgrade` to walk back, with `--to-version` targeting, and `dbwarden make-rollback` for generating rollbacks. The rollback SQL sits in the same reviewed, committed file as the upgrade. What you tested is what you run.

## Applying migrations: upgrade head vs migrate

**What this piece is:** the execution step. Taking the pending changes and actually running them against a database, while keeping track of what has already run.

**Alembic's answer** is `alembic upgrade head`. It reads the `alembic_version` table in your database, finds where you are in the revision chain, and executes every `upgrade()` function between there and the newest revision. You can target a specific revision instead of `head`, step relatively with `+1`, and `alembic stamp` marks a revision as applied without running it, which is how you onboard a database that already has the schema.

This works well. My friction was never with the mechanics. It was with the runtime: applying migrations means running Python, which means the target environment needs your virtualenv, your dependencies, and your `env.py` to behave. The migration is not a thing, it's a *program*.

**DBWarden's answer** is `dbwarden migrate`. Same job, different texture. It reads its migration table, finds pending `.sql` files, and applies them in order. The controls are all flags:

```bash
dbwarden migrate                          # apply everything pending
dbwarden migrate --count 2                # apply the next two
dbwarden migrate --to-version 0007        # stop at a specific version
dbwarden migrate --baseline --to-version 0005   # mark as applied without executing
dbwarden migrate --all                    # every configured database, sequentially
```

`--baseline` is the `stamp` equivalent, and it's how you onboard an existing database. `dbwarden history` shows what ran and when. `dbwarden status` shows what's pending. And because the artifacts are plain SQL, you always have the exit: take the `.sql` file and hand it to psql, to your DBA, or to whatever deployment machinery your company already trusts. The tool is convenient, not required. I consider that a feature. Lock-in through file formats is a tax, and SQL is the one format every database tool on earth can read.

One more apply-time detail. DBWarden also supports two special migration types besides versioned ones: `runs_always` migrations that execute on every migrate run, and `runs_on_change` migrations that re-execute when their content changes. Grants, refresh routines, and idempotent maintenance SQL finally get a home that isn't a cron job.

## Drift: the silent killer

**What this piece is:** drift is when the database's actual schema no longer matches what your tooling believes. A hotfix applied by hand on a Friday. A migration that half-ran. A colleague's "temporary" index from eight months ago.

**With Alembic**, the version table (`alembic_version`) records which revision the database is at. But it records which scripts *ran*, not what the schema *is*. If someone alters the database out-of-band, the version table still says everything is fine. Models say one thing, chain says another, database says a third. You typically discover the disagreement when the next migration fails in production, which is the worst possible moment.

**With DBWarden**, drift detection is structural, not optional. Every `make-migrations` run diffs the models against actual state, so out-of-band changes surface as unexpected diff entries at **generation time**, on your machine, not at deploy time in production. `dbwarden status` shows pending migrations, `dbwarden check` validates the setup, and `dbwarden diff` is a read-only comparison tool that outputs a Rich table, JSON, or raw SQL, so you can inspect exactly how reality differs from your models any time you get suspicious.

## A day in the life: the same change in both tools

Abstract philosophy is nice. Here's the same task, adding a `bio` column to `users`, done twice.

**With Alembic:**

1. Edit the model: add `bio = Column(Text, nullable=True)`.
2. Run `alembic revision --autogenerate -m "add bio"`.
3. Open the generated revision. Verify the `upgrade()` is right. Verify autogenerate didn't misread anything else in your metadata as a change.
4. Write or verify the `downgrade()`.
5. Commit the model change and the revision script. Two files, both authoritative.
6. Deploy runs `alembic upgrade head` with your Python environment on the target.

**With DBWarden:**

1. Edit the model: add `bio = Column(Text, nullable=True)`.
2. Run `dbwarden make-migrations "add bio"`.
3. Open the generated `.sql` file. Read the `ALTER TABLE users ADD COLUMN bio TEXT` and the rollback below it.
4. Commit the model change and the SQL artifact. One file is authoritative, the other is a receipt.
5. Deploy runs `dbwarden migrate`, or your DBA runs the file, or your pipeline pipes it to psql.

Both flows are short. The difference is in what each step *asks of you*. Alembic's step 3 and 4 are verification and authorship duties that never go away, on every change, forever. DBWarden's step 3 is reading SQL. On a five-person team shipping schema changes weekly, that delta compounds into real time and, more importantly, into real mistakes that never happen.

## Offline mode: CI without a database

**What this piece is:** generating or planning migrations without a live database connection. This matters more than it sounds. If your migration tool needs a database to think, then every CI job needs a database service, seeded to the right state, just to answer "what would change?".

**Alembic** has an offline mode: `alembic upgrade head --sql` renders the SQL of pending revisions to stdout instead of executing them. It's good for generating scripts a DBA will run. But *generating a new revision* with autogenerate still requires a live database to compare against, so CI pipelines that validate schema changes still need that Postgres service container.

**DBWarden** decouples generation from the database entirely. You export the model state once:

```bash
dbwarden export-models --database primary
git add .dbwarden/model_state.primary.json
```

Then, on any machine, with no database connection at all:

```bash
dbwarden make-migrations "add bio column" --offline
```

The state file is the reference point, and it updates in place after each migration. Your CI pipeline can generate and validate migrations with **zero database services**. Faster pipelines, no seeding scripts, no service containers. This is the feature the declarative model makes almost free, and it's one of my favorites.

## Beyond parity: what the declarative choice unlocks

Everything above maps DBWarden onto workflow pieces Alembic also has. This section covers the pieces that don't map, because they only make sense when the tool fully understands your target schema.

**Impact analysis.** Before a destructive change ships, `dbwarden check-impact` scans your codebase with AST analysis (grep fallback for templates) and tells you what still references the thing you're about to destroy:

```
drop_column on users.username
  References: 2
    app/routes/users.py:34  attribute_access
    app/templates/profile.jinja2:12  grep
```

You know what breaks **before** it breaks. Dropping a column stops being an act of faith.

**Sandbox validation.** `dbwarden migrate --sandbox` replays your migrations in a throwaway database before they touch a real one. Be precise about what you get out of the box, though: core ships an in-memory SQLite provider, so on a PostgreSQL project the replay runs through SQL translation. That's a smoke test, not a rehearsal. Installing the `dbwarden-sandbox` plugin registers a Testcontainers-backed provider instead, and then the replay happens against a real disposable PostgreSQL or ClickHouse, which is the version actually worth trusting. There's also `--dry-run` to preview what would be applied, and `--with-backup` to snapshot before applying. I am the paranoid engineer these flags were built for.

**Multi-database, including analytics.** One project can declare PostgreSQL, MySQL, ClickHouse, MariaDB, and SQLite databases, fully isolated, each with backend-specific `Meta` extensions: `PGTableMeta` for partitioning and RLS, `MyTableMeta` for engines and charsets, `CHTableMeta` for MergeTree engines and codecs. If you've ever managed a ClickHouse schema with shell scripts because your migration tool didn't speak ClickHouse, this one's for you.

**Dev mode.** Declare a `dev_database_type` and run SQLite locally against a PostgreSQL production schema, with automatic SQL translation. Local dev without a local Postgres.

**Reverse engineering.** `dbwarden generate-models` turns a live database into SQLAlchemy models, `class Meta` blocks included, with round-trip support. This is also the adoption path for legacy schemas: point it at the database you inherited and get models that regenerate it.

**Plugins.** The core stays focused, and a plugin system extends it: seed data management (`dbwarden-seeds`), FastAPI integration (`dbwarden-fastapi`), Testcontainers sandboxes (`dbwarden-sandbox`), PostgreSQL RBAC, custom types and extensions, ClickHouse RBAC.

## Where Alembic fits better

This section matters more than the last one. I mean every word of it.

**Python data migrations.** Alembic revisions are Python, and that's a real superpower. You can backfill data with your own code, import your models, call your services, loop with real logic. DBWarden supports manual migration files via `dbwarden new`, but those are SQL. Plenty of backfills are expressible in SQL, and honestly SQL is often the better tool for them, but if your workflow leans on Python-level transformations inside migrations, Alembic serves you better. Full stop.

**Branching and merging.** Alembic's revision graph handles parallel branches and merge points. Two developers create revisions on separate branches, and `alembic merge` reconciles them. It's a genuinely elegant design for large teams with many concurrent schema changes. DBWarden's linear versioned flow doesn't replicate it.

**Ecosystem familiarity.** Most Python tutorials, framework templates, and answers on the internet assume Alembic. Every SQLAlchemy developer you hire already knows it. That network effect has real onboarding value, and pretending otherwise would be dishonest.

**Compatibility.** DBWarden requires Python 3.12+ and SQLAlchemy 2.0+. Alembic supports much older environments. If you're pinned to Python 3.9, this decision has been made for you.

**Manual control.** If you *want* to hand-craft every migration step, an imperative tool is the honest choice. DBWarden derives SQL from your models; that's the deal you're making.

## Common questions

**Is DBWarden a wrapper around Alembic?** No. Zero shared code, zero shared runtime. It's a from-scratch implementation of a different philosophy: diff engine, snapshot store, SQL generators per backend, safety classifier. The only thing the two tools share is SQLAlchemy models as an input.

**Can I keep using my existing models?** Yes, unchanged. DBWarden reads normal SQLAlchemy models. The `class Meta` blocks are optional, additive metadata. You add them when you want comments, indexes, or backend-specific features that models can't express, not before.

**How do I move an existing Alembic project to DBWarden?** Your database already has the schema, so you generate a baseline and mark it as applied. Point DBWarden at your models, run `dbwarden make-migrations` to produce the baseline migration, then `dbwarden migrate --baseline` so it's recorded without executing. From there, new model changes generate new migrations. The full walkthrough lives in the [migrating from Alembic guide](https://dbwarden.emiliano-go.com/getting-started/migrating-from-alembic). Your Alembic history stays in git; it just stops growing.

**Can the two coexist during a transition?** They don't fight. Alembic tracks its state in `alembic_version`, DBWarden in its own migration table. Run both while you gain confidence, generate the same change in each, and compare the SQL. When DBWarden's output has earned your trust, retire the Alembic side. I'd keep the transition short, though. Two sources of truth is the exact disease we're treating.

**What about databases Alembic doesn't focus on?** This is a real differentiator. DBWarden treats ClickHouse as a first-class backend, MergeTree engines and codecs included, next to PostgreSQL and MySQL. If your stack has an analytics database managed by hand-rolled scripts, one tool can now own both schemas.

**What does adopting DBWarden actually cost?** Honestly: Python 3.12+ and SQLAlchemy 2.0+ as hard requirements, a new mental model for renames (explicit flags instead of editing generated scripts), and giving up Python-level logic inside migrations unless you write manual SQL files with `dbwarden new`. If any of those are dealbreakers, stay on Alembic. It will keep working fine.

## So which one?

Pick **Alembic** if you need Python data migrations inside revisions, depend on revision branching and merging, run older Python, or want manual control over every migration step.

Pick **DBWarden** if you want your models to be the single source of truth, want reviewable plain SQL artifacts, want rollbacks enforced by contract instead of convention, want to know a migration's blast radius before deploying, or want migration generation in CI without a live database.

And if you're torn, here's a practical tiebreaker. Look at your last ten migrations. If most of them are pure schema changes (columns, indexes, constraints, tables), you're doing declarative work with imperative tooling, and DBWarden will remove a whole category of manual labor from your week. If half of them contain data backfills in Python, loops over rows, or calls into your application code, you're doing genuinely imperative work, and Alembic is built for exactly that.

Both tools solve the same problem. They just ask you to maintain a different thing. Alembic asks you to maintain a **history of changes**. DBWarden asks you to maintain a **description of the destination**. I spent years maintaining histories. I'd rather maintain destinations. But that's my bias, and now you know exactly where it comes from.

---

If you want to try the declarative side, the docs include a [guide for migrating from Alembic to DBWarden](https://dbwarden.emiliano-go.com/getting-started/migrating-from-alembic). Your models stay exactly where they are. That's the point.

This is the first post in a series comparing DBWarden with other schema tools. Next up: [DBWarden vs Atlas](/works/dbwarden-vs-atlas/) and [DBWarden vs Django migrations](/works/dbwarden-vs-django-migrations/).
