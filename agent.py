#!/usr/bin/env python3
"""
agent.py

Collect simple CI metrics from GitHub Actions for the current repository
and send them to a Model Context Protocol (MCP) server for predictive analysis.

Behavior:
- Reads `GITHUB_REPOSITORY` (owner/repo) and `GITHUB_TOKEN` from the environment by default.
- If an MCP server is available at `MCP_SERVER_URL` (env) the script will try common endpoints
  ("/predict", "/analyze", "/v1/predict") and POST the payload. If a server responds with 200
  it prints the server response.
- If no MCP server responds, the script prints a local heuristic analysis of CI health.

This is intentionally conservative (no external MCP API assumptions). Configure the MCP server
URL and GitHub details using environment variables or command-line args.

Usage examples:
  # in GitHub Actions CI the environment already has GITHUB_REPOSITORY and GITHUB_TOKEN
  python agent.py

  # run locally against another repo and MCP server
  python agent.py --repo myorg/myrepo --mcp-url http://127.0.0.1:8080

"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

import base64


def parse_iso(s: str) -> datetime:
    # GitHub time strings end with Z. datetime.fromisoformat doesn't accept 'Z', so replace.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def fetch_workflow_runs(repo: str, token: Optional[str], per_page: int = 50) -> List[Dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/actions/runs?per_page={per_page}"
    headers = {
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("workflow_runs", [])


def compute_metrics(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(runs)
    successes = 0
    failures = 0
    durations = []
    recent_failures = []

    for r in runs:
        conclusion = r.get("conclusion")
        if conclusion == "success":
            successes += 1
        elif conclusion in ("failure", "cancelled", "timed_out"):
            failures += 1

        # duration = updated_at - created_at (best-effort)
        created = r.get("created_at")
        updated = r.get("updated_at")
        if created and updated:
            try:
                dur = (parse_iso(updated) - parse_iso(created)).total_seconds()
                if dur >= 0:
                    durations.append(dur)
            except Exception:
                pass

        if conclusion in ("failure", "timed_out"):
            recent_failures.append({
                "id": r.get("id"),
                "name": r.get("name"),
                "conclusion": conclusion,
                "html_url": r.get("html_url"),
            })

    success_rate = (successes / total) if total else None
    avg_duration = (sum(durations) / len(durations)) if durations else None

    return {
        "total_runs": total,
        "successes": successes,
        "failures": failures,
        "success_rate": success_rate,
        "avg_duration_seconds": avg_duration,
        "recent_failures": recent_failures[:10],
    }


def local_analysis(metrics: Dict[str, Any]) -> Dict[str, Any]:
    # Simple heuristic analysis as a fallback when an MCP server is not available.
    total = metrics.get("total_runs", 0)
    success_rate = metrics.get("success_rate")
    avg_dur = metrics.get("avg_duration_seconds")

    status = "unknown"
    recommendations = []

    if total == 0:
        status = "no-data"
        recommendations.append("No workflow runs found for the repository.")
    else:
        if success_rate is not None:
            if success_rate < 0.6:
                status = "unhealthy"
                recommendations.append("CI success rate below 60% — investigate flaky or failing tests.")
            elif success_rate < 0.9:
                status = "degraded"
                recommendations.append("CI success rate between 60% and 90% — look for intermittent failures.")
            else:
                status = "healthy"
                recommendations.append("CI success rate above 90%.")

        if avg_dur is not None and avg_dur > 20 * 60:
            recommendations.append("Average workflow duration is high (>20 minutes). Consider speeding up or splitting jobs.")

    return {
        "status": status,
        "recommendations": recommendations,
        "metrics": metrics,
    }


def try_send_to_mcp(mcp_url: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # Try a few common endpoint paths that MCP servers might implement. This is conservative;
    # if you run your own MCP server, ensure it accepts POST JSON on one of these endpoints.
    candidates = ["/predict", "/analyze", "/v1/predict", "/mcp/predict", ""]
    headers = {"Content-Type": "application/json"}

    for suffix in candidates:
        endpoint = mcp_url.rstrip("/") + suffix
        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        except requests.RequestException as e:
            # network error, try next
            print(f"MCP: request to {endpoint} failed: {e}", file=sys.stderr)
            continue

        if resp.status_code == 200:
            try:
                return resp.json()
            except Exception:
                return {"raw_text": resp.text}
        else:
            print(f"MCP: {endpoint} returned {resp.status_code}", file=sys.stderr)

    return None


def discover_mcp_from_repo(repo: str, token: Optional[str]) -> Optional[str]:
    """Try to discover an MCP URL from a repository file .github/mcp.json.

    Order:
    1. Try GitHub Contents API (works for private repos with token).
    2. Fallback to raw.githubusercontent.com for public repos.
    Returns the mcp_url string if found and parsable, otherwise None.
    """
    path = ".github/mcp.json"
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    contents_url = f"https://api.github.com/repos/{repo}/contents/{path}"
    try:
        r = requests.get(contents_url, headers=headers, timeout=15)
        if r.status_code == 200:
            j = r.json()
            # GitHub contents API returns base64-encoded content
            content_b64 = j.get("content")
            if content_b64:
                try:
                    raw = base64.b64decode(content_b64).decode("utf-8")
                    cfg = json.loads(raw)
                    mcp = cfg.get("mcp_url")
                    if mcp:
                        print(f"Discovered MCP URL from {path} via Contents API: {mcp}")
                        return mcp
                except Exception as e:
                    print(f"Failed to parse {path} from contents API: {e}", file=sys.stderr)
        else:
            # non-200 is fine; we'll fallback to raw URL
            pass
    except Exception as e:
        print(f"Contents API lookup failed: {e}", file=sys.stderr)

    # Fallback: try raw.githubusercontent.com (public repo)
    raw_url = f"https://raw.githubusercontent.com/{repo}/main/{path}"
    try:
        r2 = requests.get(raw_url, timeout=10)
        if r2.status_code == 200:
            try:
                cfg = r2.json()
                mcp = cfg.get("mcp_url")
                if mcp:
                    print(f"Discovered MCP URL from {path} via raw.githubusercontent: {mcp}")
                    return mcp
            except Exception as e:
                print(f"Failed to parse raw {path}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Raw URL lookup failed: {e}", file=sys.stderr)

    return None


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="CI health agent that posts metrics to an MCP server or prints local analysis.")
    p.add_argument("--repo", help="GitHub repo in owner/repo format (falls back to GITHUB_REPOSITORY env)")
    p.add_argument("--mcp-url", help="MCP server base URL (falls back to MCP_SERVER_URL env or http://127.0.0.1:8080)")
    p.add_argument("--per-page", type=int, default=50, help="Number of workflow runs to fetch (max 100).")
    p.add_argument("--no-mcp", action="store_true", help="Do not attempt to contact an MCP server; only run local analysis.")
    args = p.parse_args(argv)

    repo = args.repo or os.getenv("GITHUB_REPOSITORY")
    if not repo:
        print("ERROR: repository not specified. Set GITHUB_REPOSITORY or use --repo.", file=sys.stderr)
        return 2

    token = os.getenv("GITHUB_TOKEN")

    # MCP URL precedence (highest -> lowest):
    # 1. CLI --mcp-url
    # 2. GITHUB_MCP_URL env (explicit GitHub-hosted MCP)
    # 3. MCP_SERVER_URL env
    # 4. repository-level config in .github/mcp.json (discovered via API/raw)
    # 5. default local http://127.0.0.1:8080
    mcp_url = None
    if args.mcp_url:
        mcp_url = args.mcp_url
    else:
        mcp_url = os.getenv("GITHUB_MCP_URL") or os.getenv("MCP_SERVER_URL")

    # If we still don't have an MCP URL, attempt repo discovery (content file) when possible.
    if not mcp_url:
        try:
            discovered = discover_mcp_from_repo(repo, token)
            if discovered:
                mcp_url = discovered
        except Exception as e:
            print(f"MCP discovery failed: {e}", file=sys.stderr)

    if not mcp_url:
        mcp_url = "http://127.0.0.1:8080"

    try:
        runs = fetch_workflow_runs(repo, token, per_page=args.per_page)
    except Exception as e:
        print(f"Failed to fetch workflow runs from GitHub: {e}", file=sys.stderr)
        return 3

    metrics = compute_metrics(runs)

    payload = {
        "repository": repo,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
    }

    print("Collected metrics:")
    print(json.dumps(payload, indent=2))

    if args.no_mcp:
        print("--no-mcp set; skipping MCP server contact. Running local heuristic analysis:")
        analysis = local_analysis(metrics)
        print(json.dumps(analysis, indent=2))
        return 0

    print(f"Attempting to contact MCP server at {mcp_url}...")
    mcp_response = try_send_to_mcp(mcp_url, payload)

    if mcp_response is not None:
        print("MCP server responded with:")
        print(json.dumps(mcp_response, indent=2))
        return 0

    print("No MCP server responded. Running local heuristic analysis:")
    analysis = local_analysis(metrics)
    print(json.dumps(analysis, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
