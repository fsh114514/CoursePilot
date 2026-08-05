#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 -m http.server 8765 --directory test_site &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT INT TERM
sleep 1
open "http://127.0.0.1:8765"
wait "$server_pid"
