"""V9 fixture local e V13 caminho do consumer-ci — sem alvo remoto."""

from __future__ import annotations

import threading
from http.client import HTTPConnection
from pathlib import Path

from run_report import verificar_completude_ci

EVALS = Path(__file__).resolve().parents[1] / "evals"
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _serve(port: int):
    import importlib.util
    spec = importlib.util.spec_from_file_location("fixture_server", EVALS / "server.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    httpd = mod.ThreadingHTTPServer(("127.0.0.1", port), mod.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def _get(port: int, path: str):
    conn = HTTPConnection("127.0.0.1", port, timeout=2)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read().decode()
    conn.close()
    return resp.status, body


def test_v9_correto_verde_defeito_vermelho():
    httpd = _serve(4179)
    try:
        st, body = _get(4179, "/")
        assert st == 200
        assert "Resumo" in body
        st, broken = _get(4179, "/broken")
        assert st == 200
        assert "Resumo" not in broken
        st, fail = _get(4179, "/fail")
        assert st == 500
    finally:
        httpd.shutdown()


def test_v9_selecao_zero_nao_e_sucesso():
    erros = verificar_completude_ci({
        "url": "http://127.0.0.1:4173",
        "deployment_identity": {"sha": "local", "demonstrated": True},
        "expected_sha": "local",
        "policy": {"origins": {"local": "http://127.0.0.1:4173"}},
        "expected": ["evals::critical-path-loads"],
        "selected": [],
        "executed": [],
        "exclusions": [],
        "readiness_status": 200,
    })
    assert any("seleção zero" in e for e in erros)


def test_v13_consumer_ci_sem_segredo_nem_deploy():
    texto = (EXAMPLES / "consumer-ci.yml").read_text(encoding="utf-8")
    assert "vercel.app" not in texto
    assert "password" not in texto.lower()
    assert "gh pr comment" not in texto
    assert "deploy" not in texto.lower() or "não faz deploy" in texto
    assert "playwright test" in texto
    assert "run_report.py verify-ci" in texto
    assert "guard.py" in texto


def test_a1a_testdir_evals():
    cfg = Path(__file__).resolve().parents[3] / "playwright.config.ts"
    texto = cfg.read_text(encoding="utf-8")
    assert "skills/codesteer-cerberus/evals" in texto
    assert "sun-cash-tracker" not in texto
    assert "retain-on-failure" in texto
    assert "forbidOnly: true" in texto
