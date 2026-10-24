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
  E9  smoke sem a tag @smoke    `--grep @smoke` não o executa; some do CI calado
  E10 asserção tautológica      `expect(page).toBeTruthy()` e afins não provam nada
  E11 mutação de domínio em smoke (criar/editar/excluir/publicar)
  E12 ação smoke não classificada (não libera a suíte)
  E13 parse inválido            fail-closed
  E14 raiz/inventário vazio     fail-closed (exit 1, não 3)
  E15 timeout acima de 30_000 ms

AVISO (não falha) — heurístico, pode ter falso positivo:
  A1  dado literal sem prefixo `e2e-` em .fill()
  A2  suíte smoke acima do orçamento de casos (ver smoke-policy.md)
  A3  residual; mutação identificada é E11, não só aviso

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

from suite_model import (
    MAX_TIMEOUT_MS,
    eh_smoke_caso,
    parse_suite,
)

TS = Language(tsts.language_typescript())
PARSER = Parser(TS)
Q_EXPECT = Query(TS, '(call_expression function: (identifier) @f (#eq? @f "expect")) @call')

OK, FALHA, ERRO_DE_USO = 0, 1, 3

PADROES_SPEC = ("*.spec.ts",)
PADROES_PO = ("*.page.ts", "*.po.ts")
IGNORAR = {"node_modules", ".git", "dist", "build", ".e2e-engine"}

RE_INTENT = re.compile(r"^\s*//\s*intent:\s*(.+?)\s*$", re.M | re.I)
RE_FILL = re.compile(r"\.fill\(\s*['\"]([^'\"]+)['\"]")

# --- smoke -----------------------------------------------------------------
# Um teste smoke é reconhecido pelo caminho: tests/smoke/** ou *.smoke.spec.ts.
# Ver references/smoke-policy.md.
LIMITE_CASOS_SMOKE = 12

RE_CASO_TESTE = re.compile(r"(?m)^\s*test\s*\(")

# A tag precisa estar no título ou na opção `tag:` — em comentário não serve,
# porque é `--grep @smoke` que decide o que roda no CI.
RE_TAG_SMOKE = re.compile(
    r"(?m)^.*(?:\btest\s*\(|\btest\.describe\s*\(|\btag\s*:).*@smoke")

# Asserções que passam independentemente do estado do produto. É o modo de
# falha clássico do smoke: "a página carregou" não prova caminho crítico.
RE_ASSERCAO_VAZIA = re.compile(
    r"""
    expect\s*\(\s*(?:true|1|page)\s*\)\s*\.\s*(?:toBeTruthy|toBeDefined)\b
  | expect\s*\(\s*true\s*\)\s*\.\s*toBe\s*\(\s*true\s*\)
  | expect\s*\(\s*page\s*\)\s*\.\s*not\s*\.\s*toBeNull\b
  | expect\s*\(\s*page\.locator\(\s*['"](?:body|html)['"]\s*\)\s*\)
      \s*\.\s*(?:toBeVisible|toBeAttached)\b
    """,
    re.X,
)

# Heurística: verbo de mutação no locator, ou preenchimento de formulário.
RE_ACAO_MUTANTE = re.compile(
    r"""(?ix)
    \.fill\s*\(
  | \.setInputFiles\s*\(
  | (?:getByRole|getByText|getByTestId|getByLabel|getByTitle)\s*\(
    [^)]*?\b(?: salvar | save | criar | create | cadastrar | novo | nova | new
              | excluir | deletar | delete | remover | remove | apagar
              | confirmar | confirm | enviar | submit | publicar | publish )\b
    """,
)

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
    "E9": "teste smoke sem a tag `@smoke` — `--grep @smoke` não vai executá-lo",
    "E10": "asserção tautológica — passa com o produto quebrado; prove um sinal real",
    "E11": "mutação de domínio em smoke — criar/editar/excluir/publicar bloqueia a suíte",
    "E12": "ação smoke não classificada como leitura, login excepcional ou filtro de busca",
    "E13": "arquivo não parseia como TypeScript — o que não se analisa não se aprova",
    "E14": "raiz inexistente ou inventário vazio — falha de lint, não só erro de uso",
    "E15": f"timeout acima do teto de {MAX_TIMEOUT_MS} ms (qualquer notação numérica)",
    "A1": "dado literal sem prefixo `e2e-` — pode não ser rastreável no teardown",
    "A2": f"suíte smoke acima de {LIMITE_CASOS_SMOKE} casos — deixou de ser smoke",
    "A3": "ação aparentemente mutante em smoke — smoke é somente leitura (scope RL)",
}


