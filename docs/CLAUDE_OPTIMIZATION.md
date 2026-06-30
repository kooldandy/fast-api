# Claude Code Token Optimization — Implementation Summary

This document describes all Claude Code optimization files added to this project, what each one does, and why it was added.

---

## Files Added

```
fast-api/
├── CLAUDE.md                        # Project-wide instructions (auto-loaded)
├── CLAUDE.local.md                  # Personal local overrides (gitignored)
├── .claudeignore                    # Files Claude should never read
├── .gitignore                       # Updated to gitignore CLAUDE.local.md
└── .claude/
    ├── settings.json                # Permissions, model, env config
    └── rules/
        ├── routing.md               # Rules for app/routing/**
        ├── database.md              # Rules for app/database/** + alembic/**
        ├── models.md                # Rules for app/models/**
        └── auth.md                  # Rules for app/auth/**
```

---

## 1. `CLAUDE.md` — Project Instructions

**Loads:** Every session, automatically  
**Token cost:** Fixed startup cost (~60 lines)

Contains:
- Stack overview (FastAPI, SQLAlchemy 2.0, Auth0, Lambda)
- Project layout map
- Dev commands (run, migrate, install)
- Code conventions (auth, ORM style, Pydantic v2)
- Pointer to known production issues in `docs/Improvement/`

**Why kept short:** Files over 200 lines reduce Claude's adherence and waste context. All detailed per-area rules are moved to scoped rule files (see below).

---

## 2. `CLAUDE.local.md` — Personal Local Overrides

**Loads:** Every session, alongside CLAUDE.md  
**Token cost:** Same as CLAUDE.md  
**Committed:** No — added to `.gitignore`

Contains your local DB URL, local server address, and personal dev preferences. Each developer on the team keeps their own version. Never committed to the repo.

---

## 3. `.claudeignore` — File Exclusion

**Loads:** Applied as a filter before any file read  
**Token cost:** Zero — prevents reads rather than adding context

Excludes:
| Pattern | Reason |
|---|---|
| `**/__pycache__/` | Compiled bytecode — never useful to read |
| `**/*.pyc` | Same as above |
| `alembic/versions/` | Generated migration files — noisy, rarely need editing |
| `dist/`, `build/` | Build output |
| `.env`, `.env.*` | Secrets — must never be read into context |
| `venv/`, `.venv/` | Vendored dependencies |

---

## 4. `.claude/settings.json` — Project Config

**Loads:** As config, not context  
**Token cost:** Zero — it's settings, not instructions

```json
{
  "model": "claude-sonnet-4-6",
  "permissions": { "deny": [...] },
  "env": { "APP_ENV": "development" }
}
```

- **`permissions.deny`** — Hard blocks on reading secrets, cache, and build artifacts. More reliable than `.claudeignore` for security-sensitive paths.
- **`model`** — Pins the project to `claude-sonnet-4-6` so all team members use the same model.
- **`env`** — Sets `APP_ENV=development` so Claude knows the local context without reading `.env`.

---

## 5. `.claude/rules/` — Path-Scoped Rules (The Main Token Saver)

**Loads:** On demand — only when Claude reads a file matching the path pattern  
**Token cost:** Zero until triggered

Instead of putting all coding conventions in `CLAUDE.md` (which loads every session even when you're just asking a question), these rules only activate when Claude is actually working in that area of the code.

| Rule File | Activates When | Contains |
|---|---|---|
| `routing.md` | Editing `app/routing/**` | Auth requirement, status codes, pagination, REST conventions |
| `database.md` | Editing `app/database/**` or `alembic/**` | SQLAlchemy 2.0 style, session lifecycle, migration rules, Decimal vs float |
| `models.md` | Editing `app/models/**` | Pydantic v2 syntax, field validation, schema separation pattern |
| `auth.md` | Editing `app/auth/**` | RS256 requirement, JWKS singleton, 401 vs 403, JWT logging rules |

**Example:** If you ask Claude to "add a new field to the product model", only `models.md` and `database.md` load — not `routing.md` or `auth.md`. This keeps the effective context small and relevant.

---

## How These Work Together

```
Every session:
  CLAUDE.md (project context) + CLAUDE.local.md (personal context)
  ↓
  .claude/settings.json (model + hard deny rules applied)
  ↓
  .claudeignore (file read filter)

On demand (when Claude opens matching files):
  .claude/rules/routing.md    — routing conventions
  .claude/rules/database.md   — DB + migration conventions
  .claude/rules/models.md     — Pydantic schema conventions
  .claude/rules/auth.md       — Auth0 JWT conventions
```

---

## Token Budget Impact

| Before | After |
|---|---|
| All conventions in CLAUDE.md, loaded every session | Core conventions in CLAUDE.md, detailed rules load on demand |
| Claude reads `__pycache__`, `.pyc`, `.env` when exploring | Hard-blocked via `.claudeignore` + `permissions.deny` |
| No model pinning — varies per user | Pinned to `claude-sonnet-4-6` in `settings.json` |
| Local DB URL typed in chat each session | Stored in `CLAUDE.local.md`, loaded automatically |

---

## What Was NOT Added (and Why)

| Feature | Decision |
|---|---|
| `.claude/agents/` | No subagent workflows defined yet — add when needed |
| `.claude/skills/` | No reusable task workflows yet — add as team grows |
| `~/.claude/CLAUDE.md` | User-level rules — personal choice, not project-level |
| Nested `app/CLAUDE.md` | Rules are path-scoped via `.claude/rules/` — simpler |
| Hooks | No automation tasks identified yet — add when CI/CD hooks needed |

---

## Maintenance Notes

- Keep `CLAUDE.md` under **200 lines** — split into rules if it grows
- Add new resource rules to `.claude/rules/<resource>.md` when adding new modules (e.g., `orders`, `users`)
- Update `permissions.deny` in `settings.json` when adding new generated/cached directories
- `CLAUDE.local.md` is personal — each developer maintains their own version locally
