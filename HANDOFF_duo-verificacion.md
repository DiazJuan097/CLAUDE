# Traspaso: skill "duo-verificacion" (Claude + DeepSeek)

> Pega TODO este documento en un chat nuevo de Claude y escribe después tus preguntas técnicas.
> Instrucción para el Claude que lo lea: eres quien continuará construyendo esta skill. Lee todo,
> no inventes funciones, flags ni APIs (si no estás seguro de que algo existe, dilo y sugiere
> verificarlo en la documentación oficial), y cuando propongas cambios entrega el ARCHIVO COMPLETO
> modificado (no diffs), indicando cuál archivo es.

## 1. Objetivo
Que Claude y DeepSeek hagan EL MISMO trabajo, se revisen entre sí de forma rigurosa, iteren
(limpiar datos, verificar datos y confiabilidad, analizar, corregir, calificar), unifiquen un solo
entregable mejor redactado y al final ambos lo verifiquen. Debe quedar como skill reutilizable de Claude Code.

## 2. Restricciones del usuario (obligatorias)
- Todo se usará en Claude Code SIN repositorio de GitHub: el código no puede referenciar ningún repositorio,
  rama ni rutas del entorno donde se creó. Debe ser autocontenido (una carpeta con 4 archivos, solo Python 3 estándar).
- La skill NO debe publicarse ni instalarse hasta que el usuario lo diga explícitamente.
- La clave de DeepSeek va solo en la variable de entorno DEEPSEEK_API_KEY; nunca en archivos ni en el chat.
- Preferencia del usuario: verdad y precisión sobre utilidad. Señalar incertidumbre, no inventar fuentes,
  cifras, nombres de funciones ni sintaxis; si algo es dudoso, decir que hay que verificarlo.
- El usuario habla español.

## 3. Decisiones de diseño y por qué
- Cada modelo es un comando de shell (prompt por stdin, respuesta por stdout) definido en duo.config.json.
  Así funciona con `claude -p` (Claude Code en modo no interactivo) y con la API de DeepSeek vía deepseek_api.py.
- Por qué NO es un simple "se califican 1-10 y se mezcla": los modelos tienden a coincidir y dar notas altas
  (errores correlados); la fusión puede "lavar" errores; reescribir todo en cada ronda introduce errores nuevos.
- Por eso: (a) revisión por AFIRMACIONES comprobables, ciega entre modelos; (b) foco en desacuerdos;
  (c) evidencia externa con código Python opcional (--run-code, 20 s máx., ejecuta código escrito por modelos: riesgo a revisar);
  (d) parches puntuales de texto exacto en vez de reescrituras; (e) checklist sí/no de 5 puntos en vez de nota 1-10;
  (f) el bucle se detiene cuando una ronda no encuentra problemas nuevos o llega al máximo de rondas;
  (g) lo no comprobable va a PENDIENTES.md para revisión humana.
- Idea clave: que ambos aprueben NO prueba que sea verdad; hay que decirlo siempre.

## 4. Flujo de duo.py
1 generar (ambos, independiente) -> 2 por ronda: extraer afirmaciones (JSON) -> revisión ciega cruzada (OK/ERROR/UNVERIFIED)
-> alinear afirmaciones A vs B (acuerdo/conflicto/solo_a/solo_b) -> evidencia con código (opcional) -> parches ->
3 fusión (un modelo, sin afirmaciones nuevas) -> 4 checklist final sí/no por ambos (1 reintento con parche) ->
salidas en ./duo_output: FINAL.md, PENDIENTES.md, changelog.json, log.txt y archivos por ronda.
Uso: `python3 duo.py "tarea" --rounds 3 [--run-code]`, `python3 duo.py --ping` (prueba rápida de ambos modelos), `--file tarea.txt`.