def eh_smoke_por_caminho(caminho: Path) -> bool:
    """tests/smoke/**/*.spec.ts ou *.smoke.spec.ts — ver smoke-policy.md."""
    return "smoke" in {p.lower() for p in caminho.parts[:-1]} or \
        caminho.name.lower().endswith(".smoke.spec.ts")


def eh_smoke(caminho: Path, texto: str | None = None) -> bool:
    """
    Caminho **ou** tag por caso (com herança de describe). Comentário e
    string não contam — é `--grep @smoke` que decide o que o CI executa.
    O caminho continua valendo para pegar o arquivo na pasta certa que
    esqueceu a tag (E9).
    """
    if eh_smoke_por_caminho(caminho):
        return True
    fonte = caminho.read_bytes() if texto is None else texto.encode()
    suite = parse_suite(fonte, str(caminho))
    return any(eh_smoke_caso(c) for c in suite.tests)


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
    suite = parse_suite(fonte)
    if suite.parse_error:
        return False
    return bool(suite.assertions)


RE_VERBO_MUTACAO = re.compile(
    r"(?ix)\b(?:salvar|save|criar|create|cadastrar|novo|nova|new|"
    r"excluir|deletar|delete|remover|remove|apagar|"
    r"confirmar|confirm|enviar|submit|publicar|publish|"
    r"editar|edit|atualizar|update)\b"
)
RE_LOGIN = re.compile(r"(?ix)\b(?:entrar|login|signin|sign-in|acessar|logar)\b")
RE_CAMPO_LOGIN = re.compile(
    r"(?ix)\b(?:senha|password|e-?mail|usuario|username)\b"
)
RE_BUSCA = re.compile(
    r"(?ix)\b(?:busca|buscar|search|filtrar|filtro|filter|searchbox)\b"
)
_LEITURA = {
    "goto", "goBack", "goForward", "reload",
    "waitFor", "waitForURL", "waitForSelector", "waitForLoadState",
    "hover", "focus", "blur",
}
_MUTACAO_DIRETA = {
    "fill", "type", "pressSequentially", "setInputFiles",
    "selectOption", "check", "uncheck", "setChecked",
}
_CLICK = {"click", "dblclick", "tap"}


def classificar_acao_smoke(kind: str, receiver: str) -> str:
    """leitura | login | busca | mutacao | nao_classificada."""
    if kind in _LEITURA:
        return "leitura"
    if kind in _MUTACAO_DIRETA:
        if RE_CAMPO_LOGIN.search(receiver) or RE_LOGIN.search(receiver):
            return "login"
        if RE_BUSCA.search(receiver):
            return "busca"
        return "mutacao"
    if kind in _CLICK:
        if RE_VERBO_MUTACAO.search(receiver):
            return "mutacao"
        if RE_LOGIN.search(receiver) or RE_CAMPO_LOGIN.search(receiver):
            return "login"
        if RE_BUSCA.search(receiver):
            return "busca"
        return "nao_classificada"
    return "nao_classificada"


def linha_de(texto: str, pos: int) -> int:
    return texto.count("\n", 0, pos) + 1


