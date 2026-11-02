# Egress network policy. Sourced by setup/keel.sh.
# shellcheck shell=bash
net_internal=true  # egress-internal
dns_forward=off  # dns-forward-off
ipv6_off=1  # egress-ipv6-off
egress_fail_closed=1  # egress-fail-closed

egress_names() {
  if [ -n "${KEEL_NS:-}" ]; then
    local ns
    ns=$(printf '%s' "$KEEL_NS" | tr '[:upper:]' '[:lower:]')
    EGRESS_NET="keel-egress-${ns}"
    EGRESS_OUT="keel-out-${ns}"
    PROXY_NAME="keel-proxy-${ns}"
    MOCK_NAME="keel-mock-${ns}"
  else
    EGRESS_NET="keel-egress"
    EGRESS_OUT="keel-out"
    PROXY_NAME="keel-proxy"
    MOCK_NAME="keel-mock"
  fi
}

role_network() {
  case $1 in
    developer) printf '%s\n' egress;;  # developer-egress
    critic) printf '%s\n' none;;  # critic-none
    qa|researcher) printf '%s\n' none;;  # qa-researcher-none
    *) printf '%s\n' none;;
  esac
}

egress_refuse() {
  python3 "$HERE/lib/egress.py" deny --keel "$P" --role "${1:-}" --host "${2:-}" --port "${3:-0}" --reason "$4" >/dev/null 2>&1 || true
  echo "REFUSE	$4	${2:-}	${3:-0}"
  return 1
}

egress_network_create() {
  local name=$1 internal=$2
  if $DOCKER network inspect "$name" >/dev/null 2>&1; then
    return 0
  fi
  if [ "$internal" = true ]; then
    $DOCKER network create --internal --ipv6=false "$name" >/dev/null
  else
    $DOCKER network create --ipv6=false "$name" >/dev/null
  fi
}

egress_proxy_up() {
  egress_names
  local want_internal=false
  if [ "$net_internal" = true ] && [ "$dns_forward" = off ]; then
    want_internal=true
  fi
  if $DOCKER network inspect "$EGRESS_NET" >/dev/null 2>&1; then
    local got
    got=$($DOCKER network inspect -f '{{.Internal}}' "$EGRESS_NET" 2>/dev/null || echo missing)
    if [ "$egress_fail_closed" = 1 ] && [ "$got" != "$want_internal" ]; then
      egress_refuse developer "" 0 egress_network
      return 1
    fi
  else
    egress_network_create "$EGRESS_NET" "$want_internal" || { egress_refuse developer "" 0 egress_network; return 1; }
  fi
  if ! $DOCKER network inspect "$EGRESS_OUT" >/dev/null 2>&1; then
    egress_network_create "$EGRESS_OUT" false || { egress_refuse developer "" 0 egress_network; return 1; }
  fi
  mkdir -p "$P/.keel/logs"
  if [ "$($DOCKER inspect -f '{{.State.Running}}' "$MOCK_NAME" 2>/dev/null || echo false)" != true ]; then
    $DOCKER rm -f "$MOCK_NAME" >/dev/null 2>&1 || true
    $DOCKER run -d --name "$MOCK_NAME" --network "$EGRESS_NET" --network-alias keel-mock --network-alias keel-secret \
      -v "$HERE/lib/mock_model.py:/keel/mock_model.py:ro" \
      keel-proxy python3 /keel/mock_model.py >/dev/null || { egress_refuse developer "" 0 egress_proxy; return 1; }
  fi
  proxy_state=$($DOCKER inspect -f '{{.State.Running}}' "$PROXY_NAME" 2>/dev/null || echo missing)
  if [ "$proxy_state" = false ] && [ "$egress_fail_closed" = 1 ]; then
    egress_refuse developer "" 0 egress_proxy
    return 1
  fi
  if [ "$proxy_state" != true ]; then
    $DOCKER rm -f "$PROXY_NAME" >/dev/null 2>&1 || true
    $DOCKER run -d --name "$PROXY_NAME" --network "$EGRESS_NET" --network-alias keel-proxy \
      -e KEEL_ALLOW_FILE=/allow/developer.allow -e KEEL_LOG_ROOT=/keel-log -e KEEL_EGRESS_LOG=/keel-log/egress.jsonl -e KEEL_PROXY_ROLE=developer \
      -v "$HERE/egress/developer.allow:/allow/developer.allow:ro" \
      -v "$HERE/lib/egress.py:/keel/egress.py:ro" \
      -v "$HERE/lib/egress_proxy.py:/keel/egress_proxy.py:ro" \
      -v "$P/.keel/logs:/keel-log" \
      keel-proxy python3 /keel/egress_proxy.py >/dev/null || { egress_refuse developer "" 0 egress_proxy; return 1; }
    $DOCKER network connect "$EGRESS_OUT" "$PROXY_NAME" >/dev/null 2>&1 || true
  fi
  if [ "$egress_fail_closed" = 1 ] && [ "$($DOCKER inspect -f '{{.State.Running}}' "$PROXY_NAME" 2>/dev/null || echo false)" != true ]; then
    egress_refuse developer "" 0 egress_proxy
    return 1
  fi
  return 0
}

crun_for() {
  local role=$1
  shift
  local mode
  mode=$(role_network "$role")
  if [ "$mode" = none ]; then
    crun "$@"
    return $?
  fi
  if [ "$mode" = egress ]; then
    if ! python3 "$HERE/lib/egress.py" check --harness "$HERE" --role "$role" >/dev/null; then
      python3 "$HERE/lib/egress.py" deny --keel "$P" --role "$role" --host "" --port 0 --reason malformed_profile >/dev/null 2>&1 || true
      python3 "$HERE/lib/egress.py" check --harness "$HERE" --role "$role"
      return 1
    fi
    egress_proxy_up || return $?
    local a skip=0 args=()
    for a in "${HARDEN[@]}"; do
      if [ "$skip" = 1 ]; then skip=0; continue; fi
      if [ "$a" = "--network" ]; then skip=1; continue; fi
      args+=("$a")
    done
    # The user-defined network resolver is already 127.0.0.11. Do not pass
    # --dns 127.0.0.11: that value becomes the upstream and the lookup loops.
    args+=(--network "$EGRESS_NET")
    if [ "$ipv6_off" = 1 ]; then
      args+=(--sysctl net.ipv6.conf.all.disable_ipv6=1)
    fi
    args+=(-e HTTP_PROXY=http://keel-proxy:3128 -e HTTPS_PROXY=http://keel-proxy:3128)
    args+=(-e http_proxy=http://keel-proxy:3128 -e https_proxy=http://keel-proxy:3128)
    $DOCKER run "${args[@]}" "${GITENV[@]}" "$@"  # role-env-explicit
    return $?
  fi
  # open: default bridge, no explicit network (mutant)
  local a skip=0 args=()
  for a in "${HARDEN[@]}"; do
    if [ "$skip" = 1 ]; then skip=0; continue; fi
    if [ "$a" = "--network" ]; then skip=1; continue; fi
    args+=("$a")
  done
  $DOCKER run "${args[@]}" "${GITENV[@]}" "$@"
}
