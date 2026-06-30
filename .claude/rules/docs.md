---
paths:
  - "docs/**/*.md"
---

# Documentation Rules

## Structure
- `docs/Improvement/` — production issues, bugs, and improvement tasks (numbered files: 1_, 2_, etc.)
- `docs/CLAUDE_OPTIMIZATION.md` — Claude Code config and token optimization decisions

## When Editing Docs
- Use tables for comparisons and issue tracking — easier to scan than prose
- Use checkboxes `- [ ]` for actionable items so progress can be tracked
- Keep headings consistent: Critical / High / Medium / Low for issue severity
- Add a "Last Updated" line at the top of improvement docs when making changes

## When Fixing a Tracked Issue
- Mark the relevant checkbox done in `docs/Improvement/1_app_improvement.md`
- Add a short note next to it: `- [x] Fixed: <what was changed and in which file>`

## Adding New Improvement Docs
- New doc files follow the naming pattern: `<number>_<topic>_improvement.md`
- Example: `2_auth_improvement.md`, `3_database_improvement.md`
- Always include: Overview, Critical / High / Medium sections, and a Prioritized Fix Roadmap

## Diagram Support
- Use Mermaid syntax inside code fences for architecture and flow diagrams
- GitHub and most doc renderers display these natively — no external tool needed
- Example for a request flow:
  ```mermaid
  graph LR
    Client --> APIGateway
    APIGateway --> Lambda
    Lambda --> RDS
  ```
