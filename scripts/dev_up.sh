#!/usr/bin/env bash
#
# One-click local dev for Cutagent.
#
#   scripts/dev_up.sh [up]        start infra, bootstrap DB, then API + worker + web (idempotent)
#   scripts/dev_up.sh down        stop the API + worker + web app processes (infra stays up)
#   scripts/dev_up.sh down --infra also `docker compose down` the infra (data volumes kept)
#   scripts/dev_up.sh restart     down (app only) then up
#   scripts/dev_up.sh status      show infra + app process / port status
#   scripts/dev_up.sh logs [name] tail a component log (api|worker|web)
#
# Config (env file): CUTAGENT_ENV_FILE, else <repo>/.env.local (template: .env.example).
# Overridable: CUTAGENT_API_PORT (8000), CUTAGENT_WEB_PORT (8001), CUTAGENT_VENV.
# Public dev proxy: CUTAGENT_TUNNEL_ENABLE=auto|1|0, CUTAGENT_TUNNEL_HOST=shuying-tunnel.
#
set -euo pipefail

# Non-login SSH sessions on macOS often miss Homebrew/Docker CLI paths. Keep
# this script self-contained so Mac mini restarts do not depend on shell init.
export PATH="/opt/homebrew/bin:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"

# ── paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

ENV_FILE="${CUTAGENT_ENV_FILE:-$ROOT/.env.local}"
API_HOST=127.0.0.1
API_PORT="${CUTAGENT_API_PORT:-8000}"
# dev.shuying.cyou serves the web UI as static assets from the Singapore ECS.
# Only /api and /ws are reverse-proxied through the Mac mini API tunnel.
WEB_PORT="${CUTAGENT_WEB_PORT:-8001}"
RUN_DIR="$ROOT/.data/dev"
INFRA_SERVICES=(postgres redis minio temporal temporal-ui)
TUNNEL_ENABLE="${CUTAGENT_TUNNEL_ENABLE:-auto}"
TUNNEL_HOST="${CUTAGENT_TUNNEL_HOST:-shuying-tunnel}"
TUNNEL_REMOTE_HOST="${CUTAGENT_TUNNEL_REMOTE_HOST:-127.0.0.1}"
TUNNEL_REMOTE_API_PORT="${CUTAGENT_TUNNEL_REMOTE_API_PORT:-18000}"
TUNNEL_CONNECT_TIMEOUT="${CUTAGENT_TUNNEL_CONNECT_TIMEOUT:-5}"

# Infra is owned by the main checkout's compose project. Pin its name + file so
# running from a worktree reuses the existing containers instead of spinning up
# a duplicate set (which would collide on :55432 / :7233 / :9000).
COMPOSE_DIR="${ROOT%/.claude/worktrees/*}"
COMPOSE_PROJECT="$(basename "$COMPOSE_DIR")"

# venv: prefer this checkout's .venv, else the main checkout's (worktrees share it).
VENV="${CUTAGENT_VENV:-}"
if [[ -z "$VENV" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    VENV="$ROOT/.venv"
  else
    VENV="${ROOT%/.claude/worktrees/*}/.venv"
  fi
fi
PY="$VENV/bin/python"

# ── pretty logging ─────────────────────────────────────────────────────────
c() { printf '\033[%sm' "$1"; }
log()  { printf '%s▸%s %s\n'  "$(c '1;34')" "$(c 0)" "$*"; }
ok()   { printf '%s✓%s %s\n'  "$(c '1;32')" "$(c 0)" "$*"; }
warn() { printf '%s!%s %s\n'  "$(c '1;33')" "$(c 0)" "$*"; }
die()  { printf '%s✗%s %s\n'  "$(c '1;31')" "$(c 0)" "$*" >&2; exit 1; }

# ── helpers ────────────────────────────────────────────────────────────────
compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_DIR/docker-compose.yml" "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_DIR/docker-compose.yml" "$@"
  else die "docker compose not found"; fi
}

tcp_up()  { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && exec 3>&- 2>/dev/null; }
http_code() { curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$1" 2>/dev/null || echo 000; }

tunnel_enabled() {
  local mode
  mode="$(printf '%s' "$TUNNEL_ENABLE" | tr '[:upper:]' '[:lower:]')"
  case "$mode" in
    0|false|no|off) return 1 ;;
    1|true|yes|on) return 0 ;;
    auto|"")
      command -v ssh >/dev/null 2>&1 || return 1
      ssh -o BatchMode=yes -o ConnectTimeout="$TUNNEL_CONNECT_TIMEOUT" "$TUNNEL_HOST" true >/dev/null 2>&1
      ;;
    *) die "invalid CUTAGENT_TUNNEL_ENABLE=$TUNNEL_ENABLE (use auto|1|0)" ;;
  esac
}

