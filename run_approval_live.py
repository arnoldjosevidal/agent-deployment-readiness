"""Start a hash-bound live-model approval workflow after separate authorization.

The normal run_approval_demo.py remains offline-only. This entrypoint refuses
to start without a new approved grant, fresh evidence sink, valid token binding
and the required environment credential; it never prints the credential.
"""
from getpass import getpass
from pathlib import Path
import argparse
import secrets

from adr_approval.live_runtime import build_live_model
from adr_approval.server import serve


def main():
    parser = argparse.ArgumentParser(description="Start the separately authorized ADR live-model approval workflow.")
    parser.add_argument("--grant", required=True, help="Path to the newly approved ADR live grant JSON.")
    parser.add_argument("--evidence-root", required=True, help="Fresh isolated durable evidence directory.")
    parser.add_argument("--db", required=True, help="New isolated approval workflow SQLite database.")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    model = build_live_model(args.grant, args.evidence_root)
    password = getpass("Choose a local operator password (16+ characters): ")
    if len(password) < 16:
        raise SystemExit("Password must be at least 16 characters.")
    confirm = getpass("Confirm local operator password: ")
    if not secrets.compare_digest(password, confirm):
        raise SystemExit("Passwords did not match.")
    serve(args.db, password, port=args.port, model=model)


if __name__ == "__main__":
    main()
