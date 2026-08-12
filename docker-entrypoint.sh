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
exec setpriv --reuid=appuser --regid=appuser --clear-groups "$@"
