# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

This repository is currently a skeleton. It contains only:

- `README.md` — a single-line title (`# crypto`)
- `CLAUDE.md` — this file

There is no source code, build tooling, dependency manifest, test suite, or CI configuration yet. There are also no Cursor rules (`.cursor/rules/`, `.cursorrules`) or Copilot instructions (`.github/copilot-instructions.md`).

Because nothing about the language, framework, or architecture has been established, do not assume any particular stack. When adding the first real code, pick and document the toolchain here (build, lint, test, and single-test commands) so future sessions can rely on it. Keep this file updated as the codebase grows — replace this "Current state" section with the actual architecture once it exists.

## Git workflow

- Default branch: `main`.
- Active development branch for Claude sessions: `claude/claude-md-docs-xtu1qe`. Develop, commit, and push here; create it locally from `main` if it doesn't exist. Do not push to other branches without explicit permission.
- Push with `git push -u origin <branch-name>`.
- Do not open a pull request unless explicitly asked.
