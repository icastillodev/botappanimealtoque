#!/usr/bin/env bash
# Actualiza desde Git, instala dependencias y reinicia el bot (PID en .run/bot.pid).
# Uso (Git Bash / WSL / Linux):  chmod +x update.sh && ./update.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -d "$ROOT/.git" ]]; then
  echo "ERROR: No hay repositorio Git aquí (falta .git)." >&2
  echo "Esta carpeta no se creó con 'git clone'. Ejemplo en el servidor:" >&2
  echo "  cd ~ && git clone https://github.com/icastillodev/botappanimealtoque.git botdiscord" >&2
  echo "  cp /ruta/vieja/.env ~/botdiscord/.env   # si ya tenías .env" >&2
  echo "  cd ~/botdiscord && bash update.sh" >&2
  exit 1
fi

# Si no hay venv en Linux/macOS, crear .venv (evita ModuleNotFoundError: discord con python del sistema)
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  if [[ ! -d "$ROOT/.venv" ]] && command -v python3 >/dev/null 2>&1; then
    echo "==> No existe .venv — creando con: python3 -m venv .venv"
    python3 -m venv "$ROOT/.venv"
  fi
fi

_pick_python() {
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    echo "$ROOT/.venv/bin/python"
  elif [[ -f "$ROOT/.venv/Scripts/python.exe" ]]; then
    echo "$ROOT/.venv/Scripts/python.exe"
  elif [[ -x "$ROOT/venv/bin/python" ]]; then
    echo "$ROOT/venv/bin/python"
  elif [[ -f "$ROOT/venv/Scripts/python.exe" ]]; then
    echo "$ROOT/venv/Scripts/python.exe"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    command -v python
  fi
}

PY="$(_pick_python)"
RUN_DIR="$ROOT/.run"
mkdir -p "$RUN_DIR"
PID_FILE="$RUN_DIR/bot.pid"
LOG_FILE="$RUN_DIR/bot.log"

echo "==> Repo: $ROOT"
echo "==> Python: $PY"

echo "==> git pull --ff-only"
git pull --ff-only

if [[ -f "$ROOT/requirements.txt" ]]; then
  echo "==> pip install -r requirements.txt (con: $PY)"
  "$PY" -m pip install --upgrade pip -q
  "$PY" -m pip install -r "$ROOT/requirements.txt"
fi

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(tr -d ' \r\n' <"$PID_FILE" || true)"
  if [[ -n "${old_pid:-}" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "==> Deteniendo proceso anterior (PID $old_pid)..."
    kill "$old_pid" 2>/dev/null || true
    sleep 2
    if kill -0 "$old_pid" 2>/dev/null; then
      echo "==> Forzando cierre..."
      kill -9 "$old_pid" 2>/dev/null || true
    fi
  fi
  rm -f "$PID_FILE"
fi

echo "==> Iniciando main.py (log: $LOG_FILE)"
nohup "$PY" "$ROOT/main.py" >>"$LOG_FILE" 2>&1 &
new_pid=$!
echo "$new_pid" >"$PID_FILE"
echo "==> Listo. PID $new_pid"
echo "    Seguimiento: tail -f \"$LOG_FILE\""
