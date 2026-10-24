#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["tree-sitter>=0.26", "tree-sitter-typescript>=0.23"]
# ///
"""
assertion_guard.py — o GATE do self-healing.

Impede que a correção automática de um teste altere aquilo que o teste prova.
Um loop que edita o teste quando o teste falha converge para a suíte que sempre
passa. Este script é a barreira contra esse atrator, e é 100% determinístico:
nenhuma inferência, nenhum modelo, mesmo resultado sempre.

DECOMPOSIÇÃO CENTRAL
--------------------
    await expect( page.getByRole('row').filter(...).getByTestId('cel') ).toHaveText('A')
                  └──────────────── LOCATOR ────────────────┘  └───── MATCHER ─────┘
                        endereçamento — MUTÁVEL                  semântica — CONGELADO

    Matcher (nome, argumentos, negação)  → congelado
    Contagem de asserções                → congelada
    Locator DENTRO de expect()           → mutável SOB PROVA (exit 2)
    Locator FORA de expect() (ações)     → livre

INVARIANTE DO POM
-----------------
Este gate só funciona porque as asserções vivem nos arquivos `.spec.ts`.
Sob Page Object Model, um `expect()` que migra para dentro de um `.page.ts`
sai do campo de visão do gate — e o healing ganha uma rota livre para
enfraquecer o teste. Por isso `--check-po` existe: ele protege a premissa.

O HEADER `// intent:`
---------------------
Todo `.spec.ts` declara, ao lado dos `// spec:` e `// seed:` do fluxo oficial:

    // intent: produto criado aparece na lista como Ativo

O gate **lê esse valor dos dois arquivos**. Ele nunca o recebe por argumento —
um guarda cujo valor de referência é fornecido por quem está sendo guardado
não guarda nada. Reescrever ou remover o header é rejeitado.

USO
---
    uv run assertion_guard.py <antes.ts> <depois.ts>
    uv run assertion_guard.py <antes.ts> <depois.ts> --sem-intent   # suíte legada
    uv run assertion_guard.py --check-po tests/
    uv run assertion_guard.py --self-test

EXIT CODES
----------
    0  APROVA              patch pode ser aplicado
    1  REJEITA             patch viola a política — descarte e escale
    2  APROVA_COM_PROVA    locator de asserção mudou; exige prova de mesmo
                           elemento no trace antes de aplicar
    3  ERRO_DE_USO
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

from suite_model import (
    MAX_TIMEOUT_MS,
    casos_por_id,
    enriquecer_matcher,
    extrair_intent,
    parse_suite,
)

APROVA, REJEITA, APROVA_COM_PROVA, ERRO_DE_USO = 0, 1, 2, 3


class GateError(Exception):
    """Falha de análise. Sempre resulta em rejeição (fail-closed)."""


@dataclass(frozen=True)
class Assercao:
    matcher: str
    locator: str


@dataclass
class Verdict:
    decision: str          # APROVA | REJEITA | APROVA_COM_PROVA
    exit_code: int
    reason: str
    detail: dict

    def emit(self) -> int:
        print(json.dumps(asdict(self), ensure_ascii=False, indent=2))
        return self.exit_code


def decompor(source: bytes) -> list[Assercao]:
    """Extrai (matcher, locator) de cada asserção do arquivo.

    Matcher preserva literais (espaço, aspas, escape, template, regex).
    Timeout de opção de matcher não entra na identidade; timeout que mora
    dentro de dado do matcher permanece. Comparação por teste vive em `gate`.
    """
    suite = parse_suite(source)
    if suite.parse_error:
        raise GateError("arquivo não parseia como TypeScript")
    return [
        Assercao(
            matcher=enriquecer_matcher(a.matcher, a.locator, suite.bindings),
            locator=a.locator,
        )
        for a in suite.assertions
    ]


def modificadores(source: bytes) -> set[str]:
    suite = parse_suite(source)
    if suite.parse_error:
        return set()
    return set(suite.modifiers)


def contar_steps(source: bytes) -> int:
    """Awaits que não são asserções — proxy para as ações do teste."""
    suite = parse_suite(source)
    if suite.parse_error:
        raise GateError("arquivo não parseia como TypeScript")
    return suite.steps


def _matcher_de(suite, assercao) -> str:
    return enriquecer_matcher(assercao.matcher, assercao.locator, suite.bindings)


def gate(antes: bytes, depois: bytes, exigir_intent: bool = True) -> Verdict:
    # @MindContext: Gate de healing compara prova por teste/alvo/ordem e rejeita
    # wrapper, rebind e forma não suportada — sem equivalência semântica de TS.
    # @MindSpec: Input: dois fontes + exigir_intent | Output: Verdict 0/1/2 | Error: 3 só na CLI
    # @MindDecision: Listas globais ordenadas de matcher deixam de autorizar APROVA.
    # 0. A intenção declarada do teste é congelada.
    #    Ambos os valores vêm dos ARQUIVOS, não de argumentos de linha de comando.
    intent_antes = extrair_intent(antes)
    intent_depois = extrair_intent(depois)

    if exigir_intent and intent_antes is None:
        return Verdict(
            "REJEITA", REJEITA,
            "arquivo original não declara `// intent:` — sem ele não há o que "
            "congelar. Adicione o header antes de qualquer healing.",
            {"exemplo": "// intent: produto criado aparece na lista como Ativo"},
        )

    if intent_antes is not None and intent_depois is None:
        return Verdict("REJEITA", REJEITA,
                       "o header `// intent:` foi removido do arquivo",
                       {"antes": intent_antes})

    if intent_antes != intent_depois:
        return Verdict("REJEITA", REJEITA, "o `// intent:` do teste foi alterado",
                       {"antes": intent_antes, "depois": intent_depois})

    # 1. Fail-closed: o que não se analisa não se aprova.
    sa, sd = parse_suite(antes), parse_suite(depois)
    if sa.parse_error or sd.parse_error:
        return Verdict("REJEITA", REJEITA,
                       "fail-closed: arquivo não parseia como TypeScript", {})

    if sd.expect_rebound:
        return Verdict("REJEITA", REJEITA, "rebind de expect", {})

    if sd.unsupported:
        return Verdict("REJEITA", REJEITA, "forma não suportada",
                       {"formas": sd.unsupported})

    for caso in sd.tests:
        for assercao in caso.assertions:
            if assercao.unsupported:
                return Verdict("REJEITA", REJEITA, "forma não suportada",
                               {"detalhe": assercao.unsupported})
            if assercao.wrapped:
                return Verdict("REJEITA", REJEITA, assercao.wrapped, {})

    try:
        a, d = decompor(antes), decompor(depois)
        steps_antes, steps_depois = sa.steps, sd.steps
    except GateError as e:
        return Verdict("REJEITA", REJEITA, f"fail-closed: {e}", {})

    # 2. Contagem de asserções é congelada.
    if len(a) != len(d):
        return Verdict("REJEITA", REJEITA, "número de asserções mudou",
                       {"antes": len(a), "depois": len(d)})

    # 3. Semântica por teste, alvo e ordem — não por lista global ordenada.
    mapa_a, mapa_d = casos_por_id(sa), casos_por_id(sd)
    if set(mapa_a) != set(mapa_d):
        return Verdict("REJEITA", REJEITA, "identidade de teste mudou",
                       {"antes": sorted(mapa_a), "depois": sorted(mapa_d)})

    for tid, ta in mapa_a.items():
        td = mapa_d[tid]
        if len(ta.assertions) != len(td.assertions):
            return Verdict("REJEITA", REJEITA, "número de asserções mudou",
                           {"test_id": tid,
                            "antes": len(ta.assertions),
                            "depois": len(td.assertions)})
        for xa, xd in zip(ta.assertions, td.assertions):
            ma, md = _matcher_de(sa, xa), _matcher_de(sd, xd)
            if ma != md:
                return Verdict("REJEITA", REJEITA, "matcher alterado",
                               {"test_id": tid, "antes": ma, "depois": md})

    # 4. skip / fixme / only nunca podem ser introduzidos.
    novos_mod = set(sd.modifiers) - set(sa.modifiers)
    if novos_mod:
        return Verdict("REJEITA", REJEITA, "modificador proibido introduzido",
                       {"modificadores": sorted(novos_mod)})

    # 5. Steps não podem desaparecer.
    if steps_depois < steps_antes:
        return Verdict("REJEITA", REJEITA, "steps removidos",
                       {"antes": steps_antes, "depois": steps_depois})

    # 6. Timeout tem teto (ajuste de opção — não literal de dado).
    if (excedidos := [v for v in sd.timeouts if v > MAX_TIMEOUT_MS]):
        return Verdict("REJEITA", REJEITA, f"timeout acima do teto de {MAX_TIMEOUT_MS}ms",
                       {"valores": excedidos})

    # 7. Locator dentro da asserção mudou → exige prova de mesmo alvo de domínio.
    trocas = []
    for tid, ta in mapa_a.items():
        td = mapa_d[tid]
        for xa, xd in zip(ta.assertions, td.assertions):
            if xa.locator != xd.locator:
                trocas.append({"test_id": tid, "antes": xa.locator, "depois": xd.locator})
    if trocas:
        return Verdict(
            "APROVA_COM_PROVA", APROVA_COM_PROVA,
            "locator de asserção mudou — confirme no trace que o locator novo "
            "resolve para o MESMO alvo de domínio antes de aplicar",
            {"trocas": trocas, "alvo_dominio": inferir_alvo_dominio(trocas[0]["depois"])},
        )

    return Verdict("APROVA", APROVA, "nenhuma violação de política", {})


def inferir_alvo_dominio(locator: str) -> dict:
    testid = re.search(r"getByTestId\(\s*['\"]([^'\"]+)", locator)
    role = re.search(r"getByRole\(\s*['\"]([^'\"]+)", locator)
    name = re.search(r"name:\s*['\"]([^'\"]+)", locator)
    entidade = (name.group(1) if name else
                (testid.group(1) if testid else "desconhecida"))
    if role:
        papel = f"role:{role.group(1)}" + (f":{name.group(1)}" if name else "")
    elif testid:
        papel = f"testid:{testid.group(1)}"
    else:
        papel = "desconhecido"
    return {
        "entidade": entidade,
        "papel_ou_testid": papel,
        "cardinalidade": "one",
        "escopo": "pagina",
    }


def _sha256(caminho: Path) -> str:
    return "sha256:" + hashlib.sha256(caminho.read_bytes()).hexdigest()


_PROTECTED = ("fixture", "mock", "playwright.config", "storagestate", "global-setup")


def comparar_superficie(
    manifesto: dict,
    surface: Path,
    evidencias: dict | None = None,
    manifesto_path: Path | None = None,
) -> Verdict:
    """Compara a superfície candidata ao ManifestoDeBaseline do host.

    @MindSpec: Sem manifesto suficiente, baseline do candidato, import dinâmico,
    import fora da raiz, helper/PO novo ou ausente, ou mudança de fixture/config
    → REJEITA. Locator em PO/helper já hasheado → no mínimo exit 2.
    """
    from validate_evidence import validar

    erros = validar("baseline", manifesto)
    if erros:
        return Verdict("REJEITA", REJEITA, "manifesto de baseline insuficiente",
                       {"errors": erros})
    if not surface.exists():
        return Verdict("REJEITA", REJEITA, "superfície candidata inexistente",
                       {"surface": str(surface)})
    if manifesto_path is not None:
        try:
            manifesto_path.resolve().relative_to(surface.resolve())
            return Verdict(
                "REJEITA", REJEITA,
                "baseline sob controle do candidato — hash local não aprova",
                {"baseline": str(manifesto_path)},
            )
        except ValueError:
            pass

    hashes = manifesto.get("content_hashes") or {}
    root = Path(manifesto["authorized_root"])
    trocas_po = []
    for path in sorted(p for p in surface.rglob("*") if p.is_file()):
        if IGNORAR & set(path.parts):
            continue
        rel = path.relative_to(surface).as_posix()
        nome = (rel + " " + path.name).lower()
        if path.suffix in {".ts", ".js", ".tsx"}:
            suite = parse_suite(
                path.read_bytes(), str(path), authorized_root=root,
            )
            if any(imp.dynamic for imp in suite.imports):
                return Verdict("REJEITA", REJEITA, "import dinâmico",
                               {"arquivo": rel})
            if any(imp.outside_root for imp in suite.imports):
                return Verdict("REJEITA", REJEITA, "dependência fora da raiz",
                               {"arquivo": rel})
        protegido = any(h in nome for h in _PROTECTED)
        esperado = hashes.get(rel)
        atual = _sha256(path) if path.is_file() else None
        if protegido and esperado != atual:
            return Verdict(
                "REJEITA", REJEITA,
                "fixture, mock, config ou seleção alterados sem revisão",
                {"arquivo": rel},
            )
        eh_po = path.match("*.page.ts") or path.match("*.po.ts") or "helper" in nome
        if eh_po and esperado != atual:
            if not esperado:
                return Verdict(
                    "REJEITA", REJEITA,
                    "helper/PO novo sem baseline do host",
                    {"arquivo": rel},
                )
            trocas_po.append(rel)

    for rel, _esperado in hashes.items():
        if not (surface / rel).is_file():
            return Verdict(
                "REJEITA", REJEITA,
                "arquivo da baseline ausente na superfície",
                {"arquivo": rel},
            )

    if trocas_po:
        prova = bool(evidencias and evidencias.get("mesmo_alvo"))
        if not prova:
            return Verdict(
                "APROVA_COM_PROVA", APROVA_COM_PROVA,
                "locator em PO/helper mudou — exige prova de mesmo alvo e "
                "impacto nos specs dependentes. Ausência de expect no PO "
                "não autoriza a troca.",
                {"arquivos": trocas_po, "alvo_dominio": inferir_alvo_dominio("")},
            )
        return Verdict(
            "APROVA_COM_PROVA", APROVA_COM_PROVA,
            "locator em PO/helper mudou com evidência de mesmo alvo de domínio",
            {"arquivos": trocas_po, "alvo_dominio": evidencias.get("alvo_dominio")
             if evidencias else inferir_alvo_dominio("")},
        )

    return Verdict("APROVA", APROVA, "superfície alinhada à baseline do host", {})


# ------------------------------------------------------- invariante do POM

# Arquivos tratados como page objects.
PADROES_PO = ("*.page.ts", "*.po.ts")
# Diretórios ignorados na varredura.
IGNORAR = {"node_modules", ".git", "dist", "build", ".e2e-engine"}


def achar_page_objects(raiz: Path) -> list[Path]:
    if raiz.is_file():
        return [raiz]
    achados: list[Path] = []
    for padrao in PADROES_PO:
        achados += [
            p for p in raiz.rglob(padrao)
            if not (IGNORAR & set(p.parts))
        ]
    return sorted(set(achados))


def check_po(raiz: Path) -> int:
    """Falha se algum page object contiver asserção.

    Sob a convenção desta skill, o page object expõe locators e ações; o que
    o teste PROVA fica visível no `.spec.ts`. Asserção dentro do PO cega o
    gate e esconde a prova do leitor do teste.
    """
    arquivos = achar_page_objects(raiz)
    if not arquivos:
        print(json.dumps({
            "decision": "APROVA",
            "reason": f"nenhum page object encontrado em {raiz}",
            "detail": {"padroes": list(PADROES_PO)},
        }, ensure_ascii=False, indent=2))
        return APROVA

    violacoes = []
    for arq in arquivos:
        try:
            achadas = decompor(arq.read_bytes())
        except GateError as e:
            violacoes.append({"arquivo": str(arq), "erro": str(e)})
            continue
        if achadas:
            violacoes.append({
                "arquivo": str(arq),
                "assercoes": [f"expect{a.locator}.{a.matcher}" for a in achadas],
            })

    if violacoes:
        print(json.dumps({
            "decision": "REJEITA",
            "reason": "page object contém asserção — o gate ficaria cego e a "
                      "prova do teste, escondida. Mova o expect() para o .spec.ts",
            "detail": {"arquivos_verificados": len(arquivos),
                       "violacoes": violacoes},
        }, ensure_ascii=False, indent=2))
        return REJEITA

    print(json.dumps({
        "decision": "APROVA",
        "reason": "nenhuma asserção em page object; invariante preservado",
        "detail": {"arquivos_verificados": len(arquivos),
                   "arquivos": [str(a) for a in arquivos]},
    }, ensure_ascii=False, indent=2))
    return APROVA


# ---------------------------------------------------------------- self-test

INTENT_PADRAO = "produto criado aparece na lista como Ativo"


def _t(corpo: str, intent: str | None = INTENT_PADRAO) -> bytes:
    cabecalho = f"// intent: {intent}\n" if intent else ""
    return f"{cabecalho}test('t', async ({{ page }}) => {{{corpo}}});".encode()


CASOS = [
    ("troca de locator em ação", _t(
        "await page.getByTestId('novo').click();"
        " await expect(page.getByTestId('lin')).toBeVisible();"), _t(
        "await page.getByRole('button', { name: 'Novo' }).click();"
        " await expect(page.getByTestId('lin')).toBeVisible();"), "APROVA"),

    # Espera web-first é permitida. Note que `networkidle` NÃO é usado aqui:
    # a skill oficial playwright-cli o desaconselha explicitamente.
    ("adiciona espera web-first", _t(
        "await page.getByTestId('a').click();"
        " await expect(page.getByTestId('x')).toBeVisible();"), _t(
        "await page.getByTestId('a').click();"
        " await page.getByTestId('spinner').waitFor({ state: 'hidden' });"
        " await expect(page.getByTestId('x')).toBeVisible();"), "APROVA"),

    ("timeout dentro do teto", _t(
        "await expect(page.getByTestId('x')).toBeVisible();"), _t(
        "await expect(page.getByTestId('x')).toBeVisible({ timeout: 15000 });"), "APROVA"),

    ("row-scoping dentro da asserção", _t(
        "await expect(page.getByTestId('cel')).toHaveText('A');"), _t(
        "await expect(page.getByRole('row').filter({ hasText: 'A' })"
        ".getByTestId('cel')).toHaveText('A');"), "APROVA_COM_PROVA"),

    ("remove asserção", _t(
        "await page.goto('/');"
        " await expect(page.getByTestId('x')).toBeVisible();"), _t(
        "await page.goto('/');"), "REJEITA"),

    ("afrouxa matcher", _t(
        "await expect(page.getByTestId('x')).toBeVisible();"), _t(
        "await expect(page.getByTestId('x')).toBeAttached();"), "REJEITA"),

    ("muda valor esperado", _t(
        "await expect(page.getByTestId('t')).toHaveText('10');"), _t(
        "await expect(page.getByTestId('t')).toHaveText('0');"), "REJEITA"),

    ("nega asserção", _t(
        "await expect(page.getByTestId('x')).toBeVisible();"), _t(
        "await expect(page.getByTestId('x')).not.toBeVisible();"), "REJEITA"),

    ("introduz skip",
     _t("await page.goto('/'); await expect(page.getByTestId('x')).toBeVisible();"),
     b"test.skip('t', async ({ page }) => { await page.goto('/');"
     b" await expect(page.getByTestId('x')).toBeVisible(); });", "REJEITA"),

    ("remove step", _t(
        "await page.goto('/'); await page.getByTestId('a').click();"
        " await expect(page.getByTestId('x')).toBeVisible();"), _t(
        "await page.goto('/');"
        " await expect(page.getByTestId('x')).toBeVisible();"), "REJEITA"),

    ("timeout acima do teto", _t(
        "await expect(page.getByTestId('x')).toBeVisible();"), _t(
        "await expect(page.getByTestId('x')).toBeVisible({ timeout: 120000 });"), "REJEITA"),

    ("sintaxe quebrada",
     _t("await expect(page.getByTestId('x')).toBeVisible();"),
     b"test('t', async ({ page }) => { await page.goto('/' ;;; ", "REJEITA"),

    ("opção semântica não é timeout", _t(
        "await expect(page.getByTestId('t')).toHaveText('A');"), _t(
        "await expect(page.getByTestId('t')).toHaveText('A', { ignoreCase: true });"),
     "REJEITA"),

    # --- o intent vem dos ARQUIVOS, não de argumentos ---------------------
    ("intent reescrito",
     _t("await expect(page.getByTestId('x')).toBeVisible();"),
     _t("await expect(page.getByTestId('x')).toBeVisible();",
        intent="a tela de produtos carrega"), "REJEITA"),

    ("intent removido",
     _t("await expect(page.getByTestId('x')).toBeVisible();"),
     _t("await expect(page.getByTestId('x')).toBeVisible();", intent=None),
     "REJEITA"),

    ("original sem intent",
     _t("await expect(page.getByTestId('x')).toBeVisible();", intent=None),
     _t("await expect(page.getByTestId('x')).toBeVisible();", intent=None),
     "REJEITA"),

    ("intent preservado com locator trocado",
     _t("await page.getByTestId('a').click();"
        " await expect(page.getByTestId('x')).toBeVisible();"),
     _t("await page.getByRole('button', { name: 'A' }).click();"
        " await expect(page.getByTestId('x')).toBeVisible();"), "APROVA"),

    # --- V1 wrappers que impedem a prova ---------------------------------
    ("V1 if (false) envolve expect",
     _t("await expect(page.getByTestId('x')).toBeVisible();"),
     _t("if (false) { await expect(page.getByTestId('x')).toBeVisible(); }"),
     "REJEITA"),
    ("V1 retorno antecipado",
     _t("await expect(page.getByTestId('x')).toBeVisible();"),
     _t("return; await expect(page.getByTestId('x')).toBeVisible();"),
     "REJEITA"),
    ("V1 callback morto",
     _t("await expect(page.getByTestId('x')).toBeVisible();"),
     _t("const fn = () => { expect(page.getByTestId('x')).toBeVisible(); };"),
     "REJEITA"),
    ("V1 catch vazio",
     _t("await expect(page.getByTestId('x')).toBeVisible();"),
     _t("try { await expect(page.getByTestId('x')).toBeVisible(); }"
        " catch (e) {}"),
     "REJEITA"),

    # --- V2 literais sem colapso semântico --------------------------------
    ("V2 espaço em literal",
     _t("await expect(page.getByTestId('t')).toHaveText('hello');"),
     _t("await expect(page.getByTestId('t')).toHaveText('hello ');"),
     "REJEITA"),
    ("V2 aspas do literal",
     _t("await expect(page.getByTestId('t')).toHaveText('A');"),
     _t('await expect(page.getByTestId(\'t\')).toHaveText("A");'),
     "REJEITA"),
    ("V2 formatação fora de literal",
     _t("await expect(page.getByTestId('x')).toBeVisible();"),
     _t("await expect( page.getByTestId('x') ).toBeVisible();"),
     "APROVA"),
    ("V2 timeout dentro do dado não é ajuste",
     _t("await expect(page.getByTestId('t')).toHaveText('timeout: 50000');"),
     _t("await expect(page.getByTestId('t')).toHaveText('timeout: 50000');"),
     "APROVA"),

    # --- V3 alvo, rebind, forma não suportada -----------------------------
    ("V3 troca de matcher entre alvos",
     _t("await expect(page.getByTestId('a')).toHaveText('A');"
        " await expect(page.getByTestId('b')).toBeVisible();"),
     _t("await expect(page.getByTestId('a')).toBeVisible();"
        " await expect(page.getByTestId('b')).toHaveText('A');"),
     "REJEITA"),
    ("V3 rebind de expect",
     _t("await expect(page.getByTestId('x')).toBeVisible();"),
     _t("const expect = () => ({ toBeVisible: () => {} });"
        " await expect(page.getByTestId('x')).toBeVisible();"),
     "REJEITA"),
    ("V3 variável esperada redefinida",
     _t("const esperado = 'A';"
        " await expect(page.getByTestId('t')).toHaveText(esperado);"),
     _t("const esperado = 'B';"
        " await expect(page.getByTestId('t')).toHaveText(esperado);"),
     "REJEITA"),
    ("V3 forma não suportada expect.soft",
     _t("await expect(page.getByTestId('x')).toBeVisible();"),
     _t("await expect.soft(page.getByTestId('x')).toBeVisible();"),
     "REJEITA"),
]


PO_LIMPO = b"""
import { type Page, type Locator } from '@playwright/test';
export class ProdutosPage {
  readonly novo: Locator;
  constructor(private readonly page: Page) {
    this.novo = page.getByTestId('produto-novo');
  }
  async goto() { await this.page.goto('/produtos'); }
  linhaDe(nome: string): Locator {
    return this.page.getByRole('row').filter({ hasText: nome });
  }
}
"""

PO_SUJO = b"""
import { type Page, expect } from '@playwright/test';
export class ProdutosPage {
  constructor(private readonly page: Page) {}
  async verificarStatus(esperado: string) {
    await expect(this.page.getByTestId('produto-status')).toHaveText(esperado);
  }
}
"""


def self_test() -> int:
    falhas = 0
    print(f"assertion_guard — self-test ({len(CASOS) + 2} casos)\n")
    for nome, antes, depois, esperado in CASOS:
        v = gate(antes, depois)
        ok = v.decision == esperado
        falhas += not ok
        print(f"  {'PASS' if ok else 'FALHA':5}  {nome:34} "
              f"esperado={esperado:17} obtido={v.decision}")

    # Invariante do POM: page object não pode conter asserção.
    for nome, fonte, espera_violacao in (
        ("PO sem asserção", PO_LIMPO, False),
        ("PO com asserção", PO_SUJO, True),
    ):
        tem = bool(decompor(fonte))
        ok = tem == espera_violacao
        falhas += not ok
        obtido = "REJEITA" if tem else "APROVA"
        esperado = "REJEITA" if espera_violacao else "APROVA"
        print(f"  {'PASS' if ok else 'FALHA':5}  {nome:34} "
              f"esperado={esperado:17} obtido={obtido}")

    print()
    if falhas:
        print(f"{falhas} caso(s) divergente(s) — NÃO use este gate.")
        return REJEITA
    print("Todos os casos conforme. Gate operacional.")
    return APROVA


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Gate determinístico de self-healing para testes Playwright.")
    ap.add_argument("antes", nargs="?", type=Path, help="arquivo .spec.ts original")
    ap.add_argument("depois", nargs="?", type=Path, help="arquivo .spec.ts proposto")
    ap.add_argument("--sem-intent", action="store_true",
                    help="não exige o header `// intent:` (só para suítes legadas; "
                         "se o header existir nos dois arquivos, ainda é comparado)")
    ap.add_argument("--check-po", type=Path, metavar="DIR",
                    help="verifica que nenhum page object contém asserção")
    ap.add_argument("--baseline", type=Path,
                    help="ManifestoDeBaseline.json (opt-in, modo de projeto)")
    ap.add_argument("--surface", type=Path,
                    help="diretório da superfície candidata")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if args.baseline or args.surface:
        if not args.baseline or not args.surface:
            print("--baseline e --surface são obrigatórios juntos.", file=sys.stderr)
            return ERRO_DE_USO
        if not args.baseline.is_file() or not args.surface.exists():
            print("baseline ou superfície não encontrada.", file=sys.stderr)
            return ERRO_DE_USO
        try:
            manifesto = json.loads(args.baseline.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(json.dumps({"decision": "REJEITA", "exit_code": REJEITA,
                              "reason": f"baseline inválida: {e}", "detail": {}},
                             ensure_ascii=False, indent=2))
            return REJEITA
        return comparar_superficie(
            manifesto, args.surface, manifesto_path=args.baseline,
        ).emit()

    if args.check_po:
        if not args.check_po.exists():
            print(f"caminho não encontrado: {args.check_po}", file=sys.stderr)
            return ERRO_DE_USO
        return check_po(args.check_po)

    if not args.antes or not args.depois:
        ap.print_usage()
        print("\nInforme os dois arquivos, ou use --check-po / --self-test.",
              file=sys.stderr)
        return ERRO_DE_USO

    for p in (args.antes, args.depois):
        if not p.is_file():
            print(f"arquivo não encontrado: {p}", file=sys.stderr)
            return ERRO_DE_USO

    return gate(
        args.antes.read_bytes(),
        args.depois.read_bytes(),
        exigir_intent=not args.sem_intent,
    ).emit()


if __name__ == "__main__":
    raise SystemExit(main())
