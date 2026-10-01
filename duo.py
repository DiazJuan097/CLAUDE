#!/usr/bin/env python3
"""Claude + DeepSeek: mismo trabajo, revisión cruzada en bucle, fusión y verificación final.

Cada modelo es un comando de shell que lee el prompt por stdin y escribe la
respuesta por stdout (ver duo.config.json). Así funciona con cualquier forma
de tener instalado cada modelo (CLI, Ollama, script propio con API, etc.).

Uso:
    python3 duo.py "tu tarea"            [--rounds 2] [--config duo.config.json]
    python3 duo.py --file tarea.txt      [--out resultados]
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REVIEW_PROMPT = """Eres revisor riguroso. Tarea original:
<tarea>
{task}
</tarea>

Trabajo de tu colega a revisar:
<trabajo>
{work}
</trabajo>

Haz, en este orden: 1) LIMPIEZA de datos (duplicados, errores, formato); 2) VERIFICACIÓN de datos y
confiabilidad (marca como "NO VERIFICADO" todo lo que no puedas comprobar; no inventes fuentes ni cifras);
3) ANÁLISIS; 4) CORRECCIONES concretas; 5) CALIFICACIÓN.
Termina SIEMPRE con una última línea exactamente así: SCORE: N/10"""

REVISE_PROMPT = """Tarea original:
<tarea>
{task}
</tarea>

Tu trabajo actual:
<trabajo>
{work}
</trabajo>

Crítica recibida de tu colega:
<critica>
{review}
</critica>

Reescribe tu trabajo completo aplicando las correcciones válidas. Si una crítica es incorrecta, ignórala.
No inventes datos ni fuentes; marca lo no verificable. Entrega solo el trabajo corregido."""

MERGE_PROMPT = """Tarea original:
<tarea>
{task}
</tarea>

Versión A:
<a>
{a}
</a>

Versión B:
<b>
{b}
</b>

Une lo mejor de ambas en UN solo trabajo: sin duplicados, datos consistentes (si A y B discrepan,
indícalo y elige lo mejor sustentado), mejor redactado y estructurado. No inventes datos ni fuentes.
Entrega solo el trabajo unificado."""

FINAL_CHECK_PROMPT = """Tarea original:
<tarea>
{task}
</tarea>

Trabajo final candidato:
<trabajo>
{work}
</trabajo>

Verifica que cumple la tarea, que los datos son consistentes y que no hay afirmaciones inventadas.
Responde con los problemas encontrados (o "Sin problemas") y termina con una última línea exactamente:
VEREDICTO: APRUEBO   o   VEREDICTO: NO APRUEBO
y antes SCORE: N/10"""


def call(model, cfg, prompt, log):
    cmd = cfg[model]["cmd"]
    for attempt in range(2):
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                           timeout=cfg[model].get("timeout", 900))
        out = re.sub(r"<think>.*?</think>", "", p.stdout, flags=re.S).strip()
        if p.returncode == 0 and out:
            log(f"  [{model}] ok ({len(out)} caracteres)")
            return out
        log(f"  [{model}] fallo (rc={p.returncode}) {p.stderr.strip()[:200]}")
        time.sleep(2)
    raise RuntimeError(f"{model} no respondió: revisa el comando en la config")


def score(text):
    m = re.findall(r"SCORE:\s*(\d+(?:\.\d+)?)\s*/\s*10", text)
    return float(m[-1]) if m else None


def approved(text):
    return bool(re.search(r"VEREDICTO:\s*APRUEBO", text)) and "NO APRUEBO" not in text.split("VEREDICTO:")[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task", nargs="?")
    ap.add_argument("--file")
    ap.add_argument("--config", default=str(Path(__file__).with_name("duo.config.json")))
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--out", default="duo_output")
    args = ap.parse_args()

    task = Path(args.file).read_text() if args.file else args.task
    if not task:
        ap.error("da una tarea o --file")
    cfg = json.loads(Path(args.config).read_text())
    a, b = list(cfg)[:2]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    def log(msg):
        print(msg, flush=True)
        with open(out / "log.txt", "a") as f:
            f.write(msg + "\n")

    def save(name, text):
        (out / name).write_text(text)

    log("1) Trabajo independiente")
    work = {m: call(m, cfg, task, log) for m in (a, b)}
    for m in work:
        save(f"00_{m}_inicial.md", work[m])

    scores = {}
    for r in range(1, args.rounds + 1):
        log(f"2) Ronda {r}: revisión cruzada y corrección")
        reviews = {}
        for m, other in ((a, b), (b, a)):
            reviews[other] = call(m, cfg, REVIEW_PROMPT.format(task=task, work=work[other]), log)
            scores[(r, other)] = score(reviews[other])
            save(f"r{r}_{m}_revisa_a_{other}.md", reviews[other])
        log(f"   calificaciones: " + ", ".join(f"{k[1]}={v}" for k, v in scores.items() if k[0] == r))
        for m in (a, b):
            work[m] = call(m, cfg, REVISE_PROMPT.format(task=task, work=work[m], review=reviews[m]), log)
            save(f"r{r}_{m}_corregido.md", work[m])

    log("3) Fusión: cada modelo une ambas versiones")
    merged = {m: call(m, cfg, MERGE_PROMPT.format(task=task, a=work[a], b=work[b]), log) for m in (a, b)}
    for m in merged:
        save(f"merge_{m}.md", merged[m])

    log("4) Calificación cruzada de las fusiones y elección")
    final_scores = {}
    for m, other in ((a, b), (b, a)):
        rv = call(m, cfg, REVIEW_PROMPT.format(task=task, work=merged[other]), log)
        final_scores[other] = score(rv) or 0
        save(f"merge_{m}_califica_a_{other}.md", rv)
    best = max(final_scores, key=final_scores.get)
    final = merged[best]
    log(f"   notas fusión: {final_scores} -> se elige la de {best}")

    log("5) Verificación final por ambos")
    for attempt in range(2):
        checks = {m: call(m, cfg, FINAL_CHECK_PROMPT.format(task=task, work=final), log) for m in (a, b)}
        for m in checks:
            save(f"final_check_{m}.md", checks[m])
        if all(approved(c) for c in checks.values()):
            log("   ambos aprueban")
            break
        log("   hay objeciones: corrección y nueva verificación")
        objections = "\n\n".join(f"[{m}]\n{c}" for m, c in checks.items())
        final = call(best, cfg, REVISE_PROMPT.format(task=task, work=final, review=objections), log)
    else:
        log("   AVISO: tras el reintento no hubo aprobación de ambos; revisa final_check_*.md")

    save("FINAL.md", final)
    log(f"Listo -> {out / 'FINAL.md'}")


if __name__ == "__main__":
    sys.exit(main())
