# Resumen de la sesión: skills de automatización

## Objetivo
Crear dos skills para Claude Code:
1. **doble-verificacion** (HECHA, falta probarla): conecta Claude con DeepSeek para trabajos que requieren mucho análisis y verificación (principalmente análisis de datos e investigación; revisión de código en menor medida). Solo se usa cuando tú la invocas.
2. **guiones** (PENDIENTE): automatizar ~10 guiones por día a partir de videos, ahorrando tokens.

## Conceptos clave
- Una skill es una carpeta con un `SKILL.md` (frontmatter con `name` y `description` + instrucciones).
- La `description` es lo más importante: Claude decide con ella cuándo activarla.
- Código: solo cuando hace falta algo mecánico o externo (llamar a una API, transcribir, validar formato). Para estilo y criterio bastan instrucciones y ejemplos.
- Ahorro de tokens: `SKILL.md` corto, guía de estilo y ejemplos en archivos aparte, procesar en lote, preprocesar fuera de Claude (p. ej. transcripciones), plantilla fija de salida, guardar resultados en archivos.

## Qué se construyó (ya en la rama `main`)
```
.claude/skills/doble-verificacion/
├── SKILL.md                       instrucciones del flujo
└── scripts/consultar_deepseek.py  llama a la API de DeepSeek (solo biblioteca estándar)
```

Flujo de la skill:
1. Claude analiza el problema por su cuenta (sin mostrarlo).
2. El script envía el enunciado a DeepSeek SIN la respuesta de Claude.
3. Claude compara: acuerdos y desacuerdos.
4. Cada desacuerdo se resuelve verificando con datos o cálculos reales.
5. Salida: Conclusión / Acuerdos / Desacuerdos y resolución / Incertidumbres.

Reglas incluidas: quitar datos sensibles antes de enviar, recalcular cifras clave, tratar las fuentes citadas como no verificadas, informar errores del script sin inventar la respuesta de DeepSeek.

Uso del script:
```
python3 .claude/skills/doble-verificacion/scripts/consultar_deepseek.py --archivo ENUNCIADO.md --modo razonar
python3 .claude/skills/doble-verificacion/scripts/consultar_deepseek.py --texto "pregunta corta" --modo rapido
```

Variables de entorno que lee: `DEEPSEEK_API_KEY` (obligatoria), `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL_RAZONAR`, `DEEPSEEK_MODEL_RAPIDO` (opcionales).

Verificado hasta ahora: el script compila y, sin clave, falla con el mensaje "falta la variable de entorno DEEPSEEK_API_KEY". NO se ha probado contra DeepSeek.

## API key de DeepSeek
- Se crea en https://platform.deepseek.com/api_keys (empieza por `sk-`).
- `@deepseek-ai/dsh-experimental-tool-agent-team` NO es una API key (parece nombre de paquete npm).
- Guardarla como variable de entorno `DEEPSEEK_API_KEY` en el entorno cloud (menú del entorno en la barra de título → Edit → API credentials o variables de entorno). Una sesión NUEVA la recoge.
- Nunca pegarla en el chat ni en archivos del repo.

## Para practicar en Claude Code (pasos)
1. Abre una sesión NUEVA con el repo `DiazJuan097/CLAUDE` (rama `main`) y el entorno que tiene `DEEPSEEK_API_KEY`.
2. Comprueba que existe la variable: `echo ${DEEPSEEK_API_KEY:+definida}` (debe imprimir "definida").
3. Prueba el script solo, con algo trivial:
   `python3 .claude/skills/doble-verificacion/scripts/consultar_deepseek.py --texto "¿Cuánto es 17*23? Explica." --modo rapido`
4. Si hay error de red/403, la política de red del entorno puede bloquear `api.deepseek.com`; hay que permitirlo en la configuración del entorno.
5. Si hay error de modelo (404/400), revisa los nombres vigentes en la documentación de DeepSeek y ajústalos con `DEEPSEEK_MODEL_RAZONAR` / `DEEPSEEK_MODEL_RAPIDO`.
6. Invoca la skill: `/doble-verificacion` seguido de un problema real pequeño (p. ej. analizar un CSV corto o una pregunta de investigación).
7. Revisa que la salida siga el formato (Conclusión / Acuerdos / Desacuerdos / Incertidumbres) y ajusta el `SKILL.md` según lo que falle.

## Cosas NO verificadas (comprobar)
- Nombres de modelo por defecto (`deepseek-reasoner`, `deepseek-chat`) y URL base `https://api.deepseek.com`: recordados de memoria; confirmar en https://api-docs.deepseek.com/
- La opción `disable-model-invocation: true` del frontmatter (para que solo la invoques tú): no estoy seguro del nombre exacto; verificar en la documentación de skills de Claude Code.
- Si DeepSeek exige saldo prepagado: no confirmado; revisar facturación.
- Que las skills de usuario (`~/.claude/skills/`) persistan en sesiones cloud: no verificado. Por ahora la skill vive en el repo, así que funciona en sesiones que clonen `DiazJuan097/CLAUDE`.
- La variable de entorno solo aplica a sesiones que usen ese mismo entorno cloud.

## Pendiente
- [ ] Probar la skill 1 contra DeepSeek (sesión nueva con la key).
- [ ] Contarle a Claude con detalle qué trabajos de análisis/investigación quieres y ajustar el flujo.
- [ ] Skill 2 (guiones). Datos que hacen falta: origen de los videos (YouTube/archivos/otro), si hay transcripciones, formato del guion (con 1 o 2 ejemplos reales), duración, tono, idioma y dónde guardar los guiones.
- [ ] Decidir si Claude resuelve solo los desacuerdos o te muestra ambas respuestas.

## Nota de git
La rama `main` no existía en el remoto; se creó y se subió con el commit de la skill. No se abrió ningún pull request.
