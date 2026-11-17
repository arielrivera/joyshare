"""Commands for the person who runs the server, and for the ./joyshare script.

    docker compose exec web python -m app.cli setup-code
    docker compose exec web python -m app.cli busy
    docker compose exec web python -m app.cli update-failed "REASON"

setup-code     Prints a one-time code that registers a new device for the admin.
               Use it for the very first device, or to get back in if every passkey is lost.
busy           Prints how many videos are waiting or being made. Exits 0 if any are, 1 if none.
               "./joyshare self-update" uses it to wait instead of cutting someone's video off.
update-failed  Sends the admin an alert that new code was not put live, with the reason.
update-check VERSION SUBJECT MODE EVERY
               The update helper checking in (see app/codeupdate.py). Exits 0 when the admin asked for an update.
update-status STATUS [VERSION] [DETAIL]
               The update helper reporting a step: found, waiting, started, finished, failed, blocked, current.
"""
import sys

from . import auth, codeupdate, config, db, notify
from .i18n import T


def busy(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'running')").fetchone()[0]


def main(argv: list[str]) -> int:
    command, rest = (argv[1] if len(argv) > 1 else ""), argv[2:]
    wrong = (command not in ("setup-code", "busy", "update-failed", "update-check", "update-status")
             or (command == "update-failed" and not rest)
             or (command == "update-check" and len(rest) != 4)
             or (command == "update-status" and not (1 <= len(rest) <= 3 and rest[0] in codeupdate.STATUSES)))
    if wrong:
        print(__doc__)
        return 2
    db.init()
    conn = db.connect()
    try:
        if command == "busy":
            count = busy(conn)
            print(count)
            return 0 if count else 1
        if command == "update-check":
            version, subject, mode, every = rest
            asked = codeupdate.check_in(conn, version, subject, mode, int(every) if every.isdigit() else 0)
            print("asked" if asked else "not asked")
            return 0 if asked else 1
        if command == "update-status":
            codeupdate.report(conn, rest[0], *rest[1:])
            return 0
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
