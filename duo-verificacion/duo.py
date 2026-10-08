#!/usr/bin/env python3
"""Claude + DeepSeek v3 (eficiente): ambos hacen el trabajo; solo se gasta en lo que discrepan.

Flujo (≈6-10 llamadas, con cargas pequeñas):
  1 generar (ambos, independientes; cada uno entrega trabajo + lista de afirmaciones en la MISMA llamada)
  2 alinear afirmaciones A vs B (1 llamada, solo textos cortos) -> acuerdo / conflicto / solo_a / solo_b
  3 arbitrar SOLO las disputas (conflictos y afirmaciones de riesgo alto que solo dijo uno):
    revisión ciega con etiquetas X/Y (orden invertido para cada modelo); si no coinciden, ronda de refutación
  4 fusionar (1 llamada) aplicando las decisiones; lo no resuelto queda "(no verificado)"
  5 comprobación final sí/no por el OTRO modelo (1 llamada)
Salidas en ./duo_output: FINAL.md, INFORME.md (qué aportó el 2.º modelo y uso), PENDIENTES.md, log.txt, JSON de cada paso.

Cada modelo es un comando de shell (prompt por stdin, respuesta por stdout): ver duo.config.json.
Autocontenido: solo Python 3 y esta carpeta (duo.py, duo.config.json, deepseek_api.py). Sin git ni dependencias.

Uso:
    python3 duo.py "tu tarea" [--rounds 2] [--run-code] [--out duo_output]
    python3 duo.py --file tarea.txt
    python3 duo.py --ping
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MARK = "===AFIRMACIONES==="

CHECKLIST = {
    "cumple_la_tarea": "¿Cumple exactamente lo pedido?",
    "cifras_con_respaldo": "¿Cada cifra/dato tiene respaldo o está marcada como no verificada?",
    "totales_coherentes": "¿Totales, porcentajes y cálculos son coherentes?",
    "sin_contradicciones": "¿No hay contradicciones internas ni con las decisiones tomadas?",
    "sin_invenciones": "¿No hay fuentes, citas o datos inventados?",
}

GEN = """[PASO:generar]
{task}

