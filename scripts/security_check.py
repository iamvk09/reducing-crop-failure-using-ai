#!/usr/bin/env python3
"""Lightweight Secret and Credential Scanner for CI/CD and Local Verification.

Scans the repository for accidentally committed secrets, credentials, and sensitive
configuration files without false positives on mock tokens or documentation templates.
Never outputs detected secret values to logs.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

# Set UTF-8 encoding for stdout/stderr if possible
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Sensitive file names that must never be tracked in git
DISALLOWED_TRACKED_FILES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.staging",
    "id_rsa",
    "id_ed25519",
    "service_account.json",
    "credentials.json",
    "gee_key.json",
    "gee-key.json",
    "earth_engine_key.json",
    "earth-engine-key.json",
    "google_credentials.json",
}

# Regex patterns for high-risk secrets (avoiding test fixtures / mock tokens)
HIGH_RISK_PATTERNS = [
    (re.compile(r"-----BEGIN (RSA|EC|DSA|OPENSSH|PGP|PRIVATE) KEY-----"), "Private Cryptographic Key"),
    (re.compile(r"sk_live_[0-9a-zA-Z]{24,}"), "Stripe Live Secret Key"),
    (re.compile(r"ghp_[0-9a-zA-Z]{36}"), "GitHub Personal Access Token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS Access Key ID"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "Google API Key"),
    (re.compile(r"eyJhbGciOi[A-Za-z0-9_\-\.]{100,}"), "Live JWT / Supabase Service Token"),
]

# Paths and extensions to ignore (e.g. build artifacts, tests with mock fixtures, lock files)
IGNORED_PATHS = {
    ".git",
    ".pytest_cache",
    ".next",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    "postman", # Contains placeholder templates
}

ALLOWED_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".sql", ".yml", ".yaml",
    ".md", ".txt", ".toml", ".ini", ".env.example"
}


def get_tracked_files() -> list[str]:
    """Retrieve list of git-tracked files, or fall back to directory walk."""
    try:
        res = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = [f.strip() for f in res.stdout.splitlines() if f.strip()]
        if files:
            return files
    except Exception:
        pass

    # Fallback if git is not available
    walked = []
    for root, _, filenames in os.walk("."):
        if any(ign in root.split(os.sep) for ign in IGNORED_PATHS):
            continue
        for fn in filenames:
            walked.append(os.path.normpath(os.path.join(root, fn)))
    return walked


def scan_repository() -> tuple[int, list[str]]:
    """Scan tracked repository files for sensitive files and secret patterns."""
    violations = []
    files = get_tracked_files()

    for file_path in files:
        norm_path = os.path.normpath(file_path)
        parts = norm_path.split(os.sep)
        filename = parts[-1]

        # 1. Check for disallowed filenames
        if filename in DISALLOWED_TRACKED_FILES:
            violations.append(f"Disallowed sensitive file tracked in git: {norm_path}")
            continue

        # Skip ignored directories and test fixtures
        if any(ign in parts for ign in IGNORED_PATHS):
            continue

        # Skip files that are explicitly test fixtures or examples
        if "test" in filename.lower() or filename.endswith(".example") or filename.endswith(".sample"):
            continue

        ext = os.path.splitext(filename)[1].lower()
        if ext and ext not in ALLOWED_EXTENSIONS:
            continue

        # 2. Check file contents against high-risk secret patterns
        try:
            with open(norm_path, "r", encoding="utf-8", errors="ignore") as f:
                for line_no, line in enumerate(f, 1):
                    # Skip comment-only or example-only lines
                    if line.strip().startswith("#") and "example" in line.lower():
                        continue
                    if "placeholder" in line.lower() or "your-" in line.lower() or "dev-insecure" in line.lower():
                        continue

                    for pattern, desc in HIGH_RISK_PATTERNS:
                        if pattern.search(line):
                            # DO NOT print the secret value
                            violations.append(
                                f"Potential secret pattern detected ({desc}) in {norm_path}:{line_no}"
                            )
                            break
        except Exception:
            # Binary or unreadable file
            pass

    return len(violations), violations


def main() -> int:
    print("[SECURITY] Running Automated Security & Secret Scan...")
    count, violations = scan_repository()

    if count == 0:
        print("[SUCCESS] Security Scan Passed: No tracked secret files or raw credentials detected.")
        return 0
    else:
        print(f"[FAIL] Security Scan Failed: {count} violation(s) detected:")
        for v in violations:
            print(f"   - {v}")
        print("\nEnsure secrets are configured via environment variables and never committed to git.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