## 5. Estado real (honesto)
Probado: el flujo completo con modelos SIMULADOS (JSON, parches, ejecución de código, checklist); el adaptador
deepseek_api.py contra un servidor HTTP local falso; ejecución desde otra carpeta; `claude -p` respondió "OK" en el
entorno donde se creó.
NO probado: con la API real de DeepSeek (el usuario aún debe probar con su clave); calidad real del JSON que
devuelven los modelos reales (modelos pequeños pueden devolver JSON inválido: se reintenta una vez y si falla se omite el paso);
rendimiento/costo reales (con 3 rondas son decenas de llamadas).
NO verificado (confirmar en documentación oficial): nombre vigente del modelo DeepSeek (`deepseek-chat` por defecto,
cambiable con DEEPSEEK_MODEL); URL base https://api.deepseek.com y endpoint /chat/completions (formato tipo OpenAI);
ruta de instalación de skills (~/.claude/skills/<nombre>/SKILL.md personal o .claude/skills/ por proyecto);
si Claude Code ofrece una variable con la ruta de la propia skill (no se usó; el SKILL.md manda buscar duo.py).

## 6. Pendientes / ideas abiertas
- Preguntar al usuario qué tipos de trabajo hará (datos, investigación con fuentes, código, redacción) para calibrar la rúbrica.
- Búsqueda web compartida: dar a AMBOS modelos las mismas fuentes recuperadas (hoy los hechos sin código quedan en PENDIENTES).
- Mejorar el match de afirmaciones y la resolución de conflictos; decidir qué modelo hace la fusión (hoy siempre el primero de la config).
- Robustez: manejo de respuestas largas/truncadas, costos, límites de tasa, Windows (usar `python` en vez de `python3`).
- Terminar SKILL.md (descripción para que se active bien, instrucciones de ubicación de carpeta, ejemplos).
- Cuando el usuario autorice: instalar la skill (carpeta duo-verificacion completa).

## 7. Archivos (la carpeta duo-verificacion debe contener exactamente estos 4)

### Archivo: SKILL.md

````markdown
---
name: duo-verificacion
description: Ejecuta un mismo trabajo con dos modelos (Claude y DeepSeek), los hace verificarse entre sí por afirmaciones, corregir con parches puntuales, fusionar en un solo entregable y marcar pendientes para revisión humana. Úsala cuando el usuario pida que Claude y DeepSeek trabajen juntos, se revisen, se califiquen o unifiquen resultados.
---

# Dúo de verificación (Claude + DeepSeek)  — BORRADOR, en construcción

## Cuándo usarla
El usuario quiere que dos modelos hagan el mismo trabajo, se verifiquen mutuamente, iteren y entreguen un resultado unificado.

## Requisitos
- Python 3 (sin librerías extra) y estos archivos, todos en la MISMA carpeta de esta skill: `duo.py`, `duo.config.json`, `deepseek_api.py`. No se usa git ni ningún repositorio.
- Variable de entorno `DEEPSEEK_API_KEY` definida en el equipo del usuario (nunca escribirla en archivos ni mostrarla).
- Cada modelo configurado como comando de shell que lee el prompt por stdin y responde por stdout.
  Ejemplo: `["claude","-p"]` y `["ollama","run","deepseek-r1"]` (verificar nombres con `claude --help` y `ollama list`).

## Procedimiento
1. Confirmar con el usuario la tarea exacta y qué se considera "dato verificable" (cálculos, fuentes, etc.).
2. Ubicar la carpeta de esta skill (la que contiene este SKILL.md; si no se conoce la ruta, buscar `duo.py` bajo `~/.claude/skills` o `.claude/skills`). Comprobar con `python3 <carpeta>/duo.py --ping` (en Windows puede ser `python` en vez de `python3`).
   Ejecutar: `python3 <carpeta>/duo.py "<tarea>" --rounds 3` (añadir `--run-code` solo si el usuario acepta ejecutar código escrito por los modelos).
3. Leer `duo_output/PENDIENTES.md` y `duo_output/log.txt` (se crean en la carpeta de trabajo actual); presentar al usuario `FINAL.md` junto con los pendientes.

## Reglas
- Que ambos modelos aprueben NO prueba que sea verdad: errores correlados son posibles. Decirlo siempre.
- Nunca presentar como verificado algo que quedó en PENDIENTES.md.
- No inventar fuentes, cifras ni citas; lo no comprobable se marca "(no verificado)".
- Priorizar evidencia externa (código que recalcula, fuentes reales) sobre el acuerdo entre modelos.
- Los puntos en desacuerdo se resuelven con evidencia o se escalan al usuario.

