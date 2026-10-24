#!/usr/bin/env python3
"""Fixture HTTP stdlib — defeito conhecido e caminho correto.

Não é aplicação de produto. Healing não pode tornar verde o defeito.
"""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.environ.get("E2E_FIXTURE_HOST", "127.0.0.1")
PORT = int(os.environ.get("E2E_FIXTURE_PORT", "4173"))
MODE = os.environ.get("E2E_FIXTURE_MODE", "correct")  # correct | defect

CORRECT = """<!doctype html><html lang="pt-BR"><head><title>Fixture</title></head>
<body>
  <h1>Resumo</h1>
  <p data-testid="saldo-total">100</p>
</body></html>"""

DEFECT = """<!doctype html><html lang="pt-BR"><head><title>Fixture</title></head>
<body>
  <p>página carregou sem o sinal de domínio</p>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _html(self, code: int, body: str) -> None:
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path.startswith("/health"):
            self._html(200, "ok")
            return
        if self.path.startswith("/fail"):
            self._html(500, "erro interno")
            return
        if self.path.startswith("/broken") or MODE == "defect":
            self._html(200, DEFECT)
            return
        self._html(200, CORRECT)


def main() -> None:
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()


if __name__ == "__main__":
    main()
