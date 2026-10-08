---
name: duo-verificacion
description: Hace que Claude y DeepSeek resuelvan el mismo trabajo de forma independiente, compara sus afirmaciones, arbitra solo los desacuerdos (con código cuando se pueda), fusiona en un único entregable y reporta qué aportó el segundo modelo y qué queda sin verificar. Úsala SOLO si el usuario lo pide explícitamente y el trabajo exige verificación extrema (cifras, datos o afirmaciones donde un error cuesta caro). No la actives por tu cuenta ni para tareas repetitivas, básicas, preguntas simples o cálculos que un script resuelve.
disable-model-invocation: true
---

# Dúo de verificación (Claude + DeepSeek) — BORRADOR

## Cuándo usarla (restringido)
Solo si el usuario la pide de forma explícita (por ejemplo con `/duo-verificacion`) Y el trabajo exige verificación extrema. Nunca para tareas repetitivas o básicas.

## Qué la hace distinta de usar un solo modelo
- Los dos modelos trabajan **sin verse** y entregan sus afirmaciones comprobables; el script compara y solo gasta tokens en **lo que discrepan**.
- Los desacuerdos se arbitran a ciegas (etiquetas X/Y, orden invertido para cada modelo) y, si siguen en disputa, hay una ronda de refutación.
- El código Python (opcional) es la única evidencia que cuenta como prueba; el acuerdo entre modelos no lo es.
- Cada corrida genera `INFORME.md`: cuántas discrepancias aparecieron, qué errores se confirmaron y cuánto se usó. Si no hubo discrepancias, el informe dice que el segundo modelo aportó poco.

## Cuándo NO usarla
- Preguntas simples, respuestas rápidas o problemas objetivos que un cálculo o script resuelve: usar un solo modelo más código.
- Datos sensibles o de terceros sin que el usuario lo confirme: el contenido se envía a los servidores de DeepSeek.

## Requisitos
- Python 3 (sin librerías extra) y estos archivos juntos en la carpeta de esta skill: `duo.py`, `duo.config.json`, `deepseek_api.py`.
- Variable de entorno `DEEPSEEK_API_KEY` definida en el equipo del usuario (nunca pedirla, escribirla ni mostrarla).
- `claude` instalado y con sesión iniciada (el script lo usa con `claude -p`).
- No se usa git ni ningún repositorio.

## Procedimiento
1. Pide al usuario: la tarea exacta, los datos pegados dentro del texto (el script no recibe adjuntos), el formato del entregable y qué cuenta como verificable.
2. Avisa antes de ejecutar: son típicamente 5 a 10 llamadas con cargas pequeñas (estimación por diseño, no medida), y los datos viajan a DeepSeek. Confirma que está de acuerdo.
3. Prueba la conexión: `python3 ${CLAUDE_SKILL_DIR}/duo.py --ping` (en Windows puede ser `python`). Si falla, muestra el error y detente.
4. Ejecuta: `python3 ${CLAUDE_SKILL_DIR}/duo.py --file tarea.txt --rounds 2` (guarda la tarea en `tarea.txt`). Añade `--run-code` solo si el usuario acepta que se ejecute código escrito por los modelos (20 s máx. cada uno).
5. Lee `duo_output/INFORME.md`, `duo_output/PENDIENTES.md` y `duo_output/log.txt` (se crean en la carpeta de trabajo actual).
6. Entrega al usuario: `FINAL.md`, un resumen del informe y los pendientes destacados aparte.

## Reglas
- Que ambos modelos coincidan o aprueben NO prueba que sea verdad (pueden compartir el error). Dilo siempre.
- Nunca presentes como verificado algo de `PENDIENTES.md` ni las "coincidencias de riesgo alto sin verificación externa".
- No edites `FINAL.md` con tu propio conocimiento; si propones un cambio, indícalo por separado.
- No inventes fuentes, cifras ni citas; lo no comprobable se marca "(no verificado)".
- Si el log indica "JSON inválido" o "llamada extra", avisa que esa parte de la verificación fue más débil.

## Limitaciones conocidas
- No busca en la web: los hechos sin cálculo que lo compruebe quedan como no verificados.
- La calidad depende de que los modelos devuelvan JSON válido; un modelo pequeño puede fallar (se reintenta una vez).
- Aún no probado con la API real de DeepSeek ni con tareas reales; el nombre del modelo (`deepseek-chat` por defecto, cambiable con `DEEPSEEK_MODEL`) y la URL de la API deben confirmarse en la documentación oficial.
- `claude -p` podría disponer de herramientas en la carpeta de trabajo; verificar con `claude --help` cómo restringirlas.