## Pendiente por definir
- Búsqueda web compartida (mismas fuentes para ambos modelos).
- Calibrar rúbrica sí/no según tipo de tarea (datos, investigación, código, redacción).

````

### Archivo: duo.config.json

````json
{
  "claude":   { "cmd": ["claude", "-p"], "timeout": 900 },
  "deepseek": { "cmd": ["{python}", "deepseek_api.py"], "timeout": 900 }
}

````

### Archivo: deepseek_api.py

````python
#!/usr/bin/env python3
"""Adaptador DeepSeek: lee el prompt por stdin y escribe la respuesta por stdout.

Variables de entorno:
  DEEPSEEK_API_KEY   (obligatoria) tu clave; NO la pongas en archivos ni en el repositorio
  DEEPSEEK_MODEL     opcional, por defecto "deepseek-chat" (verifica nombres vigentes en la doc oficial)
  DEEPSEEK_BASE_URL  opcional, por defecto "https://api.deepseek.com"
"""
import json
import os
import sys
import urllib.error
import urllib.request

key = os.environ.get("DEEPSEEK_API_KEY")
if not key:
    sys.exit("Falta la variable de entorno DEEPSEEK_API_KEY")

base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
body = json.dumps({
    "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
    "messages": [{"role": "user", "content": sys.stdin.read()}],
    "stream": False,
}).encode()
req = urllib.request.Request(f"{base}/chat/completions", data=body, headers={
    "Content-Type": "application/json", "Authorization": f"Bearer {key}"})
try:
    with urllib.request.urlopen(req, timeout=600) as r:
        print(json.load(r)["choices"][0]["message"]["content"])
except urllib.error.HTTPError as e:
    sys.exit(f"HTTP {e.code}: {e.read().decode()[:300]}")
except (KeyError, IndexError, ValueError) as e:
    sys.exit(f"Respuesta inesperada de la API: {e}")

````

### Archivo: duo.py

````python
#!/usr/bin/env python3
"""Claude + DeepSeek v2: mismo trabajo, verificación por afirmaciones y parches puntuales.

Flujo: generar (ambos, independientes) -> [ronda: extraer afirmaciones -> revisión ciega cruzada
-> alinear y detectar desacuerdos -> evidencia con código (opcional) -> parches puntuales]
-> fusión -> comprobación final sí/no por ambos -> FINAL.md + PENDIENTES.md.

Cada modelo es un comando de shell (prompt por stdin, respuesta por stdout): ver duo.config.json.
Autocontenido: solo necesita Python 3 y esta carpeta (duo.py, duo.config.json, deepseek_api.py). Sin git ni dependencias.

Uso:
    python3 duo.py "tu tarea" [--rounds 3] [--run-code] [--out duo_output]
    python3 duo.py --file tarea.txt
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CHECKLIST = {
    "cumple_la_tarea": "¿Cumple exactamente lo pedido?",
    "cifras_con_respaldo": "¿Cada cifra/dato tiene respaldo o está marcada como no verificada?",
    "totales_coherentes": "¿Totales, porcentajes y cálculos son coherentes?",
    "sin_contradicciones": "¿No hay contradicciones internas?",
    "sin_invenciones": "¿No hay fuentes, citas o datos inventados?",
}

GEN = """[PASO:generar]
{task}

