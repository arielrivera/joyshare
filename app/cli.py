"""Commands for the person who runs the server, and for the ./joyshare script.

    docker compose exec web python -m app.cli setup-code
    docker compose exec web python -m app.cli busy
    docker compose exec web python -m app.cli update-failed "REASON"

setup-code     Prints a one-time code that registers a new device for the admin.
               Use it for the very first device, or to get back in if every passkey is lost.
busy           Prints how many videos are waiting or being made. Exits 0 if any are, 1 if none.
               "./joyshare self-update" uses it to wait instead of cutting someone's video off.
update-failed  Sends the admin an alert that new code was not put live, with the reason.
"""
import sys

from . import auth, config, db, notify
from .i18n import T


def busy(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'running')").fetchone()[0]


def main(argv: list[str]) -> int:
    command, rest = (argv[1] if len(argv) > 1 else ""), argv[2:]
    if command not in ("setup-code", "busy", "update-failed") or (command == "update-failed") != bool(rest):
        print(__doc__)
        return 2
    db.init()
    conn = db.connect()
    try:
        if command == "busy":
            count = busy(conn)
            print(count)
            return 0 if count else 1
        if command == "update-failed":
            sent = notify.send(conn, "update_failed", "Update not put live",
                               T("joyshare stayed on the running version: {reason}", reason=" ".join(rest)[:300]))
            print("Alert sent." if sent else "No alert sent (alerts are off, or ntfy could not be reached).")
            return 0
        code = auth.recovery_code(conn)
    finally:
        conn.close()
    print(f"\n  One-time code:  {code}\n  Open {config.PUBLIC_URL} and enter it to register a device.\n"
          "  It works once and expires in 30 minutes.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
