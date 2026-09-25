#!/usr/bin/env bash
# Foreground tunnel. A supervisor/LaunchAgent can keep this command alive.
set -euo pipefail
: "${SSH_TARGET:?Set user@host}" "${SSH_PORT:?}" "${LOCAL_PORT:?}" "${REMOTE_PORT:?}"
for value in "$SSH_PORT" "$LOCAL_PORT" "$REMOTE_PORT"; do
 [[ "$value" =~ ^[1-9][0-9]*$ ]] && ((value <= 65535)) || exit 2
done
[[ "$SSH_TARGET" != -* && "$SSH_TARGET" != *$'\n'* ]] || exit 2
args=(-NT -o BatchMode=yes -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=yes
 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o ConnectTimeout=15)
[[ -z "${SSH_KEY:-}" ]] || args+=(-i "$SSH_KEY")
[[ -z "${SSH_HOST_KEY_ALIAS:-}" ]] || args+=(-o "HostKeyAlias=$SSH_HOST_KEY_ALIAS")
exec ssh "${args[@]}" -L "127.0.0.1:$LOCAL_PORT:127.0.0.1:$REMOTE_PORT" -p "$SSH_PORT" "$SSH_TARGET"
