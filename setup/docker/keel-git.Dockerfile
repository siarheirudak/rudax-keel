FROM alpine:3.20
RUN apk add --no-cache git
COPY ancestor-guard.sh /usr/local/bin/keel-ancestor-guard.sh
RUN sh /usr/local/bin/keel-ancestor-guard.sh /
