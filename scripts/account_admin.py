"""Small local-only account administration command.

Run on the application host or a trusted maintenance workstation.  It never
prints passwords, platform credentials or stored reset-token hashes.
"""
import argparse
import sys

import auth


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("suspend", "resume", "issue-reset"):
        item = sub.add_parser(name)
        item.add_argument("username")
        if name != "issue-reset":
            item.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    if args.command == "issue-reset":
        token = auth.issue_password_reset(args.username)
        if not token:
            print("account not found", file=sys.stderr)
            return 1
        print(token)  # displayed once for secure out-of-band delivery
        return 0
    status = "suspended" if args.command == "suspend" else "active"
    if not auth.set_account_status(args.username, status, args.reason):
        print("account not found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
