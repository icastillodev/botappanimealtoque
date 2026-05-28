# Checklist backlog — Bot Anime Altoque

**Estado:** ✅ **Completo** (2026-05-28). Pedido original + ideas futuras cerradas o descartadas.

- Historial ítems: [`checklist-finalizados/CHECKLIST-BACKLOG-BOT-2026-05.md`](checklist-finalizados/CHECKLIST-BACKLOG-BOT-2026-05.md)
- Variables Impostor: [`ENV-IMPOSTOR.md`](ENV-IMPOSTOR.md)

---

## Ideas futuras — resueltas en esta ronda

- [x] Revancha: `IMPOSTOR_REMATCH_VOTE_PERCENT` (1–100, default 50)
- [x] Historial: tabla `impostor_game_log` + `/impostor-historial` · `?impostorhistorial`
- [x] `IMPOSTOR_DB_PATH` documentado como obsoleto (borrar del `.env`)
- [x] Tests: `tests/test_impostor_rules.py`

---

## Fuera de alcance (no planificado)

- [ ] **Espectadores / modo observador** — requiere diseño de permisos y UX aparte; no era parte del pedido inicial.

---

## Comandos útiles (resumen)

| Comando | Uso |
|---------|-----|
| `/helpimpostor` | Reglas |
| `/impostor-activos` | Salas vivas |
| `/impostor-historial` | Últimas partidas en BD |
| `/revancha` / `?revancha` | Host reinicia |
| `?quierorevancha` | Voto revancha |

---

## Archivos clave

| Área | Ruta |
|------|------|
| Impostor | `cogs/impostor/` |
| Tests reglas | `tests/test_impostor_rules.py` |
| Trivia | `cogs/economia/trivia_cog.py` |
