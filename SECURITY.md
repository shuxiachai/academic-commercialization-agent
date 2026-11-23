# Security policy

## Reporting

Use GitHub's private vulnerability reporting on this repository
(Security tab, "Report a vulnerability"), or email the maintainer at the
address in `pyproject.toml`. Please do not open a public issue for a
vulnerability. You should hear back within a week.

## What a deployment holds, and what it does not

- **API keys.** The operator's own keys live only in the deployment's
  environment. Keys used without an account, or by an account that has
  unticked "Save these keys to my account", are never stored: the browser
  keeps them in session storage for the tab, sends them with each paid
  request, and the worker that runs the operation holds them until it ends.
  An account's keys are otherwise saved with it as one sealed record
  (`api/account_keys.py`): a Fernet token holding the provider, the model
  and both keys, with nothing readable about them in the account database.
  The API returns only the provider, the model and the last four characters
  of each key, never a key.
- **The secret for saved keys** is `ACCOUNT_KEYS_SECRET` where it is set.
  Otherwise a random secret is written once to `<ACCOUNTS_DB>.keys-secret`,
  beside the database. That file is not part of a backup, so a copy of the
  database alone opens nothing, but whoever holds the volume holds both;
  setting the variable keeps the secret off the volume.
- **Accounts** (when `ACCOUNTS_DB` is set): email, a scrypt password hash,
  session tokens stored as SHA-256, and the sealed key record above. An
  account can delete itself from the page, which removes its assessments,
  uploads, receipts and saved keys with it.
- **Runs.** Reports, scorecards, source lists and extracted paper metadata
  are kept under `outputs/` for the retention window and are readable by the
  identity that created them (an access code, an account, or the run id for
  an ownerless bring-your-own-key run).

## Scope

In scope: the FastAPI server (`api/`), the browser client (`web/`), the
pipeline (`src/academic_agent/`) and the container image. Out of scope: the
closed experiment runners under `experiments/`, which are archives and are
not deployed.

## Supported versions

The `main` branch, as deployed. There are no release branches.
