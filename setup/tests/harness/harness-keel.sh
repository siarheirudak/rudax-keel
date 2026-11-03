#!/usr/bin/env bash
# Test-only launcher for the harness suites.
# It classifies the rootless fixture, then runs the real keel.sh command.
# setup/keel.sh itself is unchanged and still classifies the live daemon.
HERE=$(cd "$(dirname "$0")" && pwd -P)
exec bash "$HERE/runtime-stub.sh" --exec -- "$@"
