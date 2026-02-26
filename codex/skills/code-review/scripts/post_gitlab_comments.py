#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import requests


# ===============================
# TEMP OPTIONS
# Prefer env var; supports hardcode fallback.
TOKEN = os.environ.get("GITLAB_TOKEN", "").strip()
if not TOKEN:
  # If you insist on hardcoding for now, put it here (DO NOT COMMIT)
  TOKEN = "YOUR_TOKEN_HERE"
# ===============================


def sh(cmd: List[str]) -> str:
  return subprocess.check_output(cmd, text=True).strip()


def load_repo_config() -> Dict[str, Any]:
  path = ".codex-reviewer.json"
  if not os.path.exists(path):
    return {}
  with open(path, "r", encoding="utf-8") as f:
    return json.load(f)


def parse_remote(url: str) -> Tuple[str, str]:
  """
  Supports:
    - git@gitlab.host:group/subgroup/repo.git
    - https://gitlab.host/group/subgroup/repo.git
  Returns (host, project_path)
  """
  m = re.match(r"git@([^:]+):(.+?)(?:\.git)?$", url)
  if m:
    return m.group(1), m.group(2)

  m = re.match(r"https?://([^/]+)/(.+?)(?:\.git)?$", url)
  if m:
    return m.group(1), m.group(2)

  raise RuntimeError(f"Unsupported remote URL format: {url}")


def api_get(host: str, path: str, params: Optional[dict] = None) -> Any:
  scheme = os.environ.get("GITLAB_SCHEME", "https")
  url = f"{scheme}://{host}/api/v4{path}"
  r = requests.get(url, headers={"PRIVATE-TOKEN": TOKEN}, params=params, timeout=30)
  if r.status_code >= 300:
    raise RuntimeError(f"GET {url} failed: {r.status_code} {r.text}")
  return r.json()


def api_post(host: str, path: str, payload: dict) -> Any:
  scheme = os.environ.get("GITLAB_SCHEME", "https")
  url = f"{scheme}://{host}/api/v4{path}"
  r = requests.post(
    url,
    headers={"PRIVATE-TOKEN": TOKEN, "Content-Type": "application/json"},
    data=json.dumps(payload),
    timeout=30,
  )
  if r.status_code >= 300:
    raise RuntimeError(f"POST {url} failed: {r.status_code} {r.text}")
  return r.json()


def get_origin_info(cfg: Dict[str, Any]) -> Tuple[str, str]:
  # Allow override from config (rare, but useful for multi-remote repos)
  host = cfg.get("gitlab_host")
  project_path = cfg.get("project_path")
  if host and project_path:
    return host, project_path

  remote_name = cfg.get("remote_name", "origin")
  remote = sh(["git", "remote", "get-url", remote_name])
  return parse_remote(remote)


def get_current_branch() -> str:
  branch = sh(["git", "branch", "--show-current"])
  if not branch:
    raise RuntimeError("Could not determine current branch.")
  return branch


def find_open_mr(host: str, project_id: str, source_branch: str) -> dict:
  mrs = api_get(
    host,
    f"/projects/{project_id}/merge_requests",
    params={"state": "opened", "source_branch": source_branch, "per_page": 50},
  )
  if not mrs:
    raise RuntimeError(f"No open MR found for source_branch={source_branch}")
  # If multiple, take most recently updated
  return sorted(mrs, key=lambda x: x.get("updated_at", ""), reverse=True)[0]


def get_diff_refs(host: str, project_id: str, mr_iid: int) -> dict:
  mr_full = api_get(host, f"/projects/{project_id}/merge_requests/{mr_iid}")
  diff_refs = mr_full.get("diff_refs")
  if not diff_refs:
    raise RuntimeError("MR response missing diff_refs; cannot post inline comments.")
  return diff_refs


def normalize_body(s: str) -> str:
  # Normalize whitespace to improve duplicate detection
  return re.sub(r"\s+", " ", (s or "").strip())


def load_existing_discussions(host: str, project_id: str, mr_iid: int) -> List[dict]:
  # Discussions can paginate; simple best-effort fetch first 100
  return api_get(
    host,
    f"/projects/{project_id}/merge_requests/{mr_iid}/discussions",
    params={"per_page": 100},
  )


def make_key(path: str, line: int, body: str) -> Tuple[str, int, str]:
  return (path, int(line), normalize_body(body))


def existing_keys_from_discussions(discussions: List[dict]) -> set:
  keys = set()
  for d in discussions or []:
    notes = d.get("notes") or []
    for n in notes:
      pos = n.get("position") or {}
      new_path = pos.get("new_path")
      new_line = pos.get("new_line")
      body = n.get("body", "")
      if new_path and new_line:
        keys.add(make_key(new_path, int(new_line), body))
  return keys


def main() -> None:
  if len(sys.argv) != 2:
    print("Usage: post_gitlab_comments.py review_comments.json", file=sys.stderr)
    sys.exit(2)

  if not TOKEN or TOKEN == "PASTE_YOUR_TOKEN_HERE":
    print("Missing token. Set GITLAB_TOKEN or edit TOKEN in script (not recommended).", file=sys.stderr)
    sys.exit(2)

  review_file = sys.argv[1]
  if not os.path.exists(review_file):
    print(f"File not found: {review_file}", file=sys.stderr)
    sys.exit(2)

  cfg = load_repo_config()
  dry_run = bool(cfg.get("dry_run", False))

  with open(review_file, "r", encoding="utf-8") as f:
    payload = json.load(f)

  comments = payload.get("comments", [])
  if not comments:
    print("No comments to post.")
    return

  host, project_path = get_origin_info(cfg)
  project_id = urllib.parse.quote(project_path, safe="")
  branch = get_current_branch()

  mr = find_open_mr(host, project_id, branch)
  mr_iid = int(mr["iid"])
  project_ref = str(mr.get("project_id") or project_id)

  diff_refs = get_diff_refs(host, project_ref, mr_iid)
  base_sha = diff_refs["base_sha"]
  start_sha = diff_refs["start_sha"]
  head_sha = diff_refs["head_sha"]

  discussions = load_existing_discussions(host, project_ref, mr_iid)
  existing = existing_keys_from_discussions(discussions)

  posted = 0
  skipped_dup = 0

  for c in comments:
    path = c.get("path")
    new_line = c.get("new_line")
    body = c.get("body")
    severity = c.get("severity", "warning")

    if not path or new_line is None or not body:
      continue

    full_body = f"[{severity}] {body}"
    key = make_key(path, int(new_line), full_body)

    if key in existing:
      skipped_dup += 1
      continue

    req = {
      "body": full_body,
      "position": {
        "position_type": "text",
        "base_sha": base_sha,
        "start_sha": start_sha,
        "head_sha": head_sha,
        "new_path": path,
        "old_path": path,
        "new_line": int(new_line),
      },
    }

    if dry_run:
      print(f"DRY_RUN would post: {path}:{new_line} {full_body}")
      posted += 1
      continue

    api_post(host, f"/projects/{project_ref}/merge_requests/{mr_iid}/discussions", req)
    posted += 1
    existing.add(key)

  print(f"MR !{mr_iid} — posted={posted}, skipped_duplicates={skipped_dup}, dry_run={dry_run}")


if __name__ == "__main__":
  main()
