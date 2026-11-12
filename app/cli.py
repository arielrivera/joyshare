"""Commands for the person who runs the server.

    docker compose exec web python -m app.cli setup-code

Prints a one-time code that registers a new device for the admin.
Use it for the very first device, or to get back in if every passkey is lost.
"""
import sys

from . import auth, config, db


def main(argv: list[str]) -> int:
    if argv[1:] != ["setup-code"]:
        print(__doc__)
        return 2
    db.init()
    conn = db.connect()
    try:
        code = auth.recovery_code(conn)
    finally:
        conn.close()
    print(f"\n  One-time code:  {code}\n  Open {config.PUBLIC_URL} and enter it to register a device.\n"
          "  It works once and expires in 30 minutes.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
