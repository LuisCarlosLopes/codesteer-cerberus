"""V10 — corpus 24+8, held-out separado, métricas com denominador."""

from __future__ import annotations

import json
from pathlib import Path

from run_report import metricas_rf19
from validate_evidence import validar

CATALOG = Path(__file__).resolve().parents[1] / "evals" / "corpus" / "catalog.json"
POLICY = Path(__file__).resolve().parents[1] / "references" / "evaluation-policy.md"


def test_v10_corpus_24_mais_8():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert len(data["dev"]) == 24
    assert len(data["held_out"]) == 8
    dev_ids = {s["scenario_id"] for s in data["dev"]}
    hold_ids = {s["scenario_id"] for s in data["held_out"]}
    assert dev_ids.isdisjoint(hold_ids)
    classes = {s["class"] for s in data["dev"]}
    assert len(classes) == 6
    for s in data["dev"] + data["held_out"]:
        assert s["expected_label"]
        assert s["label_source"]
        assert s["justification"]
        assert "agente" not in s["label_source"].lower()


def test_v10_held_out_nao_treina():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert all(s["set"] == "held_out" for s in data["held_out"])
    assert all(s["set"] == "dev" for s in data["dev"])


def test_v10_metricas_e_promocao():
    m = metricas_rf19([])
    assert m["hidden_failures"]["ratio"] == "N/A"
    registro = {
        "schema_version": 1,
        "scenario_id": "hold-05",
        "set": "held_out",
        "expected_label": "REJEITA",
        "label_source": "fixture",
        "attempts": [],
        "expected_label_from_agent": True,
    }
    assert validar("evaluation", registro)
    texto = POLICY.read_text(encoding="utf-8")
    assert "held-out" in texto.lower() or "held_out" in texto
    assert "SDK" in texto or "sdk" in texto.lower()
    catalog = CATALOG.read_text(encoding="utf-8")
    assert "sk-" not in catalog
    assert "api_key" not in catalog
