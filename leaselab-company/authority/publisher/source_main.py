#!/usr/bin/python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic==2.12.5", "httpx2[http2,brotli,zstd]"]
# ///
# How to run: trusted root supervisor invokes this as leaselab-source-fetch.
"""Only exact H/B JSON is accepted; credentials and HTTP errors never go to output."""
import hashlib
import json
import os
import sys
import tarfile
from pathlib import Path

import httpx2
from publisher_models import Denied, unique_keys
from source_archive import export
from source_fetch import GitHub, client, credential
from source_models import Pair


def main() -> None:
    if len(sys.argv) != 2 or len(sys.argv[1]) > 200:
        raise Denied
    pair = Pair.model_validate_json(sys.argv[1])
    json.loads(sys.argv[1], object_pairs_hook=unique_keys)
    token = credential()
    destination = Path('/var/lib/leaselab-publisher/source-fetch') / hashlib.sha256(pair.model_dump_json().encode()).hexdigest()
    destination.mkdir(mode=0o700)
    with client() as transport:
        remote = GitHub(transport, token)
        for name, sha in (('head', pair.head), ('base', pair.base)):
            tree = remote.tree(sha)
            _ = export(remote.archive(sha), tree, destination / name)
            with (destination / (name + '.tree.json')).open('x') as output:
                _ = output.write(tree.model_dump_json())
                output.flush()
                os.fsync(output.fileno())
            (destination / (name + '.tree.json')).chmod(0o400)
    with (destination / 'pair.json').open('x') as output:
        _ = output.write(pair.model_dump_json())
        output.flush()
        os.fsync(output.fileno())
    (destination / 'pair.json').chmod(0o400)
    print('SOURCE_FETCH_VERIFIED')


if __name__ == '__main__':
    try:
        main()
    except (Denied, OSError, ValueError, KeyError, tarfile.TarError, httpx2.HTTPError):
        print('SOURCE_FETCH_DENIED', file=sys.stderr)
        raise SystemExit(1) from None