tunnel_remote_health() {
  ssh -o BatchMode=yes -o ConnectTimeout="$TUNNEL_CONNECT_TIMEOUT" "$TUNNEL_HOST" \
    "curl -fsS -o /dev/null --max-time 5 http://$TUNNEL_REMOTE_HOST:$TUNNEL_REMOTE_API_PORT/api/health" \
    >/dev/null 2>&1
}

tunnel_clear_remote_forward() {
  # The cutagent-tunnel account is dedicated to this reverse tunnel. When an SSH
  # remote-forward dies half-open, ECS can keep a stale `sshd: cutagent-tunnel`
  # listener on :18000 while the Mac has no local pidfile left. Kill only that
  # non-command sshd session; the current remote command appears as @notty.
  ssh -o BatchMode=yes -o ConnectTimeout="$TUNNEL_CONNECT_TIMEOUT" "$TUNNEL_HOST" \
    "ps -u \"\$USER\" -o pid=,args= | awk '\$0 ~ /sshd: / && \$0 !~ /@notty/ {print \$1}' | xargs -r kill" \
    >/dev/null 2>&1 || true
}

# Readiness probes (named functions so wait_for can call them in-process — a
# `bash -c` subshell would not see these shell functions).
minio_up() { [[ "$(http_code http://127.0.0.1:9000/minio/health/live)" == 200 ]]; }
# Require a real 200 from /openapi.json — not merely "!= 000": WSL's localhost
# relay can return a transient 502 after a listener dies, which would otherwise
# read as "up" and make the script skip a down API.
api_up()   { [[ "$(http_code "http://$API_HOST:$API_PORT/openapi.json")" == 200 ]]; }
web_up()   { tcp_up "$WEB_PORT"; }

wait_for() { # wait_for <name> <check-cmd...>  (check returns 0 when ready)
  local name="$1"; shift
  for _ in $(seq 1 60); do "$@" && { ok "$name ready"; return 0; }; sleep 1; done
  die "$name did not become ready in 60s"
}

pidfile() { echo "$RUN_DIR/$1.pid"; }
logfile() { echo "$RUN_DIR/$1.log"; }

proc_alive() { # proc_alive <name> → 0 if the recorded pid is running
  local f; f="$(pidfile "$1")"
  [[ -f "$f" ]] && kill -0 "$(cat "$f")" 2>/dev/null
}

start_bg() { # start_bg <name> <cmd...>   (own process group so we can kill the tree)
  local name="$1"; shift
  if command -v setsid >/dev/null 2>&1; then
    setsid bash -c 'exec "$@"' _ "$@" >"$(logfile "$name")" 2>&1 &
  else
    nohup bash -c 'exec "$@"' _ "$@" >"$(logfile "$name")" 2>&1 &
  fi
  echo $! >"$(pidfile "$name")"
}

ensure_tunnel() {
  if ! tunnel_enabled; then
    warn "shuying tunnel unavailable/disabled — skipping public /api tunnel"
    return 0
  fi
  if tunnel_remote_health; then
    ok "shuying tunnel healthy (:${TUNNEL_REMOTE_API_PORT} → :${API_PORT})"
    return 0
  fi

  warn "shuying tunnel unhealthy — restarting remote forward"
  stop_named tunnel
  tunnel_clear_remote_forward
  start_bg tunnel ssh -N -T \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=15 \
    -o ServerAliveCountMax=4 \
    -R "$TUNNEL_REMOTE_HOST:$TUNNEL_REMOTE_API_PORT:$API_HOST:$API_PORT" \
    "$TUNNEL_HOST"
  wait_for "shuying tunnel :$TUNNEL_REMOTE_API_PORT" tunnel_remote_health
}

stop_named() { # stop_named <name>  (kills the whole process group)
  local f; f="$(pidfile "$1")"
  [[ -f "$f" ]] || { return 0; }
  local pid; pid="$(cat "$f")"
  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    for _ in $(seq 1 10); do kill -0 "$pid" 2>/dev/null || break; sleep 0.3; done
    kill -KILL -- "-$pid" 2>/dev/null || true
    ok "stopped $1 (pid $pid)"
  fi
  rm -f "$f"
}

load_env() {
  [[ -f "$ENV_FILE" ]] || die "env file not found: $ENV_FILE  (copy/adapt .env.example → .env.local)"
  [[ -x "$PY" ]] || die "python venv not found: $PY  (set CUTAGENT_VENV or create .venv)"
  set -a; # shellcheck disable=SC1090
  source "$ENV_FILE"; set +a
  export PYTHONPATH="$ROOT"
}

# ── commands ───────────────────────────────────────────────────────────────
cmd_up() {
  mkdir -p "$RUN_DIR"
  load_env
  log "repo:   $ROOT"
  log "venv:   $VENV"
  log "env:    $ENV_FILE"

  # 1. infra (docker compose)
  log "starting infra: ${INFRA_SERVICES[*]}"
  compose up -d "${INFRA_SERVICES[@]}"
  wait_for "postgres :55432" tcp_up 55432
  wait_for "temporal :7233"  tcp_up 7233
  wait_for "minio :9000"     minio_up

  # 2. Database schema + seed data. This is idempotent and keeps a fresh checkout
  # one-command: API startup only connects/seeds, it does not run Alembic.
  log "bootstrapping database"
  "$PY" scripts/bootstrap_database.py

  # 3. API
  if api_up; then
    warn "API already up on :$API_PORT — skipping (use 'restart' to recycle)"
  else
    log "starting API on :$API_PORT"
    start_bg api "$PY" -m uvicorn apps.api.main:app --host "$API_HOST" --port "$API_PORT"
    wait_for "API :$API_PORT" api_up
  fi
  ensure_tunnel

  # 4. worker (no port; track by pid)
  if proc_alive worker; then
    warn "worker already running (pid $(cat "$(pidfile worker)")) — skipping"
  else
    log "starting worker (queue: cutagent-production)"
    start_bg worker "$PY" -m apps.worker
    sleep 2
    proc_alive worker && ok "worker started (pid $(cat "$(pidfile worker)"))" || die "worker exited — see $(logfile worker)"
  fi

  # 5. web (vite dev)
  if tcp_up "$WEB_PORT"; then
    warn "web already up on :$WEB_PORT — skipping"
  else
    log "starting web on :$WEB_PORT"
    # vite resolves its root/config from the cwd → must run inside apps/web,
    # not the repo root (where API + worker correctly run).
    start_bg web bash -lc "cd '$ROOT/apps/web' && exec node_modules/.bin/vite --host '$API_HOST' --port '$WEB_PORT' --strictPort"
    wait_for "web :$WEB_PORT" tcp_up "$WEB_PORT"
  fi

  echo
  ok "all up"
  printf '   web        http://127.0.0.1:%s\n' "$WEB_PORT"
  printf '   api        http://127.0.0.1:%s   (openapi.json / proxied from web)\n' "$API_PORT"
  printf '   temporal   http://127.0.0.1:8080 (UI)   ·   minio  http://127.0.0.1:9001\n'
  printf '   logs       %s/{api,worker,web}.log\n' "$RUN_DIR"
}

cmd_down() {
  stop_named tunnel
  stop_named web
  stop_named worker
  stop_named api
  if [[ "${1:-}" == "--infra" ]]; then
    log "stopping infra (data volumes kept)"
    compose down
    ok "infra stopped"
  else
    log "infra left running — 'down --infra' to also stop docker"
  fi
}

cmd_status() {
  log "infra (docker compose):"; compose ps 2>/dev/null || warn "compose unavailable"
  echo
  log "app processes:"
  for n in api worker web; do
    if proc_alive "$n"; then ok "$n  pid $(cat "$(pidfile "$n")")"; else warn "$n  not running"; fi
  done
  echo
  log "ports:"
  printf '   api  :%s → %s\n' "$API_PORT" "$(http_code "http://$API_HOST:$API_PORT/openapi.json")"
  printf '   web  :%s → %s\n' "$WEB_PORT" "$(tcp_up "$WEB_PORT" && echo up || echo down)"
  if tunnel_enabled; then
    printf '   tunnel %s:%s → %s\n' "$TUNNEL_REMOTE_HOST" "$TUNNEL_REMOTE_API_PORT" "$(tunnel_remote_health && echo healthy || echo down)"
  else
    printf '   tunnel %s → unavailable/disabled\n' "$TUNNEL_HOST"
  fi
}

cmd_logs() {
  local name="${1:-api}"
  local f; f="$(logfile "$name")"
  [[ -f "$f" ]] || die "no log for '$name' (api|worker|web)"
  tail -n 60 -f "$f"
}

case "${1:-up}" in
  up)      cmd_up ;;
  down)    shift || true; cmd_down "${1:-}" ;;
  restart) cmd_down; cmd_up ;;
  status)  cmd_status ;;
  logs)    shift || true; cmd_logs "${1:-api}" ;;
  *)       die "usage: $0 [up|down [--infra]|restart|status|logs [api|worker|web]]" ;;
esac
