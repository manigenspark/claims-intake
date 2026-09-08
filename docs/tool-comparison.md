# Tool comparison (Day 4)

## Task I performed in Cursor

**Task.** Used Cursor CLI (`agent`) to rewrite only the
`### Why --platform linux/amd64` section in `README.md` for a new joiner,
with an explicit instruction not to edit any other file.

## What Cursor CLI (`agent`) made easy

- One terminal command started a scoped edit; it grepped the README, found the
  section, and changed only that block (+9/−6).
- The prompt constraint (“do not edit other files”) held — the diff was README
  only, which was easy to review with `git diff`.
- It led with a short rule (“always pass this flag”) then explained ARM local
  vs amd64 deploy in plain language, which matches the Day 4 README rubric.

## What Cursor CLI made awkward

- The interactive UI truncates the diff (`… truncated · ctrl+r to review`), so
  confirming the full wording meant leaving the agent and running `git diff`.
- It is easy to over-trust a “done” summary without reading the new paragraph
  carefully; I still had to judge whether the explanation was accurate.
- Auth / starting the CLI is a separate step from the IDE chat I was already in.

## What the autonomous agent (this IDE chat) made easy / awkward

**Easy.** Multi-file Day 4 shipping: `routes.py`, integration tests, Dockerfile,
V-6 detail on duplicates, and the first README draft — kept the contract §6
mapping and the full test suite green across many files in one thread.

**Awkward.** Large diffs are harder to learn “inch by inch”; I had to ask for
explanations after the fact. For a one-paragraph docs tweak, that agent is
heavier than necessary.

## Preference

For **a single-file docs or wording change with a tight scope** I would reach
for **Cursor CLI (`agent`)** because the prompt stays small, the diff stays
reviewable, and it is natural to run from the project directory.

For **cross-cutting implementation (HTTP + tests + Docker + contract mapping)**
I would reach for **the long-running IDE/autonomous agent** because it can hold
multi-file context and keep ruff/mypy/pytest green while wiring several
surfaces at once.
