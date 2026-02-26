# Agent Skills: GitLab Code Review Skill

This repository contains the assets for a Codex skill that reviews a GitLab MR diff and posts inline comments.

## What is in this repo

- `codex-code-reviewer.md`: skill instructions/prompt.
- `scripts/post_gitlab_comments.py`: script that posts `review_comments.json` comments to the MR.

## How the global skill works

Codex loads skills from your global skills directory (usually `~/.codex/skills`).

For this skill, the expected global layout is:

```text
~/.codex/skills/code-review/SKILL.md
~/.codex/skills/code-review/scripts/post_gitlab_comments.py
```

If you edit files in this repo, copy/sync them to the global skill directory so Codex uses the latest version.

## Important: run inside the target repository

The skill runs against the **current working directory**.  
You must start Codex inside the Git repository that contains the MR branch you want to review.

Example:

```bash
cd /path/to/repo-under-review
codex
```

Then ask Codex to use the skill, for example:

```text
Use $code-review to review this MR.
```

## Runtime behavior

When invoked correctly, the skill:

1. Fetches remote refs and computes diff vs target branch.
2. Reviews only changed lines.
3. Writes `review_comments.json` to the repo root.
4. Runs:
   `python3 ~/.codex/skills/code-review/scripts/post_gitlab_comments.py review_comments.json`

## Required setup

- `GITLAB_TOKEN` must be set (recommended).
- Git remote must point to GitLab.
- Current branch should match the MR source branch.

```bash
export GITLAB_TOKEN="your_token"
```

## Optional per-repo config

Create `.codex-reviewer.json` in the repo root:

```json
{
  "target_branch": "origin/main",
  "remote_name": "origin",
  "gitlab_host": null,
  "project_path": null,
  "dry_run": false
}
```

