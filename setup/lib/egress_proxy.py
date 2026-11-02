#!/usr/bin/env python3
"""Explicit HTTP forward proxy. ACL is CONNECT host+port, or the absolute
request target for cleartext HTTP. No TLS intercept.
"""

import os
import select
import socket
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import egress  # noqa: E402

use_connect_target = True  # connect-target-acl
follow_redirects = False  # redirect-recheck
ADMIN_HOST = "127.0.0.1"  # proxy-admin-local
FORWARD_PORT = 3128
ADMIN_PORT = 3129


def split_authority(target, default_port):
    text = target.strip()
    if text.startswith("["):
        end = text.find("]")
        host = text[1:end] if end > 0 else text
        port = default_port
        if end > 0 and text[end + 1 :].startswith(":"):
            port = int(text[end + 2 :])
        return host, port
    if text.count(":") == 1:
        host, port_text = text.rsplit(":", 1)
        if port_text.isdigit():
            return host, int(port_text)
    return text, default_port


def parse_absolute(target):
    raw = target
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    slash = raw.find("/")
    authority = raw if slash < 0 else raw[:slash]
    path = "/" if slash < 0 else raw[slash:]
    host, port = split_authority(authority, 80)
    return host, port, path, target


def header_map(lines):
    headers = {}
    for line in lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def send_denied(conn):
    body = b"DENIED"
    conn.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 6\r\nConnection: close\r\n\r\n" + body)


def deny(conn, keel, role, host, port, reason, raw_url=""):
    try:
        egress.log_denial(keel, role, host, port, reason, raw_url)
    except OSError:
        pass
    try:
        send_denied(conn)
    except OSError:
        pass


def tunnel(client, remote):
    sockets = [client, remote]
    try:
        while True:
            readable, _, _ = select.select(sockets, [], [], 30)
            if not readable:
                break
            for sock in readable:
                other = remote if sock is client else client
                data = sock.recv(8192)
                if not data:
                    return
                other.sendall(data)
    except OSError:
        return
    finally:
        for sock in (client, remote):
            try:
                sock.close()
            except OSError:
                pass


def open_origin(host, port):
    return socket.create_connection((host, port), timeout=10)


def fetch_origin(host, port, method, path, headers, body):
    remote = open_origin(host, port)
    request = "{0} {1} HTTP/1.1\r\nHost: {2}\r\nConnection: close\r\n".format(method, path, host)
    for key, value in headers.items():
        if key in ("proxy-connection", "connection", "host"):
            continue
        request += "{0}: {1}\r\n".format(key, value)
    remote.sendall(request.encode("iso-8859-1") + b"\r\n" + body)
    data = b""
    while True:
        chunk = remote.recv(8192)
        if not chunk:
            break
        data += chunk
    remote.close()
    return data


def location_of(response):
    head = response.split(b"\r\n\r\n", 1)[0].decode("iso-8859-1", "replace")
    for line in head.split("\r\n"):
        if line.lower().startswith("location:"):
            return line.split(":", 1)[1].strip()
    return ""


def handle_client(conn, entries, keel, role):
    try:
        data = b""
        conn.settimeout(10)
        while b"\r\n\r\n" not in data and len(data) < 16384:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
        if b"\r\n\r\n" not in data:
            conn.close()
            return
        head, _, rest = data.partition(b"\r\n\r\n")
        lines = head.decode("iso-8859-1", "replace").split("\r\n")
        if not lines or " " not in lines[0]:
            conn.close()
            return
        parts = lines[0].split(" ")
        method, target = parts[0].upper(), parts[1]
        headers = header_map(lines[1:])
        if method == "CONNECT":
            host, port = split_authority(target, 443)
            acl_host, acl_port = host, port
            if not use_connect_target and "host" in headers:
                acl_host, acl_port = split_authority(headers["host"], port)
                host, port = acl_host, acl_port
            try:
                allowed = egress.destination_allowed(entries, acl_host, acl_port, "connect")
            except egress.ProfileError:
                allowed = False
            if not allowed:
                deny(conn, keel, role, host, port, "not_allowlisted", target)
                conn.close()
                return
            try:
                remote = open_origin(host, port)
            except OSError:
                deny(conn, keel, role, host, port, "origin_unreachable", target)
                conn.close()
                return
            conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            if rest:
                remote.sendall(rest)
            tunnel(conn, remote)
            return
        host, port, path, raw_url = parse_absolute(target)
        try:
            allowed = egress.destination_allowed(entries, host, port, "http")
        except egress.ProfileError:
            allowed = False
        if not allowed:
            deny(conn, keel, role, host, port, "not_allowlisted", raw_url)
            conn.close()
            return
        try:
            response = fetch_origin(host, port, method, path, headers, rest)
        except OSError:
            deny(conn, keel, role, host, port, "origin_unreachable", raw_url)
            conn.close()
            return
        if follow_redirects:
            hop = 0
            while hop < 3 and response.startswith((b"HTTP/1.1 301", b"HTTP/1.1 302", b"HTTP/1.0 302")):
                loc = location_of(response)
                if not loc:
                    break
                host, port, path, raw_url = parse_absolute(loc)
                try:
                    response = fetch_origin(host, port, "GET", path, {}, b"")
                except OSError:
                    break
                hop += 1
        conn.sendall(response)
        conn.close()
    except OSError:
        try:
            conn.close()
        except OSError:
            pass


def serve_admin():
    server = socket_server(ADMIN_HOST, ADMIN_PORT)

    def admin(conn, _addr):
        try:
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\nConnection: close\r\n\r\nADMIN-OK")
        except OSError:
            pass
        finally:
            conn.close()

    accept_loop(server, admin)


def socket_server(host, port):
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(50)
    return server


def accept_loop(server, handler):
    while True:
        try:
            conn, addr = server.accept()
        except OSError:
            continue
        threading.Thread(target=handler, args=(conn, addr), daemon=True).start()


def main():
    allow_path = os.environ.get("KEEL_ALLOW_FILE", "/allow/developer.allow")
    keel = os.environ.get("KEEL_LOG_ROOT", "/keel")
    role = os.environ.get("KEEL_PROXY_ROLE", "developer")
    entries = egress.load_profile(allow_path)
    threading.Thread(target=serve_admin, daemon=True).start()
    server = socket_server("0.0.0.0", FORWARD_PORT)

    def forward(conn, _addr):
        handle_client(conn, entries, keel, role)

    accept_loop(server, forward)


if __name__ == "__main__":
    main()
