#!/bin/bash
# Root-only source materializer installation. Does not enable/start a publisher.
set -euo pipefail
[ "$(id -u)" = 0 ] || exit 1
source_code=$(cd -- "$(dirname -- "$0")" && pwd)
[ -x /opt/leaselab-publisher-executor/venv/bin/python ] || exit 1
getent passwd leaselab-source-fetch >/dev/null || useradd --system --user-group --no-create-home --home-dir /var/lib/leaselab-publisher/source-fetch --shell /usr/sbin/nologin leaselab-source-fetch
usermod -a -G leaselab-github-clients leaselab-source-fetch
install -d -o leaselab-source-fetch -g leaselab-source-fetch -m 700 /var/lib/leaselab-publisher/source-fetch
/opt/leaselab-publisher-executor/venv/bin/pip -q install 'httpx2[http2,brotli,zstd]==2.13.0'
for file in "$source_code"/source*.py; do
 install -o root -g root -m 644 "$file" /usr/local/libexec/leaselab-company/publisher/
done
# Deploy the matching broker policy/client code separately and restart its existing unit.
# This script neither copies App keys nor changes existing role/group memberships.
