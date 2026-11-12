#!/usr/bin/env bash
# Put our RustDesk server name and public key into the source just before building.
# Values come from the GitHub repository secrets RENDEZVOUS_SERVER and RS_PUB_KEY,
# so they never appear in the public code.
set -euo pipefail
f=libs/hbb_common/src/config.rs
if [ -z "${RENDEZVOUS_SERVER:-}" ] || [ -z "${RS_PUB_KEY:-}" ]; then
  echo "::error::Repository secrets RENDEZVOUS_SERVER and RS_PUB_KEY must be set (Settings > Secrets and variables > Actions)."
  exit 1
fi
case "$RS_PUB_KEY" in *[!A-Za-z0-9+/=]*) echo "::error::RS_PUB_KEY has unexpected characters"; exit 1;; esac
case "$RENDEZVOUS_SERVER" in *[!A-Za-z0-9.:-]*) echo "::error::RENDEZVOUS_SERVER has unexpected characters"; exit 1;; esac
grep -q '@@RENDEZVOUS_SERVER@@' "$f" || { echo "already injected"; exit 0; }
sed -i.bak -e "s|@@RENDEZVOUS_SERVER@@|${RENDEZVOUS_SERVER}|" -e "s|@@RS_PUB_KEY@@|${RS_PUB_KEY}|" "$f" && rm -f "$f.bak"
echo "Server settings injected."
