#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["tree-sitter>=0.26", "tree-sitter-typescript>=0.23"]
# ///
"""
spec_lint.py — verificação estática da suíte gerada.

Promove a exit code aquilo que antes era instrução no SKILL.md. Roda em
milissegundos, sem browser e sem modelo. Se o agente ignorar uma regra, aqui
ela é pega — não na revisão de código três semanas depois.

O QUE VERIFICA
--------------
ERRO (exit 1) — decidível estaticamente, sem falso positivo esperado:
  E1  waitForTimeout            espera cega; sempre lenta ou sempre insuficiente
  E2  networkidle               desaconselhado pelo próprio Playwright
  E3  seletor frágil            classe gerada (css-1x2y3z) ou cadeia estrutural
  E4  falta `// intent:`        sem ele o gate do healing não tem referência
  E5  .only()                   silencia o resto da suíte sem avisar
  E6  .skip() / .fixme()        dívida silenciosa; ver healing-policy.md
  E7  spec sem asserção         um teste que não prova nada passa sempre
  E8  expect() em page object   cega o gate; ver pom-policy.md

AVISO (não falha) — heurístico, pode ter falso positivo:
  A1  dado literal sem prefixo `e2e-` em .fill()

USO
---
    uv run spec_lint.py tests/
    uv run spec_lint.py tests/e2e/produtos/criar-produto.spec.ts
    uv run spec_lint.py tests/ --json
    uv run spec_lint.py --self-test

EXIT CODES
----------
    0  limpo (avisos não falham)
    1  ao menos um ERRO
    3  erro de uso
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

OK, FALHA, ERRO_DE_USO = 0, 1, 3

PADROES_SPEC = ("*.spec.ts",)
PADROES_PO = ("*.page.ts", "*.po.ts")
IGNORAR = {"node_modules", ".git", "dist", "build", ".e2e-engine"}

RE_INTENT = re.compile(r"^\s*//\s*intent:\s*(.+?)\s*$", re.M | re.I)
RE_FILL = re.compile(r"\.fill\(\s*['\"]([^'\"]+)['\"]")

# Classes geradas por CSS-in-JS e cadeias estruturais de DOM.
RE_SELETOR_FRAGIL = re.compile(
    r"""
    \.(css|sc|jss|emotion|MuiBox|makeStyles)-[A-Za-z0-9]{3,}   # classe gerada
  | nth-child\(                                                 # posicional
  | (?:\w+\s*>\s*){3,}                                          # cadeia estrutural
    """,
    re.X,
)

REGRAS_TEXTO = [
    ("E1", "waitForTimeout", re.compile(r"\bwaitForTimeout\s*\(")),
    ("E2", "networkidle", re.compile(r"['\"]networkidle['\"]")),
    ("E5", "test.only / .only(", re.compile(r"\b(?:test|describe)\.only\b|\.only\s*\(")),
    ("E6", "test.skip / test.fixme", re.compile(r"\b(?:test|describe)\.(?:skip|fixme)\b")),
]

MENSAGENS = {
    "E1": "espera cega — use expectativa web-first (`await expect(x).toBeVisible()`)",
    "E2": "`networkidle` é desaconselhado; espere um sinal real de estabilidade",
    "E3": "seletor frágil — ver references/selector-health.md",
    "E4": "falta o header `// intent:` — sem ele o gate do healing é bloqueado",
    "E5": "`.only` silencia o resto da suíte sem avisar",
    "E6": "`skip`/`fixme` é dívida silenciosa — ver references/healing-policy.md",
    "E7": "nenhuma asserção no arquivo — este teste passa sempre",
    "E8": "asserção dentro de page object cega o gate — mova para o `.spec.ts`",
    "A1": "dado literal sem prefixo `e2e-` — pode não ser rastreável no teardown",
}


@dataclass
class Achado:
    codigo: str
    severidade: str      # ERRO | AVISO
    arquivo: str
    linha: int
    trecho: str
    mensagem: str


def coletar(raiz: Path, padroes: tuple[str, ...]) -> list[Path]:
    if raiz.is_file():
        return [raiz] if any(raiz.match(p) for p in padroes) else []
    achados: list[Path] = []
    for padrao in padroes:
        achados += [p for p in raiz.rglob(padrao) if not (IGNORAR & set(p.parts))]
    return sorted(set(achados))


def tem_assercao(fonte: bytes) -> bool:
    tree = PARSER.parse(fonte)
    if tree.root_node.has_error:
        return True   # não penaliza o que não parseia; o gate já rejeita isso
    return bool(QueryCursor(Q_EXPECT).captures(tree.root_node).get("call", []))


def linha_de(texto: str, pos: int) -> int:
    return texto.count("\n", 0, pos) + 1


def analisar_spec(caminho: Path) -> list[Achado]:
    texto = caminho.read_text(encoding="utf-8")
    fonte = texto.encode()
    out: list[Achado] = []

    def add(cod, sev, ln, trecho):
        out.append(Achado(cod, sev, str(caminho), ln, trecho.strip()[:90],
                          MENSAGENS[cod]))

    for codigo, _rotulo, regex in REGRAS_TEXTO:
        for m in regex.finditer(texto):
            ln = linha_de(texto, m.start())
            add(codigo, "ERRO", ln, texto.splitlines()[ln - 1])

    for m in RE_SELETOR_FRAGIL.finditer(texto):
        ln = linha_de(texto, m.start())
        add("E3", "ERRO", ln, texto.splitlines()[ln - 1])

    if not RE_INTENT.search(texto):
        add("E4", "ERRO", 1, "(topo do arquivo)")

    if not tem_assercao(fonte):
        add("E7", "ERRO", 1, "(arquivo inteiro)")

    for m in RE_FILL.finditer(texto):
        valor = m.group(1)
        # Ignora o que claramente não é dado persistido.
        if valor.startswith("e2e-") or len(valor) < 3 or "@" in valor:
            continue
        add("A1", "AVISO", linha_de(texto, m.start()), m.group(0))

    return out


def analisar_po(caminho: Path) -> list[Achado]:
    texto = caminho.read_text(encoding="utf-8")
    out: list[Achado] = []

    tree = PARSER.parse(texto.encode())
    if not tree.root_node.has_error:
        for node in QueryCursor(Q_EXPECT).captures(tree.root_node).get("call", []):
            ln = node.start_point[0] + 1
            out.append(Achado("E8", "ERRO", str(caminho), ln,
                              texto.splitlines()[ln - 1].strip()[:90], MENSAGENS["E8"]))

    for m in RE_SELETOR_FRAGIL.finditer(texto):
        ln = linha_de(texto, m.start())
        out.append(Achado("E3", "ERRO", str(caminho), ln,
                          texto.splitlines()[ln - 1].strip()[:90], MENSAGENS["E3"]))

    for codigo, _rotulo, regex in REGRAS_TEXTO[:2]:   # E1 e E2 valem no PO também
        for m in regex.finditer(texto):
            ln = linha_de(texto, m.start())
            out.append(Achado(codigo, "ERRO", str(caminho), ln,
                              texto.splitlines()[ln - 1].strip()[:90], MENSAGENS[codigo]))

    return out


def lint(raiz: Path) -> tuple[list[Achado], int, int]:
    specs = coletar(raiz, PADROES_SPEC)
    pos = coletar(raiz, PADROES_PO)
    achados: list[Achado] = []
    for s in specs:
        achados += analisar_spec(s)
    for p in pos:
        achados += analisar_po(p)
    return achados, len(specs), len(pos)


def relatar(achados: list[Achado], n_spec: int, n_po: int, como_json: bool) -> int:
    erros = [a for a in achados if a.severidade == "ERRO"]
    avisos = [a for a in achados if a.severidade == "AVISO"]

    if como_json:
        print(json.dumps({
            "decision": "REJEITA" if erros else "APROVA",
            "arquivos": {"specs": n_spec, "page_objects": n_po},
            "erros": len(erros), "avisos": len(avisos),
            "achados": [asdict(a) for a in achados],
        }, ensure_ascii=False, indent=2))
        return FALHA if erros else OK

    print(f"spec_lint — {n_spec} spec(s), {n_po} page object(s)\n")
    if not achados:
        print("  Nenhum achado. Suíte conforme.")
    for a in achados:
        marca = "ERRO " if a.severidade == "ERRO" else "aviso"
        print(f"  {marca} {a.codigo}  {a.arquivo}:{a.linha}")
        print(f"        {a.mensagem}")
        print(f"        > {a.trecho}")
    print()
    print(f"{len(erros)} erro(s), {len(avisos)} aviso(s).")
    if erros:
        print("Corrija os erros antes de rodar a suíte.")
    return FALHA if erros else OK


# ---------------------------------------------------------------- self-test

SPEC_LIMPO = """// spec: .memory-bank/e2e-specs/produtos.plan.md
// intent: produto criado aparece na lista como Ativo
import { test, expect } from '../fixtures';
test('cria produto', async ({ produtosPage }) => {
  await produtosPage.goto();
  await produtosPage.nome.fill('e2e-run1-teclado');
  await expect(produtosPage.linhaDe('e2e-run1-teclado')).toBeVisible();
});
"""

CASOS_LINT = [
    ("spec limpo", SPEC_LIMPO, []),
    ("waitForTimeout", SPEC_LIMPO.replace(
        "await produtosPage.goto();",
        "await produtosPage.goto();\n  await page.waitForTimeout(3000);"), ["E1"]),
    ("networkidle", SPEC_LIMPO.replace(
        "await produtosPage.goto();",
        "await page.waitForLoadState('networkidle');"), ["E2"]),
    ("classe gerada", SPEC_LIMPO.replace(
        "produtosPage.linhaDe('e2e-run1-teclado')",
        "page.locator('.css-1x2y3z')"), ["E3"]),
    ("nth-child", SPEC_LIMPO.replace(
        "produtosPage.linhaDe('e2e-run1-teclado')",
        "page.locator('tr:nth-child(3)')"), ["E3"]),
    ("sem intent", SPEC_LIMPO.replace(
        "// intent: produto criado aparece na lista como Ativo\n", ""), ["E4"]),
    ("test.only", SPEC_LIMPO.replace("test('cria produto'", "test.only('cria produto'"),
     ["E5"]),
    ("test.skip", SPEC_LIMPO.replace("test('cria produto'", "test.skip('cria produto'"),
     ["E6"]),
    ("sem asserção", SPEC_LIMPO.replace(
        "  await expect(produtosPage.linhaDe('e2e-run1-teclado')).toBeVisible();\n", ""),
     ["E7"]),
    ("dado sem prefixo", SPEC_LIMPO.replace("'e2e-run1-teclado')", "'teclado')"),
     ["A1"]),
]


def self_test() -> int:
    import tempfile
    falhas = 0
    print(f"spec_lint — self-test ({len(CASOS_LINT)} casos)\n")
    with tempfile.TemporaryDirectory() as td:
        for nome, conteudo, esperados in CASOS_LINT:
            arq = Path(td) / "t.spec.ts"
            arq.write_text(conteudo, encoding="utf-8")
            codigos = sorted({a.codigo for a in analisar_spec(arq)})
            ok = codigos == sorted(esperados)
            falhas += not ok
            print(f"  {'PASS' if ok else 'FALHA':5}  {nome:22} "
                  f"esperado={esperados or ['-']} obtido={codigos or ['-']}")
    print()
    if falhas:
        print(f"{falhas} caso(s) divergente(s).")
        return FALHA
    print("Todos os casos conforme. Lint operacional.")
    return OK


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verificação estática da suíte E2E gerada.")
    ap.add_argument("caminho", nargs="?", type=Path,
                    help="diretório ou arquivo .spec.ts")
    ap.add_argument("--json", action="store_true", help="saída em JSON")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if not args.caminho:
        ap.print_usage()
        print("\nInforme um caminho, ou use --self-test.", file=sys.stderr)
        return ERRO_DE_USO
    if not args.caminho.exists():
        print(f"caminho não encontrado: {args.caminho}", file=sys.stderr)
        return ERRO_DE_USO

    achados, n_spec, n_po = lint(args.caminho)
    return relatar(achados, n_spec, n_po, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
