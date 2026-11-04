FROM node:22-alpine
RUN apk add --no-cache git \
  && npm install -g @mariozechner/pi-coding-agent@0.73.1
COPY ancestor-guard.sh /usr/local/bin/keel-ancestor-guard.sh
RUN sh /usr/local/bin/keel-ancestor-guard.sh /
