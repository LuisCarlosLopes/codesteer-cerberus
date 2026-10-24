"""V5 superfície, V-CLI e policy_profile omitido no legado."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from assertion_guard import APROVA, APROVA_COM_PROVA, REJEITA, comparar_superficie, gate
from guard import avaliar
from validate_evidence import validar

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _baseline(tmp: Path, hashes: dict) -> dict:
    return {
        "schema_version": 1,
        "origin_revision": "host-rev-1",
        "content_hashes": hashes,
        "authorized_root": str(tmp),
        "tests": [{
            "test_id": "t1",
            "assertions": [{
                "target": "heading",
                "matcher": "toBeVisible",
                "arguments": "()",
                "context": "smoke",
            }],
        }],
        "truth_source": "observed",
        "policy_profile": "legacy",
        "extracted_at": "2026-10-24T22:00:00Z",
    }


def test_v5_import_dinamico(tmp_path: Path):
    (tmp_path / "a.spec.ts").write_text(
        "const m = await import('./helper.ts');\n", encoding="utf-8",
    )
    v = comparar_superficie(_baseline(tmp_path, {}), tmp_path)
    assert v.exit_code == REJEITA
    assert "dinâmico" in v.reason


def test_v5_fixture_alterada(tmp_path: Path):
    fx = tmp_path / "fixtures.ts"
    fx.write_text("export const x = 1;\n", encoding="utf-8")
    hashes = {"fixtures.ts": "sha256:" + ("0" * 64)}
    v = comparar_superficie(_baseline(tmp_path, hashes), tmp_path)
    assert v.exit_code == REJEITA
    assert "fixture" in v.reason


def test_v5_baseline_do_candidato(tmp_path: Path):
    man = tmp_path / "baseline.json"
    payload = _baseline(tmp_path, {})
    man.write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "t.spec.ts").write_text("export {};\n", encoding="utf-8")
    v = comparar_superficie(payload, tmp_path, manifesto_path=man)
    assert v.exit_code == REJEITA
    assert "candidato" in v.reason


def test_v5_po_locator_exige_exit_2(tmp_path: Path):
    po = tmp_path / "app.page.ts"
    po.write_text("export const x = page.getByTestId('novo');\n", encoding="utf-8")
    hashes = {"app.page.ts": "sha256:" + ("a" * 64)}
    v = comparar_superficie(_baseline(tmp_path, hashes), tmp_path)
    assert v.exit_code == APROVA_COM_PROVA
    assert "alvo_dominio" in v.detail


def test_v5_manifesto_incompleto(tmp_path: Path):
    v = comparar_superficie({"schema_version": 1}, tmp_path)
    assert v.exit_code == REJEITA


def test_exit2_traz_alvo_dominio():
    antes = (
        b"// intent: x\n"
        b"test('t', async ({ page }) => {"
        b" await expect(page.getByTestId('cel')).toHaveText('A'); });"
    )
    depois = (
        b"// intent: x\n"
        b"test('t', async ({ page }) => {"
        b" await expect(page.getByRole('row').getByTestId('cel')).toHaveText('A'); });"
    )
    v = gate(antes, depois)
    assert v.exit_code == APROVA_COM_PROVA
    assert "alvo_dominio" in v.detail
    assert v.detail["alvo_dominio"]["papel_ou_testid"].startswith(("testid:", "role:"))


def test_vcli_guard_sem_args():
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "guard.py")],
        capture_output=True, text=True,
    )
    assert r.returncode == 3


def test_vcli_assertion_sem_args():
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "assertion_guard.py")],
        capture_output=True, text=True,
    )
    assert r.returncode == 3


def test_vcli_lint_sem_args():
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "spec_lint.py")],
        capture_output=True, text=True,
    )
    assert r.returncode == 3


def test_json_legado_omite_policy_profile():
    d = avaliar(url="http://localhost:3000", mode="regression")
    assert d.approved
    assert d.policy_profile is None
    dumped = json.dumps(d.__dict__)
    # emit() omite; o campo interno None não vaza no JSON público
    from io import StringIO
    import contextlib
    buf = StringIO()
    with contextlib.redirect_stdout(buf):
        d.emit()
    payload = json.loads(buf.getvalue())
    assert "policy_profile" not in payload


def test_policy_example_valida():
    payload = json.loads((EXAMPLES / "project-policy.json").read_text(encoding="utf-8"))
    assert validar("policy", payload) == []
