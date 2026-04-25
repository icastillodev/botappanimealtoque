#!/usr/bin/env bash
# Actualiza desde Git, instala dependencias y reinicia el bot en ESTE entorno (PID en .run/bot.pid).
# Pensado para el servidor o la copia desplegada del repo — no sustituye "python main.py" en localhost para dev.
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

_is_windows() {
  [[ "${OS:-}" == "Windows_NT" ]] || [[ "$(uname -s 2>/dev/null || true)" =~ (MINGW|MSYS|CYGWIN) ]]
}

# Si no hay venv en Linux/macOS, crear .venv (evita ModuleNotFoundError: discord con python del sistema)
_pick_system_python() {
  # Preferimos 3.12 (por wheels de aiohttp y friends). En Windows, usamos py launcher si está.
  if _is_windows && command -v py >/dev/null 2>&1; then
    if py -3.12 -c "import sys; print(sys.version)" >/dev/null 2>&1; then
      echo "py -3.12"
      return
    fi
    echo "py -3"
    return
  fi
  if command -v python3.12 >/dev/null 2>&1; then
    command -v python3.12
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    command -v python
  fi
}

_venv_python() {
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    echo "$ROOT/.venv/bin/python"
  elif [[ -f "$ROOT/.venv/Scripts/python.exe" ]]; then
    echo "$ROOT/.venv/Scripts/python.exe"
  else
    echo ""
  fi
}

SYS_PY="$(_pick_system_python)"
VENV_PY="$(_venv_python)"

if [[ -z "$VENV_PY" ]]; then
  echo "==> No existe .venv — creando venv con: $SYS_PY -m venv .venv"
  $SYS_PY -m venv "$ROOT/.venv"
  VENV_PY="$(_venv_python)"
fi

_pick_python() {
  # Siempre preferimos el venv del repo.
  if [[ -n "${VENV_PY:-}" ]]; then
    echo "$VENV_PY"
    return
  fi
  echo "$SYS_PY"
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
  "$PY" -m pip install --upgrade pip
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
sleep 1
if kill -0 "$new_pid" 2>/dev/null; then
  echo "    Seguimiento: tail -f \"$LOG_FILE\""
else
  echo "==> El bot no quedó corriendo. Últimas 80 líneas del log:"
  tail -n 80 "$LOG_FILE" || true
  exit 1
fi
