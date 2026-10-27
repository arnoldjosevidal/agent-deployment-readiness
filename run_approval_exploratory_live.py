"""Run only a separately authorized EXPLORATORY_LIVE_NON_B1 approval workflow."""
from getpass import getpass
from pathlib import Path
import argparse
import secrets

from adr_approval.exploratory_live_runtime import build_exploratory_live_model
from adr_approval.server import serve


def main():
    parser = argparse.ArgumentParser(description="Start the isolated ADR exploratory live approval console.")
    parser.add_argument("--enable-exploratory-live", action="store_true", required=True,
                        help="Explicitly acknowledge EXPLORATORY_LIVE_NON_B1; this does not satisfy B1.")
    parser.add_argument("--grant", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    model = build_exploratory_live_model(args.grant, args.evidence_root)
    password = getpass("Choose a local operator password (16+ characters): ")
    if len(password) < 16:
        raise SystemExit("Password must be at least 16 characters.")
    confirmation = getpass("Confirm local operator password: ")
    if not secrets.compare_digest(password, confirmation):
        raise SystemExit("Passwords did not match.")
    serve(args.db, password, port=args.port, model=model)


if __name__ == "__main__":
    main()
