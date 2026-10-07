#!/usr/bin/env python3
"""Serve the Atlas behind HTTP Basic auth — the belt to the encryption's braces.

Encryption (tools/lock_atlas.py) protects the *dataset*: the files on disk are
ciphertext. This protects the *surface*: without the password the server will not
hand out a single byte — not the page, not the stylesheet, not the raw exports.

    python3 tools/serve_locked.py --user windycity --password '…' --port 8000

Then open http://localhost:8000/atlas/ and log in. Nothing is stored: the
password lives in this process's memory only. Use `--password-file` or the
ATLAS_HTTP_PASSWORD environment variable to keep it out of your shell history.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hmac
import http.server
import os
import socketserver
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def make_handler(username: str, password: str, root: str, realm: str):
    expected = "Basic " + base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")

    class AuthHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def _authorized(self) -> bool:
            got = self.headers.get("Authorization", "")
            return hmac.compare_digest(got, expected)

        def _deny(self):
            self.send_response(401)
            self.send_header("WWW-Authenticate", f'Basic realm="{realm}", charset="UTF-8"')
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Password required.\n")

        def do_GET(self):
            if not self._authorized():
                return self._deny()
            return super().do_GET()

        def do_HEAD(self):
            if not self._authorized():
                return self._deny()
            return super().do_HEAD()

        def log_message(self, fmt, *a):  # quieter logs, no credentials ever logged
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % a))

    return AuthHandler


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", default=os.environ.get("ATLAS_HTTP_USER", "windycity"))
    ap.add_argument("--password", default=os.environ.get("ATLAS_HTTP_PASSWORD"))
    ap.add_argument("--password-file")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--dir", default=ROOT, help="directory to serve (default: repository root)")
    ap.add_argument("--realm", default="Paradox Atlas")
    args = ap.parse_args()

    password = args.password
    if not password and args.password_file:
        password = open(args.password_file, encoding="utf-8").read().strip()
    if not password:
        password = getpass.getpass("HTTP password: ")
        if len(password) < 8:
            sys.exit("Refusing: use at least 8 characters.")

    handler = make_handler(args.user, password, os.path.abspath(args.dir), args.realm)
    with Server((args.bind, args.port), handler) as httpd:
        host = "localhost" if args.bind in ("0.0.0.0", "::") else args.bind
        print(f"serving {args.dir} with password auth on http://{host}:{args.port}/  (user: {args.user})")
        print("  · every request needs the password, including data files and exports")
        print("  · Ctrl-C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    main()
