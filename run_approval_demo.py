from getpass import getpass
from pathlib import Path
import argparse
import secrets

from adr_approval.server import serve


def main():
    parser = argparse.ArgumentParser(description="Start the local ADR human-approval demo (no provider calls).")
    parser.add_argument("--db", default=str(Path("approval-demo.sqlite3").resolve()))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    password = getpass("Choose a local operator password (16+ characters): ")
    if len(password) < 16:
        raise SystemExit("Password must be at least 16 characters.")
    confirm = getpass("Confirm local operator password: ")
    if not secrets.compare_digest(password, confirm):
        raise SystemExit("Passwords did not match.")
    serve(args.db, password, port=args.port)


if __name__ == "__main__":
    main()
