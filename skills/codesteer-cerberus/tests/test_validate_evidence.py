"""Fail-closed dos schemas v1 — T3 / V-SEC / CA19."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from validate_evidence import validar

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("kind,filename", [
    ("policy", "project-policy.json"),
    ("evidence", "run-manifest.json"),
    ("coverage", "coverage-map.json"),
])
def test_exemplos_validos(kind, filename):
    payload = _load(filename)
    assert validar(kind, payload) == []


@pytest.mark.parametrize("kind,filename", [
    ("policy", "project-policy.json"),
    ("evidence", "run-manifest.json"),
    ("coverage", "coverage-map.json"),
])
def test_versao_desconhecida(kind, filename):
    payload = _load(filename)
    payload["schema_version"] = 99
    erros = validar(kind, payload)
    assert erros
    assert any("desconhecida" in e for e in erros)


@pytest.mark.parametrize("kind,filename,campo", [
    ("policy", "project-policy.json", "content_hash"),
    ("evidence", "run-manifest.json", "run_id"),
    ("coverage", "coverage-map.json", "entries"),
    ("baseline", None, "origin_revision"),
    ("triage", None, "evidence_package_ref"),
    ("evaluation", None, "expected_label"),
])
def test_campo_obrigatorio_ausente(kind, filename, campo):
    if filename:
        payload = _load(filename)
    else:
        payload = {"schema_version": 1}
    payload.pop(campo, None)
    erros = validar(kind, payload)
    assert any(campo in e for e in erros)


def test_credencial_rejeitada():
    payload = _load("project-policy.json")
    payload["password"] = "hunter2"
    erros = validar("policy", payload)
    assert any("credencial" in e for e in erros)


def test_token_literal_rejeitado():
    payload = _load("run-manifest.json")
    payload["artifacts"][0]["hash"] = "ghp_abcdefghijklmnopqrstuvwxyz012345"
    erros = validar("evidence", payload)
    assert any("credencial" in e for e in erros)


def test_baseline_minima():
    payload = {
        "schema_version": 1,
        "origin_revision": "rev-1",
        "content_hashes": {"a.spec.ts": "sha256:aa"},
        "authorized_root": "skills/codesteer-cerberus/evals",
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
    assert validar("baseline", payload) == []


def test_triage_product_bug_em_smoke():
    payload = {
        "schema_version": 1,
        "classification": "PRODUCT_BUG",
        "mode": "smoke",
        "test_id": "t1",
        "intent": "x",
        "evidences": [],
        "evidence_package_ref": "run/t1/chromium/1",
        "truth_ref": "spec.md",
        "citation": "CA-01",
        "source_hash": "sha256:aa",
        "contradiction": True,
    }
    erros = validar("triage", payload)
    assert any("PRODUCT_BUG" in e for e in erros)


def test_exemplos_sem_alvo_remoto():
    blob = (EXAMPLES / "project-policy.json").read_text(encoding="utf-8")
    blob += (EXAMPLES / "run-manifest.json").read_text(encoding="utf-8")
    blob += (EXAMPLES / "coverage-map.json").read_text(encoding="utf-8")
    assert "vercel.app" not in blob
    assert "sun-cash-tracker" not in blob
