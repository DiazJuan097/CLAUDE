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
