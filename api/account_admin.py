"""Operator commands for accounts, run from the deployment's own shell.

    python -m api.account_admin reset-password someone@example.com
    python -m api.account_admin verify someone@example.com

There is no password reset by email yet. A person who forgets their password
has exactly one way back, and it is this command, run by the operator.

Whoever can run it already has a shell on the machine that holds the
account database, so it grants nothing that shell did not already give. It
was once the only way, on the reasoning that an HTTP route would need a
secret of its own. An admin account is now that secret: the same reset is on
the admin console (api/admin.py), behind the admin's own password, and this
command stays for the operator who has the shell and not a browser.

The new password is generated here rather than typed, so it never appears in
a shell history or a process list, and it is printed once. Nothing else
keeps it: the database stores only its hash.

The operator is the check that the person asking owns the account. Send the
new password to the account's own address, not to whichever address the
request came from.

`verify` marks an address as proven without a link, for the operator who has
checked by other means or whose mail is not working.
"""
from __future__ import annotations

import argparse
import sys

from api import accounts, admin


def _reset_password(email: str) -> int:
    path = accounts.database_path()
    if path is None:
        print("Accounts are not enabled here: ACCOUNTS_DB is not set.", file=sys.stderr)
        return 2
    if not path.is_file():
        # Opening it would create an empty database owned by whoever ran this,
        # which the service may then be unable to write.
        print(f"No account database at {path}. Run this in the service's own shell, "
              "where ACCOUNTS_DB points at the real file.", file=sys.stderr)
        return 2
    password = admin.generated_password()
    try:
        ended = accounts.reset_password(email, password)
    except accounts.AccountError as exc:
        print(f"Not reset: {exc.message}", file=sys.stderr)
        return 2
    print(f"Password reset for {accounts.normalize_email(email)}.")
    print(f"New password (shown once): {password}")
    print(f"Sessions ended: {ended}. Any sign-in lockout for this address is cleared.")
    print("Send it to the account's own address, and ask them to change it after signing in "
          "(Account, then change password).")
    return 0


def _verify(email: str) -> int:
    path = accounts.database_path()
    if path is None or not path.is_file():
        print("Accounts are not enabled here, or ACCOUNTS_DB does not point at the real file.", file=sys.stderr)
        return 2
    try:
        changed = accounts.mark_verified(email)
    except accounts.AccountError as exc:
        print(f"Not verified: {exc.message}", file=sys.stderr)
        return 2
    print(f"{accounts.normalize_email(email)} is {'now' if changed else 'already'} verified.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m api.account_admin",
        description="Operator commands for accounts. Run in the deployment's own shell.")
    commands = parser.add_subparsers(dest="command", required=True)
    reset = commands.add_parser(
        "reset-password",
        help="Set a new random password for an account and end its sessions.")
    reset.add_argument("email", help="The account's email address.")
    verify = commands.add_parser("verify", help="Mark an account's email address as verified without a link.")
    verify.add_argument("email", help="The account's email address.")
    args = parser.parse_args(argv)
    return _verify(args.email) if args.command == "verify" else _reset_password(args.email)


if __name__ == "__main__":
    raise SystemExit(main())
