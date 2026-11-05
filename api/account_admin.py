"""Operator commands for accounts, run from the deployment's own shell.

    python -m api.account_admin reset-password someone@example.com

There is no password reset by email yet: that needs an email service, which
is a separate decision. Until then a person who forgets their password has
exactly one way back, and it is this command, run by the operator.

It is deliberately not an HTTP route. Whoever can run it already has a shell
on the machine that holds the account database, so it grants nothing that
shell did not already give; a route would have to be protected by a secret
that is one more thing to leak.

The new password is generated here rather than typed, so it never appears in
a shell history or a process list, and it is printed once. Nothing else
keeps it: the database stores only its hash.

Registration verifies no email address, so the operator is the check that the
person asking owns the account. Send the new password to the account's own
address, not to whichever address the request came from.
"""
from __future__ import annotations

import argparse
import secrets
import sys

from api import accounts

# 18 random bytes, 24 URL-safe characters: far above the password policy and
# short enough to read out or paste without wrapping.
_GENERATED_BYTES = 18


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
    password = secrets.token_urlsafe(_GENERATED_BYTES)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m api.account_admin",
        description="Operator commands for accounts. Run in the deployment's own shell.")
    commands = parser.add_subparsers(dest="command", required=True)
    reset = commands.add_parser(
        "reset-password",
        help="Set a new random password for an account and end its sessions.")
    reset.add_argument("email", help="The account's email address.")
    args = parser.parse_args(argv)
    return _reset_password(args.email)


if __name__ == "__main__":
    raise SystemExit(main())