Reglas: no inventes datos, cifras, fuentes ni citas. Marca "(no verificado)" lo que no puedas comprobar."""

EXTRACT = """[PASO:extraer]
Extrae del siguiente trabajo TODAS las afirmaciones comprobables (cifras, fechas, hechos, relaciones, cálculos).
<trabajo>
{work}
</trabajo>
Responde SOLO un JSON: [{{"id":"c1","texto":"...","tipo":"numerica|hecho|logica"}}, ...]"""

REVIEW = """[PASO:revisar]
Tarea original: {task}
Revisa de forma independiente estas afirmaciones del trabajo de otro autor. Limpia (duplicados, formato),
verifica datos y confiabilidad; no asumas que son correctas. Si no puedes comprobarla, di UNVERIFIED.
<trabajo>
{work}
</trabajo>
<afirmaciones>
{claims}
</afirmaciones>
Responde SOLO un JSON: [{{"id":"c1","veredicto":"OK|ERROR|UNVERIFIED","motivo":"..."}}, ...]"""

ALIGN = """[PASO:alinear]
Compara dos listas de afirmaciones sobre la misma tarea y agrúpalas por tema.
Lista A: {a}
Lista B: {b}
Responde SOLO un JSON: [{{"tema":"...","a_ids":["c1"],"b_ids":["c3"],"estado":"acuerdo|conflicto|solo_a|solo_b"}}, ...]
Usa "conflicto" solo si A y B afirman cosas incompatibles sobre lo mismo."""

CODE = """[PASO:codigo]
Para cada problema que se pueda comprobar de forma determinista (cálculos, sumas, porcentajes, fechas,
lógica), escribe código Python autocontenido que imprima el resultado. Si no se puede, omítelo.
<problemas>
{issues}
</problemas>
Responde SOLO un JSON: [{{"iid":"i1","codigo":"print(...)"}}, ...]"""

PATCH = """[PASO:parchear]
Tarea original: {task}
<trabajo>
{work}
</trabajo>
<problemas_y_evidencia>
{issues}
</problemas_y_evidencia>
Corrige SOLO lo necesario con cambios puntuales (no reescribas todo). Si un problema es un falso positivo, ignóralo.
Si algo no se puede comprobar, cámbialo por "(no verificado)". "buscar" debe ser texto EXACTO y único del trabajo.
Responde SOLO un JSON: [{{"buscar":"...","reemplazar":"...","motivo":"..."}}, ...]"""

MERGE = """[PASO:fusionar]
Tarea original: {task}
<version_a>
{a}
</version_a>
<version_b>
{b}
</version_b>
<puntos_sin_resolver>
{pending}
</puntos_sin_resolver>
Une ambas versiones en UN solo trabajo, sin duplicados, bien estructurado y redactado. Reglas: no agregues
afirmaciones nuevas que no estén en A o B; ante discrepancias, usa lo mejor sustentado; los puntos sin
resolver deben quedar marcados "(no verificado)". Entrega solo el trabajo."""

FINAL = """[PASO:final]
Tarea original: {task}
<trabajo>
{work}
</trabajo>
Responde cada pregunta con true/false de forma estricta:
{checklist}
Responde SOLO un JSON: {{"checklist":{{{keys}}},"problemas":["..."]}}"""


def resolve_cmd(cmd):
    """{python} -> intérprete actual; archivos que viven junto a duo.py -> ruta absoluta (funciona desde cualquier carpeta)."""
    here, out = Path(__file__).resolve().parent, []
    for part in cmd:
        if part == "{python}":
            part = sys.executable
        elif not Path(part).is_absolute() and (here / part).is_file():
            part = str(here / part)
        out.append(part)
    return out


def parse_json(text):
    dec, best, best_end = json.JSONDecoder(), None, -1
    for m in re.finditer(r"[\[{]", text):
        try:
            obj, end = dec.raw_decode(text[m.start():])
        except ValueError:
            continue
        if m.start() + end > best_end and isinstance(obj, (list, dict)):
            best, best_end = obj, m.start() + end
    return best


class Duo:
    def __init__(self, cfg, out, run_code):
        self.cfg, self.out, self.run_code = cfg, out, run_code
        self.models = list(cfg)[:2]
        out.mkdir(parents=True, exist_ok=True)

    def log(self, msg):
        print(msg, flush=True)
        with open(self.out / "log.txt", "a") as f:
            f.write(msg + "\n")

    def save(self, name, data):
        text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2)
        (self.out / name).write_text(text)

    def ask(self, model, prompt):
        c = self.cfg[model]
        for _ in range(2):
            p = subprocess.run(resolve_cmd(c["cmd"]), input=prompt, capture_output=True, text=True,
                               timeout=c.get("timeout", 900))
            txt = re.sub(r"<think>.*?</think>", "", p.stdout, flags=re.S).strip()
            if p.returncode == 0 and txt:
                return txt
            self.log(f"  [{model}] fallo rc={p.returncode} {p.stderr.strip()[:200]}")
            time.sleep(2)
        raise RuntimeError(f"{model} no respondió: revisa su comando en la config")

    def ask_json(self, model, prompt):
        txt = self.ask(model, prompt)
        data = parse_json(txt)
        if data is None:
            txt = self.ask(model, prompt + "\n\nTu respuesta anterior no era JSON válido. Responde SOLO JSON.")
            data = parse_json(txt)
        if data is None:
            self.log(f"  [{model}] JSON inválido, se ignora este paso")
            return []
        return data

    def run_snippet(self, code):
        with tempfile.TemporaryDirectory() as d:
            try:
                p = subprocess.run([sys.executable, "-c", code], cwd=d, capture_output=True,
                                   text=True, timeout=20)
                return (p.stdout + p.stderr).strip()[:1000]
            except subprocess.TimeoutExpired:
                return "timeout"

    def apply_patches(self, model, work, patches, round_no):
        applied, failed = [], []
        for p in patches if isinstance(patches, list) else []:
            f, r = p.get("buscar", ""), p.get("reemplazar", "")
            if f and work.count(f) == 1:
                work = work.replace(f, r)
                applied.append(p)
            else:
                failed.append(p)
        self.log(f"  [{model}] parches aplicados={len(applied)} fallidos={len(failed)}")
        return work, applied, failed

    def issues_for(self, claims, verdicts, groups):
        """Problemas por trabajo: errores/no verificados según el revisor + conflictos entre A y B."""
        a, b = self.models
        text = {m: {c["id"]: c["texto"] for c in claims[m] if isinstance(c, dict) and "id" in c} for m in claims}
        issues = []
        for author, vs in verdicts.items():
            for v in vs if isinstance(vs, list) else []:
                if v.get("veredicto") in ("ERROR", "UNVERIFIED"):
                    issues.append({"trabajo": author, "tipo": v["veredicto"],
                                   "afirmacion": text[author].get(v.get("id"), v.get("id")),
                                   "motivo": v.get("motivo", "")})
        for g in groups if isinstance(groups, list) else []:
            if g.get("estado") == "conflicto":
                ta = [text[a].get(i, i) for i in g.get("a_ids", [])]
                tb = [text[b].get(i, i) for i in g.get("b_ids", [])]
                for m in (a, b):
                    issues.append({"trabajo": m, "tipo": "CONFLICTO", "afirmacion": g.get("tema"),
                                   "motivo": f"{a} dice {ta}; {b} dice {tb}"})
        for n, i in enumerate(issues, 1):
            i["iid"] = f"i{n}"
        return issues

    def main(self, task, rounds):
        a, b = self.models
        self.log("1) Trabajo independiente")
        work = {m: self.ask(m, GEN.format(task=task)) for m in self.models}
        for m in work:
            self.save(f"00_{m}_inicial.md", work[m])

        stats, changelog, issues = {}, [], []
        for r in range(1, rounds + 1):
            self.log(f"2) Ronda {r}: afirmaciones -> revisión ciega -> desacuerdos")
            claims = {m: self.ask_json(m, EXTRACT.format(work=work[m])) for m in self.models}
            verdicts = {}
            for rev, auth in ((a, b), (b, a)):
                verdicts[auth] = self.ask_json(rev, REVIEW.format(
                    task=task, work=work[auth], claims=json.dumps(claims[auth], ensure_ascii=False)))
            groups = self.ask_json(a, ALIGN.format(a=json.dumps(claims[a], ensure_ascii=False),
                                                   b=json.dumps(claims[b], ensure_ascii=False)))
            issues = self.issues_for(claims, verdicts, groups)
            for m in self.models:
                vs = [v.get("veredicto") for v in verdicts[m] if isinstance(v, dict)]
                stats[(r, m)] = {k: vs.count(k) for k in ("OK", "ERROR", "UNVERIFIED")}
            self.save(f"r{r}_afirmaciones.json", claims)
            self.save(f"r{r}_veredictos.json", verdicts)
            self.save(f"r{r}_problemas.json", issues)
            self.log(f"   problemas detectados: {len(issues)} | " +
                     ", ".join(f"{m}: {stats[(r, m)]}" for m in self.models))
            if not issues:
                self.log("   sin problemas nuevos: se detiene el bucle")
                break

            evidence = {}
            if self.run_code:
                for m in self.models:
                    for item in self.ask_json(m, CODE.format(issues=json.dumps(issues, ensure_ascii=False))):
                        if isinstance(item, dict) and item.get("codigo"):
                            evidence.setdefault(item.get("iid"), []).append(
                                {"modelo": m, "salida": self.run_snippet(item["codigo"])})
                self.save(f"r{r}_evidencia.json", evidence)
            for i in issues:
                i["evidencia"] = evidence.get(i["iid"], [])

            for m in self.models:
                mine = [i for i in issues if i["trabajo"] == m]
                if not mine:
                    continue
                patches = self.ask_json(m, PATCH.format(task=task, work=work[m],
                                                        issues=json.dumps(mine, ensure_ascii=False)))
                work[m], ok, bad = self.apply_patches(m, work[m], patches, r)
                changelog.append({"ronda": r, "modelo": m, "aplicados": ok, "fallidos": bad})
                self.save(f"r{r}_{m}_corregido.md", work[m])
        self.save("changelog.json", changelog)

        pending = [i for i in issues if not i.get("evidencia")] if issues else []
        self.log("3) Fusión")
        merged = self.ask(a, MERGE.format(task=task, a=work[a], b=work[b],
                                          pending=json.dumps(pending, ensure_ascii=False)))
        self.log("4) Comprobación final sí/no por ambos")
        final_problems = []
        for attempt in range(2):
            results = {}
            cl = "\n".join(f"- {k}: {v}" for k, v in CHECKLIST.items())
            keys = ", ".join(f'"{k}": true' for k in CHECKLIST)
            for m in self.models:
                res = self.ask_json(m, FINAL.format(task=task, work=merged, checklist=cl, keys=keys))
                results[m] = res if isinstance(res, dict) else {}
            self.save("final_checks.json", results)
            final_problems = [p for m in self.models for p in results[m].get("problemas", []) if p]
            failed = [k for m in self.models for k, v in results[m].get("checklist", {}).items() if v is not True]
            self.log(f"   puntos fallidos: {failed or 'ninguno'}")
            if not failed and not final_problems:
                break
            if attempt == 0:
                patches = self.ask_json(a, PATCH.format(task=task, work=merged, issues=json.dumps(
                    {"checklist_fallido": failed, "problemas": final_problems}, ensure_ascii=False)))
                merged, _, _ = self.apply_patches(a, merged, patches, "final")

        self.save("FINAL.md", merged)
        lines = ["# Pendientes para revisión humana\n"]
        lines += [f"- [{p['tipo']}] {p['afirmacion']}: {p['motivo']}" for p in pending]
        lines += [f"- [FINAL] {p}" for p in final_problems]
        self.save("PENDIENTES.md", "\n".join(lines) if len(lines) > 1 else "# Sin pendientes detectados\n")
        self.log(f"Listo -> {self.out / 'FINAL.md'} y PENDIENTES.md (revísalo: que ambos aprueben no es prueba de verdad)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task", nargs="?")
    ap.add_argument("--file")
    ap.add_argument("--config", default=str(Path(__file__).resolve().with_name("duo.config.json")))
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--run-code", action="store_true",
                    help="ejecuta el código Python que escriban los modelos para comprobar cálculos (20 s máx., revisa antes)")
    ap.add_argument("--out", default="duo_output")
    ap.add_argument("--ping", action="store_true", help="prueba rápida: pregunta 'OK' a cada modelo y sale")
    args = ap.parse_args()
    if args.ping:
        d = Duo(json.loads(Path(args.config).read_text()), Path(args.out), False)
        for m in d.models:
            try:
                print(f"{m}: {d.ask(m, 'Responde solo con la palabra OK')[:80]!r}")
            except Exception as e:
                print(f"{m}: FALLO -> {e}")
        return
    task = Path(args.file).read_text() if args.file else args.task
    if not task:
        ap.error("da una tarea o --file")
    Duo(json.loads(Path(args.config).read_text()), Path(args.out), args.run_code).main(task, args.rounds)


if __name__ == "__main__":
    main()

````
