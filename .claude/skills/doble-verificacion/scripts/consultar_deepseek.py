#!/usr/bin/env python3
"""Envía un enunciado a la API de DeepSeek y imprime la respuesta.

Solo usa la biblioteca estándar. Configuración por variables de entorno:
  DEEPSEEK_API_KEY   (obligatoria)
  DEEPSEEK_BASE_URL  (opcional, por defecto https://api.deepseek.com)
  DEEPSEEK_MODEL_RAZONAR / DEEPSEEK_MODEL_RAPIDO  (opcionales)

Los nombres de modelo por defecto pueden cambiar: verifica en la documentación
oficial de DeepSeek y ajústalos con las variables de arriba si hace falta.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

SISTEMA = (
    "Eres un analista riguroso. Analiza el problema de forma independiente. "
    "Separa claramente hechos verificables de suposiciones, indica tu nivel de "
    "certeza, no inventes fuentes ni cifras, y señala qué habría que verificar."
)


def main():
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--archivo", help="Ruta del archivo con el enunciado")
    g.add_argument("--texto", help="Enunciado directo")
    p.add_argument("--modo", choices=["razonar", "rapido"], default="razonar")
    p.add_argument("--timeout", type=int, default=300)
    args = p.parse_args()

    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        sys.exit("ERROR: falta la variable de entorno DEEPSEEK_API_KEY")

    if args.archivo:
        with open(args.archivo, encoding="utf-8") as f:
            enunciado = f.read()
    else:
        enunciado = args.texto

    base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    modelo = (
        os.environ.get("DEEPSEEK_MODEL_RAZONAR", "deepseek-reasoner")
        if args.modo == "razonar"
        else os.environ.get("DEEPSEEK_MODEL_RAPIDO", "deepseek-chat")
    )

    cuerpo = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": SISTEMA},
            {"role": "user", "content": enunciado},
        ],
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as r:
            datos = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"ERROR HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")
    except urllib.error.URLError as e:
        sys.exit(f"ERROR de red: {e.reason}")

    try:
        print(datos["choices"][0]["message"]["content"])
    except (KeyError, IndexError):
        sys.exit(f"ERROR: respuesta inesperada: {json.dumps(datos)[:500]}")


if __name__ == "__main__":
    main()
