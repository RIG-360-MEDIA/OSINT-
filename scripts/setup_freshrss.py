"""
FreshRSS first-run setup script.

Uses the FreshRSS CLI tools inside the container (via docker exec) OR
direct PHP CLI execution when running inside the container itself.

Idempotent — safe to run twice; skips setup if admin can already authenticate.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import httpx

FRESHRSS_URL: str = os.environ.get("FRESHRSS_URL", "http://rig-freshrss:80").rstrip("/")
FRESHRSS_USERNAME: str = os.environ.get("FRESHRSS_USERNAME", "admin")
FRESHRSS_PASSWORD: str = os.environ.get("FRESHRSS_PASSWORD", "")

CLI_BASE = "/app/www/cli"
DATA_PATH = "/config/www/freshrss/data"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def wait_for_freshrss(max_retries: int = 30, delay: int = 5) -> bool:
    print(f"Waiting for FreshRSS at {FRESHRSS_URL} …")
    for attempt in range(1, max_retries + 1):
        try:
            resp = httpx.get(f"{FRESHRSS_URL}/i/", timeout=10, follow_redirects=True)
            if resp.status_code < 500:
                print(f"  FreshRSS accessible (attempt {attempt}, HTTP {resp.status_code})")
                return True
        except Exception as exc:
            print(f"  Attempt {attempt}/{max_retries}: {exc}")
        time.sleep(delay)
    return False


def get_greader_token() -> str | None:
    try:
        resp = httpx.post(
            f"{FRESHRSS_URL}/api/greader.php/accounts/ClientLogin",
            data={"Email": FRESHRSS_USERNAME, "Passwd": FRESHRSS_PASSWORD},
            timeout=15,
        )
        if resp.status_code == 200:
            for line in resp.text.splitlines():
                if line.startswith("Auth="):
                    return line[5:].strip()
    except Exception as exc:
        print(f"  GReader auth attempt: {exc}")
    return None


def run_cli(args: list[str]) -> tuple[int, str]:
    """Run a FreshRSS CLI PHP script with DATA_PATH set."""
    env = {**os.environ, "DATA_PATH": DATA_PATH}
    result = subprocess.run(
        ["php", *args],
        capture_output=True,
        text=True,
        env=env,
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode, output


def fix_api_password_hash() -> None:
    """
    Write correct bcrypt hash of the API password directly to the user config.
    Uses a PHP script to avoid shell escaping issues with bcrypt $ chars.
    """
    fix_script = f"""<?php
$password = '{FRESHRSS_PASSWORD}';
$hash = password_hash($password, PASSWORD_BCRYPT);
$file = '{DATA_PATH}/users/{FRESHRSS_USERNAME}/config.php';
$content = file_get_contents($file);
$content = preg_replace_callback(
    "/'apiPasswordHash' => '[^']*'/",
    function() use ($hash) {{ return "'apiPasswordHash' => '" . $hash . "'"; }},
    $content
);
file_put_contents($file, $content);
$cfg = include($file);
$ok = password_verify($password, $cfg['apiPasswordHash']);
echo $ok ? "OK\\n" : "FAIL\\n";
"""
    script_path = "/tmp/fix_api_hash.php"
    with open(script_path, "w") as f:
        f.write(fix_script)

    env = {**os.environ, "DATA_PATH": DATA_PATH}
    result = subprocess.run(["php", script_path], capture_output=True, text=True, env=env)
    output = (result.stdout + result.stderr).strip()
    print(f"  Hash fix result: {output}")


def fix_permissions() -> None:
    """Ensure www-data (abc user in linuxserver) can read user config."""
    user_dir = f"{DATA_PATH}/users/{FRESHRSS_USERNAME}"
    subprocess.run(
        ["chown", "-R", "abc:users", user_dir],
        capture_output=True,
    )
    subprocess.run(
        ["chmod", "-R", "750", user_dir],
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if not FRESHRSS_PASSWORD:
        print("ERROR: FRESHRSS_PASSWORD environment variable is not set.")
        sys.exit(1)

    if not wait_for_freshrss():
        print("ERROR: FreshRSS not accessible after retries.")
        sys.exit(1)

    # Idempotency — try auth first
    token = get_greader_token()
    if token:
        print("FreshRSS already configured. GReader API authenticated.")
        print("FreshRSS setup complete. GReader API authenticated.")
        return

    print("Running FreshRSS CLI installer …")

    # Step 1: do-install
    rc, out = run_cli([
        f"{CLI_BASE}/do-install.php",
        "--default-user", FRESHRSS_USERNAME,
        "--auth-type", "form",
        "--environment", "production",
        "--db-type", "sqlite",
        "--base-url", "http://localhost:8081",
    ])
    print(f"  do-install: rc={rc} {out[:100]}")

    # Step 2: enable API
    rc, out = run_cli([
        f"{CLI_BASE}/reconfigure.php",
        "--api-enabled", "1",
    ])
    print(f"  reconfigure api: rc={rc} {out[:100]}")

    # Step 3: create admin user
    rc, out = run_cli([
        f"{CLI_BASE}/create-user.php",
        "--user", FRESHRSS_USERNAME,
        "--password", FRESHRSS_PASSWORD,
        "--api-password", FRESHRSS_PASSWORD,
        "--no-default-feeds",
    ])
    print(f"  create-user: rc={rc} {out[:100]}")

    # Step 4: fix bcrypt hash (preg_replace backref issue in CLI)
    fix_api_password_hash()

    # Step 5: fix file permissions
    fix_permissions()

    time.sleep(2)

    token = get_greader_token()
    if token:
        print("FreshRSS setup complete. GReader API authenticated.")
    else:
        print("ERROR: GReader API auth failed after setup.")
        sys.exit(1)


if __name__ == "__main__":
    main()
