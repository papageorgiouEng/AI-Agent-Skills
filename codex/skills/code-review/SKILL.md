---
name: code-review
description: Autonomous GitLab MR reviewer that writes JSON findings and posts inline comments via a global script.
---

# Autonomous GitLab MR Reviewer (with de-dup + repo config)

You run inside a git repository.

You MUST:
1) Determine MR diff from local git.
2) Review the diff.
3) Cross-check for “already exists / duplicated” before raising issues when possible.
4) Write `review_comments.json` to repo root.
5) Run the global poster script:
   python3 ~/.codex/skills/code-review/scripts/post_gitlab_comments.py review_comments.json

You have access to:
- Bash
- git
- file write
- python3

Do not ask for confirmation.

---

## Repo Config (Optional, preferred)

If file `.codex-reviewer.json` exists in repo root, use it.
Schema example:
{
"target_branch": "origin/main",
"remote_name": "origin",
"gitlab_host": null,
"project_path": null,
"dry_run": false
}

If missing, use defaults:
- remote_name=origin
- target_branch=origin/main (fallback origin/master)

---

## Diff Gathering

1) git fetch <remote_name> --prune
2) Determine target branch:
- config target_branch if present
- else origin/main, fallback origin/master
3) Produce diff:
   git diff <target_branch>...HEAD --unified=5

Review ONLY what changed in the diff.

---

## Cross-check rules (reduce false positives)

Before suggesting changes like “extract helper”, “already exists”, “duplicate logic”, “use existing util”, do quick checks using bash tools:
- `rg "<symbol>"` or `rg "<error message>"` for existing patterns
- search for similar utilities/modules (names, paths)
- if you claim “already implemented”, cite the file path and function/class name

If you cannot confirm quickly, phrase as a question or skip.

---

## Output requirements

Write `review_comments.json` in repo root ONLY:

{
"comments": [
{
"path": "relative/path/from/repo/root.ext",
"new_line": 123,
"severity": "critical|warning|nit",
"body": "Concise, actionable MR inline comment. Reference symbols/paths when claiming duplication."
}
]
}

Rules:
- `path` must match the diff paths exactly (repo-relative).
- `new_line` MUST be from the NEW file version and should be a changed/nearby line from diff hunk.
- If unsure about exact line, skip the comment (do not guess).
- No markdown, no extra fields.

If nothing found:
{ "comments": [] }

After writing, execute:
python3 ~/.codex/skills/code-review/scripts/post_gitlab_comments.py review_comments.json
