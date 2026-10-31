# Security policy

## Reporting

Use GitHub's private vulnerability reporting on this repository
(Security tab, "Report a vulnerability"), or email the maintainer at the
address in `pyproject.toml`. Please do not open a public issue for a
vulnerability. You should hear back within a week.

## What a deployment holds, and what it does not

- **API keys.** A deployment never stores a visitor's or an account's LLM or
  search keys. Bring-your-own-key requests carry them per request; the
  browser keeps them in session storage for the tab. The operator's own keys
  live only in the deployment's environment.
- **Accounts** (when `ACCOUNTS_DB` is set): email, a scrypt password hash
  and session tokens stored as SHA-256. No key material.
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
