---
name: wrap-up
description: Session wrap-up workflow. Updates PROGRESS.md with session achievements, git working tree changes, decisions, and risks under 1.5 pages.
---

# Session Wrap-Up Workflow (`/wrap-up`)

This workflow summarizes session progress, updates project memory, and suggests git commit messages without performing unapproved commits or actions.

## Workflow Instructions

When the user invokes `/wrap-up`:

1. **Read Governance & Current Progress**:
   - Read [`AGENTS.md`](file:///Users/anand/Developer/AI/experiment/anti-gravity/stock-researcher-agent/AGENTS.md) to preserve non-negotiable architectural boundaries.
   - Read the existing [`PROGRESS.md`](file:///Users/anand/Developer/AI/experiment/anti-gravity/stock-researcher-agent/PROGRESS.md).

2. **Inspect the Git Working Tree & Test State**:
   - Run `git status` to identify modified, added, deleted, and untracked files.
   - Run `git diff --stat` to measure the volume of code changes.
   - Run the full test suite to verify stability: `.venv-market/bin/python -m unittest discover tests`.
   - Run `git diff --check` to ensure no whitespace or formatting errors exist.

3. **Update `PROGRESS.md`**:
   - Keep the updated document strictly **under 1.5 pages** (approximately 75–85 lines).
   - **Section 3 (Status):** Move verified items to `Done`. List partially implemented work under `Built but Untested`.
   - **Section 4 (Decisions):** Record new design or architectural choices with the date, decision, and rationale.
   - **Section 5 (Risks):** Update active security, configuration, or operational risks.
   - **Section 6 (Next Steps):** Maintain priority order unless a blocker or explicit user direction justifies reordering.
   - **Distinguish Verification Levels:** Clearly separate code implementation, mocked tests, live verification, and cloud deployments.
   - **Ambiguity Guard:** If evidence is insufficient or a decision requires user clarification, leave the status unchanged and ask.

4. **Safety & Credential Check**:
   - Verify that **no secret values, API keys, passwords, or tokens** are included in `PROGRESS.md` or any report. Only mention environment variable names.

5. **Report & Commit Suggestion**:
   - Present a concise diff/summary of the changes made to `PROGRESS.md`.
   - Suggest a clear, conventional git commit message for the session's work (e.g. `feat(...)` or `docs(...)`).
   - **Never commit, push, or deploy automatically.** Stop and wait for user approval.
