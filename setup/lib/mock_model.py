#!/usr/bin/env python3
"""Local stand-in for a model API. Speaks cleartext HTTP only."""

import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        if host == "keel-secret":
            body = b"SECRET-BODY"
            self.send_response(200)
        elif self.path.startswith("/redir"):
            self.send_response(302)
            self.send_header("Location", "http://keel-secret/hidden?x=1")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        else:
            body = b"MOCK-OK"
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


def accept_sink(port):
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", port))
    server.listen(20)
    while True:
        try:
            conn, _addr = server.accept()
        except OSError:
            continue
        try:
            conn.recv(64)
        except OSError:
            pass
        try:
            conn.close()
        except OSError:
            pass


def main():
    # Ports the allowlist must refuse. A TCP accept is enough for the proxy
    # to report Connection Established when a mutant skips the port check.
    threading.Thread(target=accept_sink, args=(22,), daemon=True).start()
    threading.Thread(target=accept_sink, args=(443,), daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()


if __name__ == "__main__":
    main()
