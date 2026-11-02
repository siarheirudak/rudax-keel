# Egress allow profiles

`setup/keel.sh role developer` joins the internal `keel-egress` network and uses the forward proxy. Every other role, and `proto`, stays on `--network none`.

The proxy listens on port 3128 on that network. Its admin port binds to `127.0.0.1` inside the proxy network namespace only.

`setup/egress/<role>.allow` is one destination per line, `host` or `host:port`. Blank lines and `#` comments are ignored. A glob, a suffix wildcard, or any other malformed token refuses the launch.

Before a match, an ASCII host is lowercased, one trailing dot is removed, and an IDN is converted to punycode. An IP is allowed only when that literal is listed. A line without a port allows port 80 for cleartext HTTP and port 443 for CONNECT. Any other port must be written on the line.

HTTPS is decided from the CONNECT host and port. Cleartext HTTP is decided from the request target host and port. A redirect is checked again on the next request. The proxy does not intercept TLS, so it does not re-read SNI inside an allowed tunnel.

Denials are appended to `$KEEL_ROOT/.keel/logs/egress.jsonl` as the normalized host:port and a reason. The path, query, and userinfo are not written.
