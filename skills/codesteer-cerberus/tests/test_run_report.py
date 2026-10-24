"""V8 / V11 / V12 / V13 — pós-processador sem browser."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from run_report import (
    comparar_pacotes,
    conciliar_inventarios,
    emitir_mapa,
    emitir_pacote,
    metricas_rf19,
    validar_proveniencia,
    validar_triagem,
    verificar_completude_ci,
)
from validate_evidence import ValidationError


def _pkg(**over):
    base = {
        "schema_version": 1,
        "run_id": "run-1",
        "test_id": "t1",
        "project": "chromium",
        "attempt": 1,
        "mode": "smoke",
        "policy": "legacy",
        "suite_revision": "rev-1",
        "target": "http://127.0.0.1:4173/",
        "inventories": {
            "expected": ["t1"],
            "selected": ["t1"],
            "executed": ["t1"],
            "exclusions": [],
        },
        "source_executed": {"path": "evals/a.spec.ts", "hash": "sha256:aa"},
        "artifacts": [
            {"path": "trace.zip", "hash": "sha256:bb", "present": True},
        ],
        "finalized_at": "2026-10-24T22:00:00Z",
    }
    base.update(over)
    return base


def test_v8_product_bug_em_regression():
    erros = validar_triagem({
        "schema_version": 1,
        "classification": "PRODUCT_BUG",
        "mode": "regression",
        "test_id": "t1",
        "intent": "x",
        "evidences": ["trace"],
        "evidence_package_ref": "run-1/t1/chromium/1",
    })
    assert any("PRODUCT_BUG" in e for e in erros)


def test_v8_product_bug_sem_citacao():
    erros = validar_triagem({
        "schema_version": 1,
        "classification": "PRODUCT_BUG",
        "mode": "spec-driven",
        "test_id": "t1",
        "intent": "x",
        "evidences": ["trace"],
        "evidence_package_ref": "run-1/t1/chromium/1",
        "truth_ref": "cadastro.spec.md",
        "source_hash": "sha256:aa",
        "contradiction": True,
    })
    assert any("citation" in e for e in erros)


def test_v8_spec_driven_aceito():
    erros = validar_triagem({
        "schema_version": 1,
        "classification": "PRODUCT_BUG",
        "mode": "spec-driven",
        "test_id": "t1",
        "intent": "x",
        "evidences": ["o status Ativo não apareceu"],
        "evidence_package_ref": "run-1/t1/chromium/1",
        "truth_ref": "cadastro.spec.md",
        "citation": "o registro aparece na lista com status Ativo",
        "source_hash": "sha256:aa",
        "contradiction": True,
    })
    assert erros == []


def test_v8_redirect_login_sem_evidencia():
    erros = validar_triagem({
        "schema_version": 1,
        "classification": "TEST_DRIFT",
        "mode": "regression",
        "test_id": "t1",
        "intent": "x",
        "evidences": ["redirect /login"],
        "evidence_package_ref": "run-1/t1/chromium/1",
    })
    assert any("UNCLASSIFIED" in e for e in erros)


def test_v11_mix_e_trace_ausente(tmp_path: Path):
    pkg = _pkg(artifacts=[{"path": "shot.png", "hash": "sha256:cc", "present": True}])
    erros = validar_proveniencia(pkg, tmp_path)
    assert any("trace" in e for e in erros)


def test_v11_anexo_fora_da_raiz(tmp_path: Path):
    fora = tmp_path.parent / "outside-trace.zip"
    fora.write_text("x", encoding="utf-8")
    pkg = _pkg(artifacts=[{
        "path": str(fora), "hash": "sha256:cc", "present": True,
    }])
    erros = validar_proveniencia(pkg, tmp_path)
    assert any("fora da raiz" in e for e in erros)


def test_v11_symlink_fora(tmp_path: Path):
    fora = tmp_path.parent / "out-trace.zip"
    fora.write_text("x", encoding="utf-8")
    link = tmp_path / "trace.zip"
    link.symlink_to(fora)
    pkg = _pkg(artifacts=[{
        "path": str(link), "hash": "sha256:cc", "present": True,
    }])
    erros = validar_proveniencia(pkg, tmp_path)
    assert any("fora da raiz" in e for e in erros)


def test_v11_reproducao_com_vinculo():
    a = _pkg()
    b = _pkg(run_id="run-2", original_failure_ref="run-1/t1/chromium/1")
    assert comparar_pacotes(a, b) == []


def test_v11_source_executed_ausente(tmp_path: Path):
    trace = tmp_path / "trace.zip"
    trace.write_bytes(b"trace")
    digest = "sha256:" + hashlib.sha256(b"trace").hexdigest()
    pkg = _pkg(
        source_executed={
            "path": str(tmp_path / "missing.spec.ts"),
            "hash": "sha256:" + ("a" * 64),
        },
        artifacts=[{"path": str(trace), "hash": digest, "present": True}],
    )
    erros = validar_proveniencia(pkg, tmp_path)
    assert any("hash divergente em source_executed" in e for e in erros)


def test_v11_source_executed_fora_da_raiz(tmp_path: Path):
    fora = tmp_path.parent / "outside.spec.ts"
    fora.write_text("export {};\n", encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(fora.read_bytes()).hexdigest()
    pkg = _pkg(source_executed={"path": str(fora), "hash": digest})
    erros = validar_proveniencia(pkg, tmp_path)
    assert any("source_executed fora da raiz" in e for e in erros)


def test_v11_hash_aplicado_diverge():
    erros = validar_triagem({
        "schema_version": 1,
        "classification": "TEST_DRIFT",
        "mode": "regression",
        "test_id": "t1",
        "intent": "x",
        "evidences": ["locator"],
        "evidence_package_ref": "run-1/t1/chromium/1",
        "applied_hash": "sha256:aa",
        "validated_hash": "sha256:bb",
        "authorizes_healing": True,
    })
    assert any("hash aplicado" in e for e in erros)


def test_v11_pacote_finalizado_imutavel(tmp_path: Path):
    run = tmp_path / "run-1"
    reports = run / "reports"
    reports.mkdir(parents=True)
    pkg = _pkg()
    (reports / "evidence-package.json").write_text(json.dumps(pkg), encoding="utf-8")
    with pytest.raises(ValidationError):
        emitir_pacote(_pkg(attempt=2), run, tmp_path)


def test_v12_id_duplicado():
    from validate_evidence import validar
    mapa = {
        "schema_version": 1,
        "suite_revision": "r",
        "requested_scope": 2,
        "authorized_scope": 2,
        "entries": [
            {"origin": "observed", "discovery": "explored", "stage": "generated",
             "feature": "a", "scenario": "s", "test_id": "t1"},
            {"origin": "observed", "discovery": "blocked", "stage": "proposed",
             "feature": "a", "scenario": "s2", "test_id": "t1"},
        ],
        "exclusions": [],
    }
    erros = validar("coverage", mapa)
    assert any("duplicado" in e for e in erros)


def test_v12_denominador_zero_na(tmp_path: Path):
    mapa = {
        "schema_version": 1,
        "suite_revision": "r",
        "requested_scope": 0,
        "authorized_scope": 0,
        "entries": [{
            "origin": "observed", "discovery": "partial", "stage": "proposed",
            "feature": "a", "scenario": "s", "test_id": "t1",
        }],
        "exclusions": [],
    }
    out = emitir_mapa(mapa, tmp_path / "run")
    assert out["coverage_ratio"] == "N/A"
    assert (tmp_path / "run" / "reports" / "coverage.md").is_file()


def test_v12_selecao_zero():
    erros = conciliar_inventarios(["t1"], [], [], [])
    assert any("seleção zero" in e for e in erros)


def test_v13_ci_nao_demonstrado():
    erros = verificar_completude_ci({
        "url": "http://127.0.0.1:4173",
        "expected_sha": "abc",
        "deployment_identity": {"sha": "abc", "demonstrated": False},
        "policy": {"origins": {"local": "http://127.0.0.1:4173"}},
        "expected": ["t1"],
        "selected": ["t1"],
        "executed": ["t1"],
        "exclusions": [],
        "readiness_status": 200,
    })
    assert any("não demonstrado" in e for e in erros)


def test_v13_readiness_5xx_e_reporter():
    erros = verificar_completude_ci({
        "url": "http://127.0.0.1:4173",
        "deployment_identity": {"sha": "abc", "demonstrated": True},
        "expected_sha": "abc",
        "policy": {"origins": {"local": "http://127.0.0.1:4173"}},
        "expected": ["t1"],
        "selected": ["t1"],
        "executed": ["t1"],
        "exclusions": [],
        "readiness_status": 503,
        "inventory_from_reporter": True,
        "interrupted": True,
        "old_report_releases_new_commit": True,
    })
    assert any("5xx" in e for e in erros)
    assert any("reporter" in e for e in erros)
    assert any("interrompida" in e for e in erros)
    assert any("commit novo" in e for e in erros)


def test_metricas_denominador_zero():
    m = metricas_rf19([])
    assert m["hidden_failures"]["ratio"] == "N/A"


def test_nao_substitui_relatorios_humanos(tmp_path: Path):
    run = tmp_path / "run-1"
    reports = run / "reports"
    reports.mkdir(parents=True)
    for nome in ("summary.md", "mutations.diff", "bug_report.md", "escalations.md"):
        (reports / nome).write_text("keep\n", encoding="utf-8")
    # emit mapa only
    emitir_mapa({
        "schema_version": 1,
        "suite_revision": "r",
        "requested_scope": 1,
        "authorized_scope": 1,
        "entries": [{
            "origin": "observed", "discovery": "explored", "stage": "executed",
            "feature": "a", "scenario": "s", "test_id": "t1",
        }],
        "exclusions": [],
    }, run)
    for nome in ("summary.md", "mutations.diff", "bug_report.md", "escalations.md"):
        assert (reports / nome).read_text(encoding="utf-8") == "keep\n"
