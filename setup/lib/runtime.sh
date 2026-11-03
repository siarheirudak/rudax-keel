#!/usr/bin/env bash
# Classify the container runtime, check free space, and refuse sandbox-off Chromium argv.
# A fixture file is accepted only as --info-file. Nothing here reads a fixture from the environment.
# shellcheck shell=bash
rootless_token=0 # rootless-token
userns_is_rootless=0 # userns-not-rootless
launch_refuse=1 # runtime-refuse
disk_gate=1 # disk-gate
# 512 MiB. Our choice for the soft free-space check. Not a task-capacity claim.
KEEL_WORK_MIN_FREE=${KEEL_WORK_MIN_FREE:-536870912}

keel_runtime_fields() {
  local info_file=$1
  if [ -n "$info_file" ]; then
    RT_SEC=$(sed -n 's/^security_options=//p' "$info_file" | head -1)
    RT_OS=$(sed -n 's/^operating_system=//p' "$info_file" | head -1)
    RT_PODMAN=$(sed -n 's/^podman_rootless=//p' "$info_file" | head -1)
    return 0
  fi
  local raw dcli
  dcli=${DOCKER:-docker}
  dcli=${dcli##* }
  raw=$($dcli info --format '{{json .SecurityOptions}}|{{.OperatingSystem}}' 2>/dev/null) || return 1
  RT_SEC=${raw%%|*}
  RT_OS=${raw#*|}
  RT_PODMAN=
  if [ "$dcli" = podman ]; then
    RT_PODMAN=$(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null || true)
  fi
}

keel_has_option() {
  local blob=$1 name=$2
  case $blob in
    *"name=${name}"*|*"name=${name}\""*|*"name=${name},"*) return 0;;
  esac
  return 1
}

keel_classify_runtime() {
  local info_file="" saw userns
  while [ $# -gt 0 ]; do
    case $1 in
      --info-file)
        info_file=${2:-}
        shift 2
        ;;
      *)
        echo "unknown" >&2
        return 2
        ;;
    esac
  done
  RT_SEC='' RT_OS='' RT_PODMAN=''
  keel_runtime_fields "$info_file" || { printf '%s\n' unknown; return 1; }
  saw=$rootless_token
  userns=0
  if keel_has_option "$RT_SEC" rootless; then saw=1; fi
  if keel_has_option "$RT_SEC" userns; then userns=1; fi
  if [ "$userns_is_rootless" = 1 ] && [ "$userns" = 1 ]; then saw=1; fi
  if [ "$RT_PODMAN" = true ]; then printf '%s\n' podman-rootless; return 0; fi
  if [ "$RT_PODMAN" = false ]; then printf '%s\n' podman-rootful; return 1; fi
  case $RT_OS in
    *[Dd]ocker\ [Dd]esktop*)
      if [ "$(uname -s)" = Darwin ]; then printf '%s\n' desktop; return 0; fi
      printf '%s\n' desktop-linux
      return 2
      ;;
  esac
  if [ "$saw" = 1 ]; then printf '%s\n' rootless; return 0; fi
  printf '%s\n' rootful
  return 1
}

keel_free_bytes() {
  local path=$1
  while [ ! -d "$path" ]; do path=$(dirname "$path"); done
  df -Pk "$path" | awk 'NR==2 { print $4 * 1024 }'
}

keel_disk_ok() {
  local path=$1 bytes
  if [ "$disk_gate" != 1 ]; then return 0; fi
  bytes=$(keel_free_bytes "$path")
  [ -n "$bytes" ] || return 1
  [ "$bytes" -ge "$KEEL_WORK_MIN_FREE" ]
}

keel_require_runtime() {
  local cls ec=0
  if ! keel_disk_ok "${KEEL_ROOT:-$HOME}"; then
    printf 'REFUSE\truntime\tdisk\t0\n'
    return 1
  fi
  if [ "$launch_refuse" != 1 ]; then
    return 0
  fi
  cls=$(keel_classify_runtime "$@") || ec=$?
  if [ "$ec" -eq 1 ]; then
    printf 'REFUSE\truntime\t%s\t0\n' "$cls"
    return 1
  fi
  return 0
}

sandbox_flags=1 # chromium-sandbox
keel_chromium_argv() {
  local arg
  if [ "$sandbox_flags" = 1 ]; then
    for arg in "$@"; do
      case $arg in
        --no-sandbox|--disable-setuid-sandbox)
          printf 'REFUSE\tchromium\tsandbox\t0\n'
          return 1
          ;;
      esac
    done
  fi
  return 0
}
