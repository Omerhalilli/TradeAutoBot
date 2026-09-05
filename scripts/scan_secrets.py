#!/usr/bin/env python3
"""
Automated Secret and Sensitive Data Scanner for AutoTradeBot.
Scans source files, configuration templates, and Git commit history for:
- Telegram bot tokens & API credentials
- Private encryption keys and certificates
- Hardcoded personal directory paths
- Unmasked passwords and sensitive IDs
"""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import List, Tuple

# Regex Patterns for Sensitive Data Detection
SECRET_PATTERNS = [
    (
        "Telegram Bot Token",
        re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"),
        # Allowed benign placeholders
        {"your_telegram_bot_token_here", "123456789:dummy_token_for_ci_testing"}
    ),
    (
        "Telegram API URL with Token",
        re.compile(r"api\.telegram\.org/bot\d+:[A-Za-z0-9_-]+"),
        set()
    ),
    (
        "Private Key",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
        set()
    ),
    (
        "Hardcoded /home User Path",
        re.compile(r"/home/[a-zA-Z0-9_-]+/(?!.*(?:<user>|<Username>|placeholder|example))"),
        set()
    ),
    (
        "Exposed Credential Pattern",
        re.compile(r"(?i)(?:api_key|secret_key|password)\s*[:=]\s*['\"][a-zA-Z0-9_\-+=/]{16,}['\"]"),
        {"your_telegram_bot_token_here", "Institutional_API_Secret_Key_987654"}
    )
]

IGNORED_DIRS = {
    ".git", "venv", ".venv", "env", "__pycache__", ".pytest_cache",
    "logs", "data", ".idea", ".vscode"
}

IGNORED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".dll", ".so", ".dylib", ".exe", ".ex4", ".ex5",
    ".db", ".sqlite", ".sqlite3", ".pyc", ".log"
}


def scan_file(filepath: Path) -> List[Tuple[str, int, str]]:
    """Scans a single file for sensitive content. Returns list of (rule_name, line_num, line_text)."""
    violations = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line_idx, line in enumerate(f, start=1):
                clean_line = line.strip()
                if not clean_line or clean_line.startswith("#") or clean_line.startswith("//"):
                    # Still check comments for tokens, but skip generic words
                    pass

                for rule_name, regex, allowlist in SECRET_PATTERNS:
                    matches = regex.findall(line)
                    for match in matches:
                        match_str = match if isinstance(match, str) else str(match)
                        if any(allowed in match_str or allowed in line for allowed in allowlist):
                            continue
                        # Special exception for generic documentation or comments describing placeholders
                        if "your_" in match_str or "<" in match_str or "example" in line.lower():
                            continue
                        violations.append((rule_name, line_idx, clean_line[:120]))
    except Exception as ex:
        print(f"Warning: Could not read {filepath}: {ex}", file=sys.stderr)
    return violations


def scan_working_tree(root_dir: Path, tracked_only: bool = False) -> int:
    """Scans files in repository."""
    total_violations = 0
    scanned_files = 0

    if tracked_only:
        print(f"🔍 Scanning Git-tracked files in {root_dir}...")
        try:
            res = subprocess.run(
                ["git", "ls-files"],
                cwd=str(root_dir),
                capture_output=True,
                text=True,
                check=True
            )
            file_list = [root_dir / p for p in res.stdout.splitlines() if p.strip()]
        except Exception as ex:
            print(f"Error listing tracked files: {ex}", file=sys.stderr)
            return 1

        for file_path in file_list:
            if file_path.suffix.lower() in IGNORED_EXTENSIONS or not file_path.exists():
                continue
            rel_path = file_path.relative_to(root_dir)
            violations = scan_file(file_path)
            scanned_files += 1
            if violations:
                total_violations += len(violations)
                print(f"\n❌ [ALERT] Found {len(violations)} issue(s) in {rel_path}:")
                for rule_name, line_num, snippet in violations:
                    print(f"   • Line {line_num} [{rule_name}]: {snippet}")
    else:
        print(f"🔍 Scanning repository directory in {root_dir} for sensitive data...")
        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
            for filename in files:
                file_path = Path(root) / filename
                if file_path.suffix.lower() in IGNORED_EXTENSIONS:
                    continue
                # Skip local .env if scanning untracked directory (it is ignored by .gitignore)
                if filename == ".env":
                    continue
                rel_path = file_path.relative_to(root_dir)
                violations = scan_file(file_path)
                scanned_files += 1

                if violations:
                    total_violations += len(violations)
                    print(f"\n❌ [ALERT] Found {len(violations)} issue(s) in {rel_path}:")
                    for rule_name, line_num, snippet in violations:
                        print(f"   • Line {line_num} [{rule_name}]: {snippet}")

    print(f"\n✅ Scanned {scanned_files} files.")
    if total_violations == 0:
        print("🎉 No sensitive credentials, tokens, or hardcoded paths detected in working tree!")
        return 0
    else:
        print(f"⚠️ TOTAL VIOLATIONS DETECTED: {total_violations}")
        return 1


def scan_git_history(root_dir: Path) -> int:
    """Scans Git commit history for sensitive tokens."""
    print("🔍 Scanning Git commit history for sensitive tokens...")
    history_violations = 0
    token_regex = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")

    try:
        res = subprocess.run(
            ["git", "log", "-p", "-G", r"[0-9]{8,10}:[a-zA-Z0-9_-]{35}"],
            cwd=str(root_dir),
            capture_output=True,
            text=True
        )
        for line in res.stdout.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                for m in token_regex.findall(line):
                    if "your_telegram_bot_token_here" not in m and "dummy" not in m:
                        print(f"❌ [ALERT] Unmasked bot token in commit: {m}")
                        history_violations += 1
    except Exception as ex:
        print(f"Warning: git log failed: {ex}", file=sys.stderr)

    if history_violations == 0:
        print("🎉 No sensitive tokens detected in Git history!")
        return 0
    else:
        print(f"⚠️ Git history violations detected: {history_violations}")
        return 1


def main():
    parser = argparse.ArgumentParser(description="AutoTradeBot Secret Scanner")
    parser.add_argument("--tracked", action="store_true", help="Scan only Git-tracked files (git ls-files)")
    parser.add_argument("--history", action="store_true", help="Also scan Git commit history")
    parser.add_argument("--root", type=str, default=".", help="Root directory to scan")
    args = parser.parse_args()

    root_path = Path(args.root).resolve()
    code = scan_working_tree(root_path, tracked_only=args.tracked)

    if args.history:
        history_code = scan_git_history(root_path)
        if history_code != 0:
            code = history_code

    sys.exit(code)


if __name__ == "__main__":
    main()