Reglas: no inventes datos, cifras, fuentes ni citas. Marca "(no verificado)" lo que no puedas comprobar.
Formato: primero el trabajo completo. Después, en una línea sola, {mark} y a continuación SOLO un JSON compacto
con las afirmaciones comprobables del trabajo (cifras, fechas, hechos, cálculos, relaciones causales):
[{{"id":"c1","texto":"...","tipo":"numerica|hecho|logica","riesgo":"alto|bajo"}}]"""

EXTRACT = """[PASO:extraer]
Extrae del trabajo TODAS las afirmaciones comprobables.
<trabajo>
{work}
</trabajo>
Responde SOLO un JSON: [{{"id":"c1","texto":"...","tipo":"numerica|hecho|logica","riesgo":"alto|bajo"}}]"""

ALIGN = """[PASO:alinear]
Agrupa por tema las afirmaciones de dos versiones independientes del mismo trabajo.
A: {a}
B: {b}
Responde SOLO un JSON: [{{"tema":"...","a_ids":["c1"],"b_ids":["c3"],"estado":"acuerdo|conflicto|solo_a|solo_b"}}]
"conflicto" solo si afirman cosas incompatibles sobre lo mismo."""

ARBITRATE = """[PASO:arbitrar]
Tarea original: {task}
Dos versiones independientes (X e Y) difieren en estos puntos. Decide cuál es correcta con tu conocimiento y
razonamiento, sin asumir que alguna tiene razón. Si no puedes afirmarlo con seguridad responde "incierto" (no adivines).
Si se puede comprobar con un cálculo, añade "codigo": Python autocontenido que imprima el resultado.
<puntos>
{items}
</puntos>
Responde SOLO un JSON: [{{"iid":"d1","veredicto":"X|Y|ninguna|incierto","correcta":"valor o texto correcto (corto)","razon":"1-2 frases","codigo":"(opcional)"}}]"""

REFUTE = """[PASO:refutar]
Tarea original: {task}
Estos puntos siguen sin acuerdo entre los dos revisores. Para cada uno ves tu veredicto previo, el del otro revisor
(con su razón) y la evidencia de código. Reconsidera: si el otro tiene razón, cámbialo; si no, refuta su razón.
Si sigues sin poder comprobarlo, "incierto".
<puntos>
{items}
</puntos>
Responde SOLO un JSON: [{{"iid":"d1","veredicto":"X|Y|ninguna|incierto","correcta":"...","razon":"...","codigo":"(opcional)"}}]"""

PATCH = """[PASO:parchear]
Tarea original: {task}
<trabajo>
{work}
</trabajo>
<problemas>
{issues}
</problemas>
Corrige SOLO lo necesario con cambios puntuales (no reescribas todo). Si algo no se puede comprobar, cámbialo por
"(no verificado)". "buscar" debe ser texto EXACTO y único del trabajo.
Responde SOLO un JSON: [{{"buscar":"...","reemplazar":"...","motivo":"..."}}]"""

MERGE = """[PASO:fusionar]
Tarea original: {task}
<version_a>
{a}
</version_a>
<version_b>
{b}
</version_b>
<decisiones_verificadas>
{decisions}
</decisiones_verificadas>
<sin_resolver>
{pending}
</sin_resolver>
Une ambas versiones en UN solo trabajo, sin duplicados, bien estructurado y redactado. Reglas: aplica las decisiones
verificadas; los puntos sin_resolver quedan marcados "(no verificado)"; no agregues afirmaciones nuevas que no estén
en A o B. Entrega solo el trabajo."""

FINAL = """[PASO:final]
Tarea original: {task}
<trabajo>
{work}
</trabajo>
<decisiones_verificadas>
{decisions}
</decisiones_verificadas>
Responde cada pregunta con true/false de forma estricta:
{checklist}
Responde SOLO un JSON: {{"checklist":{{{keys}}},"problemas":["..."]}}"""


def resolve_cmd(cmd):
    """{python} -> intérprete actual; archivos junto a duo.py -> ruta absoluta (funciona desde cualquier carpeta)."""
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


def compact(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def split_work(text):
    """Separa el trabajo de la lista de afirmaciones que el modelo añade tras MARK."""
    if MARK in text:
        body, tail = text.rsplit(MARK, 1)
        claims = parse_json(tail)
        return body.strip(), claims if isinstance(claims, list) else None
    return text.strip(), None


def is_high(c):
    return c.get("riesgo") == "alto" or (not c.get("riesgo") and c.get("tipo") == "numerica")


class Duo:
    def __init__(self, cfg, out, run_code):
        self.cfg = {k: v for k, v in cfg.items() if not k.startswith("_")}
        self.models = list(self.cfg)[:2]
        a, b = self.models
        roles = cfg.get("_roles", {})
        self.aligner = roles.get("aligner", b)
        self.merger = roles.get("merger", a)
        for r in (self.aligner, self.merger):
            if r not in self.models:
                raise SystemExit(f"_roles apunta a un modelo que no existe en la config: {r}")
        self.finalizer = b if self.merger == a else a
        self.out, self.run_code, self.usage = out, run_code, {}
        out.mkdir(parents=True, exist_ok=True)

    # ---------- utilidades ----------
    def log(self, msg):
        print(msg, flush=True)
        with open(self.out / "log.txt", "a") as f:
            f.write(msg + "\n")

    def save(self, name, data):
        text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2)
        (self.out / name).write_text(text)

    def ask(self, model, prompt):
        c, last = self.cfg[model], ""
        for _ in range(2):
            try:
                p = subprocess.run(resolve_cmd(c["cmd"]), input=prompt, capture_output=True, text=True,
                                   timeout=c.get("timeout", 900))
            except FileNotFoundError:
                raise RuntimeError(f"{model}: no se encontró el comando {c['cmd'][0]!r}; revisa duo.config.json")
            except subprocess.TimeoutExpired:
                last = "timeout"
                self.log(f"  [{model}] timeout")
                continue
            txt = re.sub(r"<think>.*?</think>", "", p.stdout, flags=re.S).strip()
            if p.returncode == 0 and txt:
                u = self.usage.setdefault(model, [0, 0, 0])
                u[0] += 1
                u[1] += len(prompt)
                u[2] += len(txt)
                return txt
            last = f"rc={p.returncode} {p.stderr.strip()[:200]}"
            self.log(f"  [{model}] fallo {last}")
            time.sleep(2)
        raise RuntimeError(f"{model} no respondió ({last}); revisa su comando y su configuración")

    def ask_json(self, model, prompt):
        data = parse_json(self.ask(model, prompt))
        if data is None:
            data = parse_json(self.ask(model, prompt + "\n\nTu respuesta anterior no era JSON válido. Responde SOLO JSON."))
        if data is None:
            self.log(f"  [{model}] JSON inválido, se omite este paso")
            return []
        return data

    def run_snippet(self, code):
        with tempfile.TemporaryDirectory() as d:
            try:
                p = subprocess.run([sys.executable, "-c", code], cwd=d, capture_output=True, text=True, timeout=20)
                return (p.stdout + p.stderr).strip()[:1000]
            except subprocess.TimeoutExpired:
                return "timeout"

    def apply_patches(self, work, patches):
        applied = failed = 0
        for p in patches if isinstance(patches, list) else []:
            f, r = (p.get("buscar") or ""), p.get("reemplazar", "")
            if f and work.count(f) == 1:
                work, applied = work.replace(f, r), applied + 1
            else:
                failed += 1
        self.log(f"  parches aplicados={applied} fallidos={failed}")
        return work

    # ---------- disputas ----------
    def labels(self, m):
        """Para el modelo m: etiqueta X/Y -> versión real (A/B). Orden invertido entre modelos para evitar sesgo de posición."""
        return {"X": "A", "Y": "B"} if m == self.models[0] else {"X": "B", "Y": "A"}

    def build_disputes(self, claims, groups):
        a, b = self.models
        info = {a: {}, b: {}}
        for m in (a, b):
            for c in claims[m]:
                if isinstance(c, dict) and c.get("id") and c.get("texto"):
                    info[m][c["id"]] = c
        disputes, agreed_high = [], []
        for g in groups if isinstance(groups, list) else []:
            ca = [info[a][i] for i in g.get("a_ids", []) if i in info[a]]
            cb = [info[b][i] for i in g.get("b_ids", []) if i in info[b]]
            est, high = g.get("estado"), any(is_high(c) for c in ca + cb)
            if est == "conflicto" or (est in ("solo_a", "solo_b") and high):
                disputes.append({"iid": f"d{len(disputes) + 1}", "tema": g.get("tema", ""), "tipo": est,
                                 "A": [c["texto"] for c in ca], "B": [c["texto"] for c in cb]})
            elif est == "acuerdo" and high:
                agreed_high.append(g.get("tema") or (ca or cb)[0]["texto"])
        return disputes, agreed_high, {m: len(info[m]) for m in info}

    def arbitrate(self, task, disputes, rounds):
        a, b = self.models
        history, evidence, resolved, unresolved = {}, {}, {}, list(disputes)
        for r in range(1, rounds + 1):
            if not unresolved:
                break
            self.log(f"3) Arbitraje ronda {r}: {len(unresolved)} punto(s) en disputa")
            for m in self.models:
                to_real = self.labels(m)
                to_label = {v: k for k, v in to_real.items()}
                items = []
                for d in unresolved:
                    it = {"iid": d["iid"], "tema": d["tema"], "X": d[to_real["X"]], "Y": d[to_real["Y"]]}
                    if r > 1:
                        h, other = history[d["iid"]], (b if m == a else a)
                        lab = lambda v: to_label.get(v, v)
                        it.update({"tu_veredicto": lab(h[m]["veredicto"]), "otro_veredicto": lab(h[other]["veredicto"]),
                                   "otro_razon": h[other]["razon"], "evidencia": evidence.get(d["iid"], [])})
                    items.append(it)
                res = self.ask_json(m, (ARBITRATE if r == 1 else REFUTE).format(task=task, items=compact(items)))
                for v in res if isinstance(res, list) else []:
                    if not isinstance(v, dict) or v.get("iid") not in {d["iid"] for d in unresolved}:
                        continue
                    ver = to_real.get(v.get("veredicto"), v.get("veredicto"))
                    ver = ver if ver in ("A", "B", "ninguna") else "incierto"
                    history.setdefault(v["iid"], {})[m] = {"veredicto": ver, "correcta": v.get("correcta", ""),
                                                           "razon": v.get("razon", "")}
                    if self.run_code and v.get("codigo"):
                        evidence.setdefault(v["iid"], []).append({"modelo": m, "salida": self.run_snippet(v["codigo"])})
            still = []
            for d in unresolved:
                h = history.get(d["iid"], {})
                va, vb = h.get(a, {}).get("veredicto"), h.get(b, {}).get("veredicto")
                if va and va == vb and va != "incierto":
                    resolved[d["iid"]] = {"tema": d["tema"], "veredicto": va, "ronda": r,
                                          "correcta": h[a]["correcta"] or h[b]["correcta"],
                                          "evidencia": evidence.get(d["iid"], [])}
                else:
                    still.append(d)
            unresolved = still
        return resolved, unresolved, history, evidence

    # ---------- flujo principal ----------
    def main(self, task, rounds):
        a, b = self.models
        self.log("1) Trabajo independiente (con afirmaciones incluidas)")
        work, claims = {}, {}
        for m in self.models:
            work[m], cl = split_work(self.ask(m, GEN.format(task=task, mark=MARK)))
            if cl is None:
                self.log(f"  [{m}] sin lista de afirmaciones válida: llamada extra para extraerla")
                cl = self.ask_json(m, EXTRACT.format(work=work[m]))
            claims[m] = cl
            self.save(f"00_{m}_trabajo.md", work[m])
        self.save("01_afirmaciones.json", claims)

        self.log("2) Alineación de afirmaciones")
        short = {m: [[c.get("id"), c.get("texto")] for c in claims[m] if isinstance(c, dict)] for m in claims}
        groups = self.ask_json(self.aligner, ALIGN.format(a=compact(short[a]), b=compact(short[b])))
        disputes, agreed_high, counts = self.build_disputes(claims, groups)
        self.save("02_alineacion.json", groups)
        self.save("03_disputas.json", disputes)
        self.log(f"   afirmaciones A={counts[a]} B={counts[b]} | disputas={len(disputes)} | "
                 f"coincidencias de riesgo alto={len(agreed_high)}")

        resolved, unresolved, history, evidence = self.arbitrate(task, disputes, rounds)
        self.save("04_decisiones.json", resolved)
        self.save("04_historial_arbitraje.json", {"historial": history, "evidencia": evidence})

        self.log(f"4) Fusión por {self.merger}")
        decisions = [{"tema": v["tema"], "correcta": v["correcta"]} for v in resolved.values()]
        pending = [{"tema": d["tema"], "A": d["A"], "B": d["B"]} for d in unresolved]
        merged = self.ask(self.merger, MERGE.format(task=task, a=work[a], b=work[b],
                                                    decisions=compact(decisions), pending=compact(pending)))

        self.log(f"5) Comprobación final por {self.finalizer}")
        cl = "\n".join(f"- {k}: {v}" for k, v in CHECKLIST.items())
        keys = ", ".join(f'"{k}": true' for k in CHECKLIST)
        final_problems, failed = [], []
        for attempt in range(2):
            res = self.ask_json(self.finalizer, FINAL.format(task=task, work=merged, decisions=compact(decisions),
                                                              checklist=cl, keys=keys))
            res = res if isinstance(res, dict) else {}
            final_problems = [p for p in res.get("problemas", []) if p]
            cl_res = res.get("checklist") if isinstance(res.get("checklist"), dict) else {}
            if not cl_res:
                final_problems.append("La comprobación final no devolvió un checklist legible: NO cuenta como aprobación")
            failed = [k for k in CHECKLIST if cl_res.get(k) is not True]  # lo que falte cuenta como fallo
            self.save("05_comprobacion_final.json", res)
            self.log(f"   puntos fallidos: {failed or 'ninguno'}")
            if not failed and not final_problems:
                break
            if attempt == 0:
                patches = self.ask_json(self.merger, PATCH.format(
                    task=task, work=merged, issues=compact({"checklist_fallido": failed, "problemas": final_problems})))
                merged = self.apply_patches(merged, patches)

        self.save("FINAL.md", merged)
        self.report(counts, disputes, agreed_high, resolved, unresolved, history, evidence, final_problems, failed)
        self.log(f"Listo -> {self.out / 'FINAL.md'}, INFORME.md y PENDIENTES.md")

    def report(self, counts, disputes, agreed_high, resolved, unresolved, history, evidence, final_problems, failed):
        a, b = self.models
        wrong = {a: 0, b: 0}
        for v in resolved.values():
            if v["veredicto"] == "A":
                wrong[b] += 1
            elif v["veredicto"] == "B":
                wrong[a] += 1
            else:
                wrong[a] += 1
                wrong[b] += 1
        with_code = sum(1 for v in resolved.values() if v["evidencia"])
        L = ["# Informe de la corrida", "",
             f"- Afirmaciones: {a}={counts[a]}, {b}={counts[b]}",
             f"- Disputas (conflictos y afirmaciones de riesgo alto que solo dijo uno): {len(disputes)}",
             f"- Resueltas con acuerdo de ambos revisores: {len(resolved)} (con evidencia de código: {with_code})",
             f"- Sin resolver (van a PENDIENTES.md): {len(unresolved)}",
             f"- Errores confirmados por ambos revisores: {a}={wrong[a]}, {b}={wrong[b]}",
             f"- Coincidencias de riesgo alto SIN verificación externa: {len(agreed_high)}", ""]
        L.append("## Lectura honesta")
        if not disputes:
            L.append("Los modelos no discreparon en nada relevante. Eso NO prueba que sea correcto (pueden compartir "
                     "el mismo error): para esta tarea el segundo modelo aportó poco; para tareas parecidas quizá "
                     "baste un modelo más código de verificación.")
        else:
            L.append(f"La comparación detectó {len(disputes)} discrepancia(s) que un solo modelo no habría mostrado. "
                     "Que dos revisores coincidan sobre una disputa no es una prueba: solo la evidencia de código lo es.")
        if agreed_high:
            L += ["", "## Coinciden ambos pero sin verificación externa (riesgo alto)"] + [f"- {t}" for t in agreed_high]
        L += ["", "## Uso (aproximado; ~4 caracteres ≈ 1 token, estimación grosera)"]
        for m, (n, ci, co) in self.usage.items():
            L.append(f"- {m}: {n} llamadas, {ci} caracteres enviados, {co} recibidos")
        self.save("INFORME.md", "\n".join(L) + "\n")

        P = ["# Pendientes para revisión humana", ""]
        for d in unresolved:
            h = history.get(d["iid"], {})
            P.append(f"- [SIN RESOLVER] {d['tema']}: A={d['A']} | B={d['B']}")
            for m, v in h.items():
                P.append(f"    - {m}: {v['veredicto']} — {v['razon']}")
            for e in evidence.get(d["iid"], []):
                P.append(f"    - evidencia código ({e['modelo']}): {e['salida']}")
        P += [f"- [FINAL] {p}" for p in final_problems]
        P += [f"- [CHECKLIST FALLIDO] {k}" for k in failed]
        self.save("PENDIENTES.md", "\n".join(P) + "\n" if len(P) > 2 else "# Sin pendientes detectados\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task", nargs="?")
    ap.add_argument("--file")
    ap.add_argument("--config", default=str(Path(__file__).resolve().with_name("duo.config.json")))
    ap.add_argument("--rounds", type=int, default=2,
                    help="rondas de arbitraje: 1 = revisión ciega; 2 = además refutación de lo que siga en disputa")
    ap.add_argument("--run-code", action="store_true",
                    help="ejecuta el código Python que propongan los modelos para comprobar cálculos (20 s máx.; revisa antes)")
    ap.add_argument("--out", default="duo_output")
    ap.add_argument("--ping", action="store_true", help="prueba rápida: pregunta 'OK' a cada modelo y sale")
    args = ap.parse_args()
    duo = Duo(json.loads(Path(args.config).read_text()), Path(args.out), args.run_code)
    if args.ping:
        for m in duo.models:
            try:
                print(f"{m}: {duo.ask(m, 'Responde solo con la palabra OK')[:80]!r}")
            except RuntimeError as e:
                print(f"{m}: FALLO -> {e}")
        return
    task = Path(args.file).read_text() if args.file else args.task
    if not task:
        ap.error("da una tarea o --file")
    try:
        duo.main(task, args.rounds)
    except RuntimeError as e:
        duo.log(f"ERROR: {e}\nSe conservó lo generado hasta ese punto en {duo.out}/")
        sys.exit(1)


if __name__ == "__main__":
    main()
