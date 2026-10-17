#!/usr/bin/env python3
"""Automated API Smoke Test Runner for Local CI/CD.

Launches the local FastAPI development server, waits for the health endpoint,
executes Newman tests against unauthenticated and security test folders,
and cleanly shuts down the server.
"""

import os
import subprocess
import sys
import time
import urllib.request

# Set UTF-8 encoding for stdout/stderr if possible
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def wait_for_server(url: str = "http://127.0.0.1:8000/health", timeout: float = 15.0) -> bool:
    """Wait for the FastAPI server to become responsive."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def main() -> int:
    print("[NEWMAN] Starting local FastAPI server for API smoke test...")
    server_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--log-level",
            "warning",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        print("[NEWMAN] Waiting for server at http://127.0.0.1:8000/health...")
        if not wait_for_server():
            print("[FAIL] FastAPI server failed to start within timeout.")
            return 1

        print("[SUCCESS] Server is live. Executing Newman smoke tests...")

        # Run unauthenticated health and negative security folders
        cmd = [
            "npx",
            "newman",
            "run",
            "postman/crop-risk-api.postman_collection.json",
            "-e",
            "postman/crop-risk-local.postman_environment.json",
            "--folder",
            "1. Health & Status",
            "--folder",
            "9. Security & Negative Tests",
            "--reporters",
            "cli",
        ]

        # Use shell=True on Windows for npx resolution
        res = subprocess.run(cmd, shell=(os.name == "nt"))
        return res.returncode
    finally:
        print("[NEWMAN] Terminating local server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            server_process.kill()


if __name__ == "__main__":
    sys.exit(main())
