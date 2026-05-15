#!/usr/bin/env python3
"""Railway startup script.

Runs `alembic upgrade head` first so any pending schema migrations land
before uvicorn binds the port and the platform starts serving traffic.
Fail-fast on migration error — better to crash the container (Railway
will restart) than to serve requests against an out-of-date schema.

For one-off operational migrations (stamping baseline, downgrades on
rollback), use `alembic` directly with the Railway DATABASE_URL — this
script only handles the auto-upgrade-to-head boot path.
"""
import logging
import os
import subprocess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [start] %(levelname)s %(message)s",
)
logger = logging.getLogger("start")


def _run_alembic_upgrade() -> None:
    """Run `alembic upgrade head` synchronously. Raise on any failure
    so the entrypoint exits non-zero and Railway restarts the container.
    """
    if not os.getenv("DATABASE_URL"):
        logger.error("DATABASE_URL is not set — cannot run alembic upgrade")
        raise SystemExit(1)

    if os.getenv("SKIP_ALEMBIC_UPGRADE", "").lower() in {"1", "true", "yes"}:
        # Escape hatch for emergency rollback drills. Off by default.
        logger.warning("SKIP_ALEMBIC_UPGRADE set — skipping alembic upgrade head")
        return

    logger.info("Running alembic upgrade head...")
    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as e:
        logger.error("alembic upgrade head failed (exit code %d)", e.returncode)
        if e.stdout:
            logger.error("alembic stdout:\n%s", e.stdout)
        if e.stderr:
            logger.error("alembic stderr:\n%s", e.stderr)
        raise SystemExit(1) from e
    except subprocess.TimeoutExpired as e:
        logger.error("alembic upgrade head timed out after 120 seconds")
        raise SystemExit(1) from e
    except FileNotFoundError as e:
        logger.error("alembic binary not on PATH — is the package installed?")
        raise SystemExit(1) from e

    # Alembic logs revision lines to stderr; surface them in container logs.
    if result.stderr:
        for line in result.stderr.rstrip().splitlines():
            logger.info("alembic: %s", line)
    logger.info("Alembic upgrade head complete.")


if __name__ == "__main__":
    _run_alembic_upgrade()

    port = int(os.getenv("PORT", 8000))
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, ws="websockets")
