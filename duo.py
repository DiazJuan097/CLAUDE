#!/usr/bin/env python3
"""Claude + DeepSeek v2: mismo trabajo, verificación por afirmaciones y parches puntuales.

Flujo: generar (ambos, independientes) -> [ronda: extraer afirmaciones -> revisión ciega cruzada
-> alinear y detectar desacuerdos -> evidencia con código (opcional) -> parches puntuales]
-> fusión -> comprobación final sí/no por ambos -> FINAL.md + PENDIENTES.md.

Cada modelo es un comando de shell (prompt por stdin, respuesta por stdout): ver duo.config.json.

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
            p = subprocess.run(c["cmd"], input=prompt, capture_output=True, text=True,
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
    ap.add_argument("--config", default=str(Path(__file__).with_name("duo.config.json")))
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