def analisar_spec(caminho: Path) -> list[Achado]:
    texto = caminho.read_text(encoding="utf-8")
    fonte = texto.encode()
    out: list[Achado] = []

    def add(cod, sev, ln, trecho):
        out.append(Achado(cod, sev, str(caminho), ln, trecho.strip()[:90],
                          MENSAGENS[cod]))

    suite = parse_suite(fonte, str(caminho))
    if suite.parse_error:
        add("E13", "ERRO", 1, "(parse)")
        return out

    for codigo, _rotulo, regex in REGRAS_TEXTO:
        for m in regex.finditer(texto):
            ln = linha_de(texto, m.start())
            add(codigo, "ERRO", ln, texto.splitlines()[ln - 1])

    for m in RE_SELETOR_FRAGIL.finditer(texto):
        ln = linha_de(texto, m.start())
        add("E3", "ERRO", ln, texto.splitlines()[ln - 1])

    if not RE_INTENT.search(texto):
        add("E4", "ERRO", 1, "(topo do arquivo)")

    if suite.tests:
        for caso in suite.tests:
            if not caso.assertions:
                add("E7", "ERRO", caso.start_line, caso.title or "(caso sem asserção)")
    elif not suite.assertions:
        add("E7", "ERRO", 1, "(arquivo inteiro)")

    for m in RE_ASSERCAO_VAZIA.finditer(texto):
        ln = linha_de(texto, m.start())
        add("E10", "ERRO", ln, texto.splitlines()[ln - 1])

    for valor in suite.timeouts:
        if valor > MAX_TIMEOUT_MS:
            add("E15", "ERRO", 1, f"timeout: {valor}")

    smoke_path = eh_smoke_por_caminho(caminho)
    for caso in suite.tests:
        tagged = eh_smoke_caso(caso)
        if smoke_path and not tagged:
            add("E9", "ERRO", caso.start_line,
                caso.title or "(caso smoke sem @smoke)")
        if not (smoke_path or tagged):
            continue
        for acao in caso.acoes:
            classe = classificar_acao_smoke(acao.kind, acao.receiver)
            if classe == "mutacao":
                add("E11", "ERRO", acao.line, acao.kind)
            elif classe == "nao_classificada":
                add("E12", "ERRO", acao.line, acao.kind)

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
    if tree.root_node.has_error:
        out.append(Achado("E13", "ERRO", str(caminho), 1, "(parse)",
                          MENSAGENS["E13"]))
        return out
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


def orcamento_smoke(specs: list[Path]) -> list[Achado]:
    """Suíte smoke longa deixa de gatear deploy: ninguém espera por ela."""
    smokes = [p for p in specs if eh_smoke(p)]
    if not smokes:
        return []
    casos = sum(len(RE_CASO_TESTE.findall(p.read_text(encoding="utf-8")))
                for p in smokes)
    if casos <= LIMITE_CASOS_SMOKE:
        return []
    return [Achado("A2", "AVISO", str(smokes[0]), 1,
                   f"{casos} casos smoke em {len(smokes)} arquivo(s)",
                   MENSAGENS["A2"])]


def lint(raiz: Path) -> tuple[list[Achado], int, int]:
    if not raiz.exists():
        return ([Achado("E14", "ERRO", str(raiz), 1, "(raiz)", MENSAGENS["E14"])],
                0, 0)
    specs = coletar(raiz, PADROES_SPEC)
    pos = coletar(raiz, PADROES_PO)
    if not specs and not pos:
        return ([Achado("E14", "ERRO", str(raiz), 1, "(inventário vazio)",
                        MENSAGENS["E14"])], 0, 0)
    achados: list[Achado] = []
    for s in specs:
        achados += analisar_spec(s)
    for p in pos:
        achados += analisar_po(p)
    achados += orcamento_smoke(specs)
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
    ("asserção tautológica", SPEC_LIMPO.replace(
        "await expect(produtosPage.linhaDe('e2e-run1-teclado')).toBeVisible();",
        "await expect(page).toBeTruthy();"), ["E10"]),
    # Fora de tests/smoke/, mas com a tag: as regras de smoke valem igual —
    # é a tag que decide o que o CI executa.
    ("smoke por tag, fora da pasta", SPEC_LIMPO.replace(
        "test('cria produto'", "test('lista produtos @smoke'"), ["E11"]),
]

SMOKE_LIMPO = """// spec: .memory-bank/e2e-specs/smoke.plan.md
// intent: dashboard responde autenticado depois do deploy
import { test, expect } from '../fixtures';
test('dashboard carrega autenticado', { tag: ['@smoke'] }, async ({ page }) => {
  await page.goto('/dashboard');
  await expect(page.getByRole('heading', { name: 'Resumo' })).toBeVisible();
});
"""

