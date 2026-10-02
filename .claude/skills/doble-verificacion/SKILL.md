---
name: doble-verificacion
description: Análisis con doble verificación entre Claude y DeepSeek. Usar SOLO cuando el usuario la invoque explícitamente (/doble-verificacion) para análisis de datos, investigación o revisión de código que requieran mucha verificación. No activar por iniciativa propia en tareas normales.
disable-model-invocation: true
---

# Doble verificación Claude + DeepSeek

Dos modelos analizan el mismo problema de forma independiente y Claude reconcilia las diferencias.

## Flujo

1. **Entender la tarea.** Si el pedido es ambiguo, pregunta antes de empezar. Define qué pregunta concreta hay que responder.
2. **Análisis propio.** Haz tu análisis completo y guárdalo en `/tmp` o en el scratchpad (no lo muestres aún). No se lo envíes a DeepSeek.
3. **Consulta independiente.** Escribe el enunciado del problema (con los datos necesarios, sin tu respuesta) en un archivo y ejecuta:
   ```
   python3 .claude/skills/doble-verificacion/scripts/consultar_deepseek.py --archivo ENUNCIADO.md
   ```
   Usa `--modo razonar` para análisis complejos y `--modo rapido` para verificaciones simples.
4. **Comparar.** Lista punto por punto: en qué coinciden, en qué difieren y qué afirmaciones solo aparecen en un modelo.
5. **Resolver desacuerdos.** Para cada diferencia, verifica con los datos, con cálculos reales o con el código. No elijas por intuición ni por "quién suena más seguro". Si no se puede resolver, dilo.
6. **Entregar.** Formato de salida abajo.

## Reglas

- **Privacidad:** el enunciado sale hacia un tercero (DeepSeek). Antes de enviar, quita datos personales, credenciales y cualquier información confidencial. Si el material es sensible, pregunta al usuario.
- **Independencia:** nunca pases tu respuesta a DeepSeek en la primera consulta. Solo úsala en una segunda ronda si hay que debatir un desacuerdo específico.
- **Honestidad:** no presentes como hecho algo que ningún modelo pudo verificar. Marca la incertidumbre.
- **Investigación:** las fuentes citadas por cualquiera de los dos modelos pueden ser inventadas. Verifícalas o márcalas como no verificadas.
- **Datos:** recalcula las cifras clave tú mismo (con código si hace falta) en vez de confiar en los números de cualquiera de los dos.
- **Costo:** esta skill gasta más tokens y dinero que una consulta normal. Úsala solo para lo que lo justifique.
- Si el script falla (sin clave, sin red, error de API), informa el error exacto. No inventes la respuesta de DeepSeek.

## Formato de salida

```
## Conclusión
(respuesta final, breve)

## Acuerdos
- ...

## Desacuerdos y cómo se resolvieron
| Punto | Claude | DeepSeek | Resolución |

## Incertidumbres
- ...
```
