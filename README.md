# SIES — Smart Islamic Education System

Multi-branch management system for an Islamic educational institution.
Django + DRF backend, React + Vite admin dashboard, Celery, Traefik.

**No code yet — this repository currently holds the design.**

Read the docs in order:

1. [`docs/00-overview.md`](docs/00-overview.md) — scope, the three academic streams, what this system is *not*
2. [`docs/01-architecture.md`](docs/01-architecture.md) — services, request path, multi-branch strategy, Celery, deployment
3. [`docs/02-system-design.md`](docs/02-system-design.md) — actors, RBAC, module workflows, API conventions, admin UI
4. [`docs/03-database.md`](docs/03-database.md) — every table, field by field
5. [`docs/04-roadmap.md`](docs/04-roadmap.md) — testing and risks
6. **[`docs/05-scope-and-v1.md`](docs/05-scope-and-v1.md) — the scope authority: what gets built first, and what waits**
7. [`docs/06-diagrams.md`](docs/06-diagrams.md) — the whole system in 15 diagrams (start here for the visual tour)
8. [`docs/07-admission-form.md`](docs/07-admission-form.md) — the printable ভর্তি ফরম: templates, questions, placeholders
9. **[`docs/08-decisions.md`](docs/08-decisions.md) — decisions taken; overrides everything above**

Agents building this: read [`CLAUDE.md`](CLAUDE.md) first.

`01`–`03` describe the full design. **`05` decides what V1 is**, and wins wherever
the documents disagree — start there.

Reference implementation borrowed from: `~/awliaa`.