CASOS_SMOKE = [
    ("smoke limpo", SMOKE_LIMPO, []),
    ("smoke sem tag @smoke", SMOKE_LIMPO.replace("{ tag: ['@smoke'] }, ", ""),
     ["E9"]),
    ("smoke tautológico", SMOKE_LIMPO.replace(
        "page.getByRole('heading', { name: 'Resumo' })",
        "page.locator('body')"), ["E10"]),
    ("smoke com ação mutante", SMOKE_LIMPO.replace(
        "  await page.goto('/dashboard');",
        "  await page.goto('/dashboard');\n"
        "  await page.getByRole('button', { name: 'Salvar' }).click();"), ["E11"]),
]


def self_test() -> int:
    import tempfile
    falhas = 0
    total = len(CASOS_LINT) + len(CASOS_SMOKE) + 13
    print(f"spec_lint — self-test ({total} casos)\n")
    with tempfile.TemporaryDirectory() as td:
        for nome, conteudo, esperados in CASOS_LINT:
            arq = Path(td) / "t.spec.ts"
            arq.write_text(conteudo, encoding="utf-8")
            codigos = sorted({a.codigo for a in analisar_spec(arq)})
            ok = codigos == sorted(esperados)
            falhas += not ok
            print(f"  {'PASS' if ok else 'FALHA':5}  {nome:22} "
                  f"esperado={esperados or ['-']} obtido={codigos or ['-']}")

        # Smoke: o reconhecimento vem do caminho (tests/smoke/**).
        pasta_smoke = Path(td) / "smoke"
        pasta_smoke.mkdir()
        for nome, conteudo, esperados in CASOS_SMOKE:
            arq = pasta_smoke / "t.spec.ts"
            arq.write_text(conteudo, encoding="utf-8")
            codigos = sorted({a.codigo for a in analisar_spec(arq)})
            ok = codigos == sorted(esperados)
            falhas += not ok
            print(f"  {'PASS' if ok else 'FALHA':5}  {nome:22} "
                  f"esperado={esperados or ['-']} obtido={codigos or ['-']}")

        # A2 é de suíte, não de arquivo: só aparece somando os casos.
        excesso = SMOKE_LIMPO + "\n".join(
            f"test('caso {i}', {{ tag: ['@smoke'] }}, async ({{ page }}) => {{\n"
            f"  await expect(page.getByRole('heading')).toBeVisible();\n}});"
            for i in range(LIMITE_CASOS_SMOKE + 1)
        )
        (pasta_smoke / "t.spec.ts").write_text(excesso, encoding="utf-8")
        codigos = sorted({a.codigo for a in orcamento_smoke([pasta_smoke / "t.spec.ts"])})
        ok = codigos == ["A2"]
        falhas += not ok
        print(f"  {'PASS' if ok else 'FALHA':5}  {'orçamento smoke (A2)':22} "
              f"esperado=['A2'] obtido={codigos or ['-']}")

        extras = [
            ("V4 parse inválido",
             Path(td) / "bad.spec.ts",
             "test('t', async ({ page }) => { await page.goto('/' ;;; ",
             ["E13"]),
            ("V4 timeout 30_001",
             Path(td) / "to.spec.ts",
             SPEC_LIMPO.replace(
                 "toBeVisible();",
                 "toBeVisible({ timeout: 30_001 });"),
             ["E15"]),
            ("V4 tag só em comentário",
             Path(td) / "cmt.spec.ts",
             SPEC_LIMPO.replace(
                 "// intent:",
                 "// @smoke\n// intent:"),
             []),
            ("V4 herança de describe",
             Path(td) / "desc.spec.ts",
             """// spec: .memory-bank/e2e-specs/smoke.plan.md
// intent: dashboard responde autenticado depois do deploy
import { test, expect } from '../fixtures';
test.describe('dashboard @smoke', () => {
  test('carrega', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.getByRole('heading', { name: 'Resumo' })).toBeVisible();
  });
});
""",
             []),
            ("V6 login excepcional",
             pasta_smoke / "login.spec.ts",
             """// spec: .memory-bank/e2e-specs/smoke.plan.md
// intent: login prova autenticação
import { test, expect } from '../fixtures';
test('login @smoke', { tag: ['@smoke'] }, async ({ page }) => {
  await page.getByLabel('Senha').fill(process.env.E2E_PASSWORD);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page.getByRole('heading', { name: 'Resumo' })).toBeVisible();
});
""",
             []),
            ("V6 filtro de busca",
             pasta_smoke / "busca.spec.ts",
             """// spec: .memory-bank/e2e-specs/smoke.plan.md
// intent: filtro de busca não muta registro
import { test, expect } from '../fixtures';
test('busca @smoke', { tag: ['@smoke'] }, async ({ page }) => {
  await page.goto('/produtos');
  await page.getByRole('searchbox').fill('e2e-query');
  await page.getByRole('button', { name: 'Buscar' }).click();
  await expect(page.getByRole('heading', { name: 'Produtos' })).toBeVisible();
});
""",
             []),
            ("V6 ação não classificada",
             pasta_smoke / "click.spec.ts",
             """// spec: .memory-bank/e2e-specs/smoke.plan.md
// intent: click sem contrato
import { test, expect } from '../fixtures';
test('detalhe @smoke', { tag: ['@smoke'] }, async ({ page }) => {
  await page.goto('/dashboard');
  await page.getByRole('button', { name: 'Detalhes' }).click();
  await expect(page.getByRole('heading', { name: 'Resumo' })).toBeVisible();
});
""",
             ["E12"]),
            ("V6 verbo só em comentário",
             pasta_smoke / "cmt-acao.spec.ts",
             SMOKE_LIMPO.replace(
                 "  await page.goto('/dashboard');",
                 "  // clique em Salvar para criar\n"
                 "  await page.goto('/dashboard');"),
             []),
            ("V6 excluir domínio",
             pasta_smoke / "del.spec.ts",
             SMOKE_LIMPO.replace(
                 "  await page.goto('/dashboard');",
                 "  await page.goto('/dashboard');\n"
                 "  await page.getByRole('button', { name: 'Excluir' }).click();"),
             ["E11"]),
        ]
        for nome, arq, conteudo, esperados in extras:
            arq.write_text(conteudo, encoding="utf-8")
            codigos = sorted({a.codigo for a in analisar_spec(arq)})
            ok = codigos == sorted(esperados)
            falhas += not ok
            print(f"  {'PASS' if ok else 'FALHA':5}  {nome:22} "
                  f"esperado={esperados or ['-']} obtido={codigos or ['-']}")

        vazia = Path(td) / "vazia"
        vazia.mkdir()
        achados_vazio, _, _ = lint(vazia)
        ok = "E14" in {a.codigo for a in achados_vazio}
        falhas += not ok
        print(f"  {'PASS' if ok else 'FALHA':5}  {'V4 inventário vazio':22} "
              f"esperado=['E14'] obtido={sorted({a.codigo for a in achados_vazio}) or ['-']}")

        achados_raiz, _, _ = lint(Path(td) / "nao-existe")
        ok = "E14" in {a.codigo for a in achados_raiz}
        falhas += not ok
        print(f"  {'PASS' if ok else 'FALHA':5}  {'V4 raiz inexistente':22} "
              f"esperado=['E14'] obtido={sorted({a.codigo for a in achados_raiz}) or ['-']}")

        parcial = pasta_smoke / "parcial.spec.ts"
        parcial.write_text(
            SMOKE_LIMPO + "\n"
            "test('sem tag', async ({ page }) => {\n"
            "  await page.goto('/x');\n"
            "  await expect(page.getByRole('heading')).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )
        ok = "E9" in {a.codigo for a in analisar_spec(parcial)}
        falhas += not ok
        print(f"  {'PASS' if ok else 'FALHA':5}  {'V4 suíte parcial':22} "
              f"esperado=['E9'] obtido={sorted({a.codigo for a in analisar_spec(parcial)}) or ['-']}")
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

    achados, n_spec, n_po = lint(args.caminho)
    return relatar(achados, n_spec, n_po, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
