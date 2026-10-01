---
name: duo-verificacion
description: Ejecuta un mismo trabajo con dos modelos (Claude y DeepSeek), los hace verificarse entre sí por afirmaciones, corregir con parches puntuales, fusionar en un solo entregable y marcar pendientes para revisión humana. Úsala cuando el usuario pida que Claude y DeepSeek trabajen juntos, se revisen, se califiquen o unifiquen resultados.
---

# Dúo de verificación (Claude + DeepSeek)  — BORRADOR, en construcción

## Cuándo usarla
El usuario quiere que dos modelos hagan el mismo trabajo, se verifiquen mutuamente, iteren y entreguen un resultado unificado.

## Requisitos
- `duo.py` y `duo.config.json` (en la carpeta de esta skill).
- Cada modelo configurado como comando de shell que lee el prompt por stdin y responde por stdout.
  Ejemplo: `["claude","-p"]` y `["ollama","run","deepseek-r1"]` (verificar nombres con `claude --help` y `ollama list`).

## Procedimiento
1. Confirmar con el usuario la tarea exacta y qué se considera "dato verificable" (cálculos, fuentes, etc.).
2. Ejecutar: `python3 duo.py "<tarea>" --rounds 3` (añadir `--run-code` solo si el usuario acepta ejecutar código escrito por los modelos).
3. Leer `duo_output/PENDIENTES.md` y `duo_output/log.txt`; presentar al usuario `FINAL.md` junto con los pendientes.

## Reglas
- Que ambos modelos aprueben NO prueba que sea verdad: errores correlados son posibles. Decirlo siempre.
- Nunca presentar como verificado algo que quedó en PENDIENTES.md.
- No inventar fuentes, cifras ni citas; lo no comprobable se marca "(no verificado)".
- Priorizar evidencia externa (código que recalcula, fuentes reales) sobre el acuerdo entre modelos.
- Los puntos en desacuerdo se resuelven con evidencia o se escalan al usuario.

## Pendiente por definir
- Búsqueda web compartida (mismas fuentes para ambos modelos).
- Calibrar rúbrica sí/no según tipo de tarea (datos, investigación, código, redacción).
