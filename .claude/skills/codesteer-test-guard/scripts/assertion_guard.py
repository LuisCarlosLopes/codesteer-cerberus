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
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

from tree_sitter import Language, Parser, Query, QueryCursor
import tree_sitter_typescript as tsts

TS = Language(tsts.language_typescript())
PARSER = Parser(TS)

Q_EXPECT = Query(TS, '(call_expression function: (identifier) @f (#eq? @f "expect")) @call')
Q_MOD = Query(
    TS,
    '(member_expression property: (property_identifier) @p'
    ' (#any-of? @p "skip" "fixme" "only"))',
)
Q_AWAIT = Query(TS, "(await_expression) @a")

# Teto de timeout que o Loop não pode ultrapassar (ms).
MAX_TIMEOUT_MS = 30_000

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


def normalizar(texto: str) -> str:
    """Colapsa espaços e uniformiza aspas para comparação estável."""
    return re.sub(r"\s+", " ", texto).replace('"', "'").strip()


def sem_timeout(args: str) -> str:
    """Remove `timeout: N` dos argumentos do matcher.

    Ajustar timeout é explicitamente permitido ao Loop, então ele não pode
    fazer parte da identidade semântica da asserção. O teto continua sendo
    verificado à parte (MAX_TIMEOUT_MS). Demais opções — `ignoreCase`,
    `useInnerText` — permanecem congeladas por alterarem a semântica.
    """
    s = re.sub(r"timeout\s*:\s*\d+\s*,?\s*", "", args)
    s = re.sub(r",\s*}", " }", s)      # vírgula pendurada antes de }
    s = re.sub(r"\{\s*\}", "", s)      # objeto que ficou vazio
    s = re.sub(r",\s*\)", ")", s)      # vírgula pendurada antes de )
    return re.sub(r"\s+", " ", s).strip()


def decompor(source: bytes) -> list[Assercao]:
    """Extrai (matcher, locator) de cada asserção do arquivo.

    Sobe da chamada `expect(...)` até o topo da cadeia para capturar
    modificadores (`not`) e o matcher com seus argumentos.
    """
    tree = PARSER.parse(source)
    if tree.root_node.has_error:
        raise GateError("arquivo não parseia como TypeScript")

    out: list[Assercao] = []
    for node in QueryCursor(Q_EXPECT).captures(tree.root_node).get("call", []):
        args = node.child_by_field_name("arguments")
        locator = normalizar(args.text.decode()) if args else ""

        cur, cadeia = node, []
        while cur.parent and cur.parent.type in (
            "member_expression",
            "call_expression",
            "await_expression",
        ):
            cur = cur.parent
            if cur.type == "member_expression":
                prop = cur.child_by_field_name("property")
                if prop:
                    cadeia.append(prop.text.decode())
            elif cur.type == "call_expression" and cadeia:
                cargs = cur.child_by_field_name("arguments")
                if cargs:
                    cadeia[-1] += sem_timeout(normalizar(cargs.text.decode()))

        out.append(Assercao(matcher=".".join(cadeia), locator=locator))
    return out


def modificadores(source: bytes) -> set[str]:
    tree = PARSER.parse(source)
    if tree.root_node.has_error:
        return set()
    return {n.text.decode() for n in QueryCursor(Q_MOD).captures(tree.root_node).get("p", [])}


def contar_steps(source: bytes) -> int:
    """Awaits que não são asserções — proxy para as ações do teste."""
    tree = PARSER.parse(source)
    if tree.root_node.has_error:
        raise GateError("arquivo não parseia como TypeScript")
    awaits = QueryCursor(Q_AWAIT).captures(tree.root_node).get("a", [])
    return sum(1 for n in awaits if "expect(" not in n.text.decode())


def timeouts_acima_do_teto(source: bytes) -> list[int]:
    valores = [int(v) for v in re.findall(r"timeout\s*:\s*(\d+)", source.decode())]
    return [v for v in valores if v > MAX_TIMEOUT_MS]


# Header obrigatório no .spec.ts, ao lado dos `// spec:` e `// seed:` que o
# fluxo oficial já usa. O gate LÊ este valor dos dois arquivos — nunca o
# recebe por argumento. Um guarda cujo valor de referência é fornecido por
# quem está sendo guardado não guarda nada.
RE_INTENT = re.compile(rb"^\s*//\s*intent:\s*(.+?)\s*$", re.M | re.I)


def extrair_intent(source: bytes) -> str | None:
    m = RE_INTENT.search(source)
    return normalizar(m.group(1).decode("utf-8")) if m else None


def gate(antes: bytes, depois: bytes, exigir_intent: bool = True) -> Verdict:
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
    try:
        a, d = decompor(antes), decompor(depois)
        steps_antes, steps_depois = contar_steps(antes), contar_steps(depois)
    except GateError as e:
        return Verdict("REJEITA", REJEITA, f"fail-closed: {e}", {})

    # 2. Contagem de asserções é congelada.
    if len(a) != len(d):
        return Verdict("REJEITA", REJEITA, "número de asserções mudou",
                       {"antes": len(a), "depois": len(d)})

    # 3. Semântica das asserções é congelada.
    ma, md = sorted(x.matcher for x in a), sorted(x.matcher for x in d)
    if ma != md:
        return Verdict("REJEITA", REJEITA, "matcher alterado",
                       {"removidos": sorted(set(ma) - set(md)),
                        "adicionados": sorted(set(md) - set(ma))})

    # 4. skip / fixme / only nunca podem ser introduzidos.
    novos_mod = modificadores(depois) - modificadores(antes)
    if novos_mod:
        return Verdict("REJEITA", REJEITA, "modificador proibido introduzido",
                       {"modificadores": sorted(novos_mod)})

    # 5. Steps não podem desaparecer.
    if steps_depois < steps_antes:
        return Verdict("REJEITA", REJEITA, "steps removidos",
                       {"antes": steps_antes, "depois": steps_depois})

    # 6. Timeout tem teto.
    if (excedidos := timeouts_acima_do_teto(depois)):
        return Verdict("REJEITA", REJEITA, f"timeout acima do teto de {MAX_TIMEOUT_MS}ms",
                       {"valores": excedidos})

    # 7. Locator dentro da asserção mudou → exige prova de mesmo elemento.
    trocas = [
        {"antes": x.locator, "depois": y.locator}
        for x, y in zip(a, d)
        if x.locator != y.locator
    ]
    if trocas:
        return Verdict(
            "APROVA_COM_PROVA", APROVA_COM_PROVA,
            "locator de asserção mudou — confirme no trace que o locator novo "
            "resolve para o MESMO elemento antes de aplicar",
            {"trocas": trocas},
        )

    return Verdict("APROVA", APROVA, "nenhuma violação de política", {})


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
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

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
