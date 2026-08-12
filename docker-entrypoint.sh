#!/bin/sh
# Runs as root (the image no longer sets USER before ENTRYPOINT) so it can
# fix ownership on /app/outputs before dropping to the unprivileged user.
#
# Necessary because a freshly attached platform volume (Railway Volumes,
# and a docker-compose bind mount to a not-yet-created host directory) is
# owned by root regardless of what the image chowned at build time — the
# mount replaces the directory entirely. Re-chowning on every start is
# cheap (non-recursive: only the top-level dir needs to be writable, since
# run subdirectories are created afterward by appuser itself) and idempotent.
set -e
mkdir -p /app/outputs
chown appuser:appuser /app/outputs

# setpriv only switches the effective uid/gid — it does not touch $HOME,
# which stays "/root" (root's own entry) unless reset here. Docker's USER
# instruction used to set this for free; dropping it for the root-then-setpriv
# startup means every path derived from $HOME now needs it set explicitly.
# Left at /root, crewai's own chromadb storage-path resolution tries to
# mkdir /root/.local/share/app as appuser and fails with EACCES on the very
# first import, taking down every endpoint that touches crewai — including
# /health and every pipeline_worker subprocess, since both inherit this
# process's environment.
export HOME=/home/appuser

exec setpriv --reuid=appuser --regid=appuser --clear-groups "$@"
