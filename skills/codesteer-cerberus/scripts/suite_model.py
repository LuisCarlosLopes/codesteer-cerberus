"""Parser TypeScript compartilhado dos gates Cerberus.

@MindContext: Extração conservadora de casos Playwright, asserções e wrappers
no mesmo processo Python dos gates — sem ponte Node ou Compiler API.
@MindDecision: Identidade de teste é `// test-id:` ou path+título; literais
do matcher não sofrem colapso semântico; forma desconhecida não vira APROVA.
@MindRisk: Análise não promete equivalência semântica geral de TypeScript.
@MindSpec: parse_suite(bytes, path?) → Suite | parse inválido em parse_error;
comparação de prova é por test_id, alvo e ordem, nunca lista global de matchers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Language, Node, Parser, Query, QueryCursor
import tree_sitter_typescript as tsts

TS = Language(tsts.language_typescript())
PARSER = Parser(TS)

Q_EXPECT = Query(
    TS, '(call_expression function: (identifier) @f (#eq? @f "expect")) @call'
)
Q_MOD = Query(
    TS,
    '(member_expression property: (property_identifier) @p'
    ' (#any-of? @p "skip" "fixme" "only"))',
)
Q_AWAIT = Query(TS, "(await_expression) @a")
Q_CALL = Query(TS, "(call_expression) @call")

MAX_TIMEOUT_MS = 30_000
OPTION_KEYS = frozenset(
    {"timeout", "interval", "ignoreCase", "useInnerText", "timeoutMessage"}
)
LITERAL_TYPES = frozenset({"string", "template_string", "regex"})
TEST_LEAFS = frozenset({"test", "test.skip", "test.only", "test.fixme"})
HOOKS = frozenset({
    "test.beforeEach", "test.afterEach", "test.beforeAll", "test.afterAll",
    "test.step", "test.describe.configure", "test.setTimeout", "test.use",
    "test.extend", "test.info",
})

RE_INTENT = re.compile(rb"^\s*//\s*intent:\s*(.+?)\s*$", re.M | re.I)
RE_TEST_ID = re.compile(r"test-id:\s*(\S+)", re.I)
RE_TAG = re.compile(r"@[\w-]+")
RE_NUMERIC = re.compile(r"^[\d_]+$")


def normalizar(texto: str) -> str:
    """Colapsa espaços e uniformiza aspas — só para locator e intent."""
    return re.sub(r"\s+", " ", texto).replace('"', "'").strip()


def normalizar_locator(texto: str) -> str:
    """Formatação fora do endereço não exige prova de alvo."""
    s = normalizar(texto)
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    s = re.sub(r"\s+,", ",", s)
    s = re.sub(r",\s+", ", ", s)
    return s


def extrair_intent(source: bytes) -> str | None:
    m = RE_INTENT.search(source)
    return normalizar(m.group(1).decode("utf-8")) if m else None


@dataclass(frozen=True)
class AssercaoModelo:
    matcher: str
    locator: str
    line: int
    wrapped: str | None = None
    unsupported: str | None = None


@dataclass
class CasoTeste:
    test_id: str
    title: str
    tags: frozenset[str]
    assertions: list[AssercaoModelo]
    start_line: int
    modifiers: set[str] = field(default_factory=set)


@dataclass
class ImportRef:
    source: str
    names: tuple[str, ...]
    dynamic: bool
    resolved: Path | None = None
    outside_root: bool = False


@dataclass
class Suite:
    path: str
    tests: list[CasoTeste]
    assertions: list[AssercaoModelo]
    parse_error: bool
    intent: str | None
    modifiers: set[str]
    steps: int
    timeouts: list[int]
    expect_rebound: bool
    unsupported: list[str]
    imports: list[ImportRef]
    bindings: dict[str, str]


def parse_source(source: bytes) -> tuple[object, bool]:
    tree = PARSER.parse(source)
    return tree, bool(tree.root_node.has_error)


def parse_suite(source: bytes, path: str = "") -> Suite:
    tree, erro = parse_source(source)
    root = tree.root_node
    if erro:
        return Suite(
            path=path, tests=[], assertions=[], parse_error=True,
            intent=extrair_intent(source), modifiers=set(), steps=0,
            timeouts=[], expect_rebound=False, unsupported=["parse inválido"],
            imports=[], bindings={},
        )

    unsupported = _formas_nao_suportadas(root)
    rebound = _expect_rebound(root)
    bindings = _coletar_bindings(root)
    assertions_all = _assercoes_no(root, root)
    tests = _coletar_testes(root, path, bindings)
    if not tests and assertions_all:
        tests = [CasoTeste(
            test_id=path or "<module>",
            title="",
            tags=frozenset(),
            assertions=assertions_all,
            start_line=1,
        )]

    return Suite(
        path=path,
        tests=tests,
        assertions=assertions_all,
        parse_error=False,
        intent=extrair_intent(source),
        modifiers=_modificadores(root),
        steps=_contar_steps(root),
        timeouts=_timeouts_ajuste(root),
        expect_rebound=rebound,
        unsupported=unsupported,
        imports=extrair_imports(source, Path(path) if path else None, None),
        bindings=bindings,
    )


def _texto(node: Node | None) -> str:
    if node is None:
        return ""
    return node.text.decode()


def _filhos_nomeados(node: Node) -> list[Node]:
    return [c for c in node.children if c.is_named]


def _callee(node: Node) -> str:
    fn = node.child_by_field_name("function")
    return _texto(fn)


def _eh_describe(nome: str) -> bool:
    return nome == "test.describe" or nome.startswith("test.describe.")


def _eh_teste(nome: str) -> bool:
    return nome in TEST_LEAFS


def _string_titulo(node: Node | None) -> str:
    if node is None:
        return ""
    if node.type in ("string", "template_string"):
        raw = _texto(node)
        if raw.startswith(("'", '"', "`")) and raw.endswith(raw[0]) and len(raw) >= 2:
            return raw[1:-1]
        return raw
    return _texto(node)


def _tags_em(texto: str) -> frozenset[str]:
    return frozenset(t.lower() for t in RE_TAG.findall(texto or ""))


def _tags_de_opcoes(obj: Node | None) -> frozenset[str]:
    if obj is None or obj.type != "object":
        return frozenset()
    tags: set[str] = set()
    for child in obj.children:
        if child.type != "pair":
            continue
        key = child.child_by_field_name("key")
        val = child.child_by_field_name("value")
        if _texto(key).strip("\"'") != "tag" or val is None:
            continue
        for item in val.children:
            if item.type in ("string", "template_string"):
                tags |= _tags_em(_string_titulo(item))
    return frozenset(tags)


def _comentario_test_id(node: Node) -> str | None:
    parent = node.parent
    if parent is None:
        return None
    filhos = list(parent.children)
    try:
        idx = filhos.index(node)
    except ValueError:
        return None
    for i in range(idx - 1, -1, -1):
        sib = filhos[i]
        if sib.type == "comment":
            m = RE_TEST_ID.search(_texto(sib))
            if m:
                return m.group(1)
            continue
        if sib.is_named:
            break
    return None


def _identidade_teste(node: Node, path: str, describes: list[str], title: str) -> str:
    explicit = _comentario_test_id(node)
    if explicit:
        return explicit
    prefix = "::".join([p for p in (path, *describes, title) if p])
    return prefix or title or "<anonymous>"


def _corpo_do_callback(args: Node | None) -> Node | None:
    if args is None:
        return None
    callbacks = [
        c for c in _filhos_nomeados(args)
        if c.type in ("arrow_function", "function_expression", "function_declaration")
    ]
    return callbacks[-1] if callbacks else None


def _args_teste(node: Node) -> tuple[str, frozenset[str], Node | None]:
    args = node.child_by_field_name("arguments")
    if args is None:
        return "", frozenset(), None
    named = _filhos_nomeados(args)
    title = _string_titulo(named[0]) if named else ""
    options = next((n for n in named if n.type == "object"), None)
    tags = _tags_em(title) | _tags_de_opcoes(options)
    return title, tags, _corpo_do_callback(args)


def _coletar_testes(root: Node, path: str, bindings: dict[str, str]) -> list[CasoTeste]:
    testes: list[CasoTeste] = []

    def visitar(node: Node, describes: list[str], herdadas: frozenset[str]) -> None:
        if node.type == "call_expression":
            nome = _callee(node)
            if _eh_describe(nome):
                title, tags, body = _args_teste(node)
                novas = herdadas | tags
                if body is not None:
                    visitar(body, describes + [title], novas)
                return
            if _eh_teste(nome):
                title, tags, body = _args_teste(node)
                todas = herdadas | tags
                assercoes = _assercoes_no(body, body) if body is not None else []
                mods = set()
                if nome.endswith(".skip"):
                    mods.add("skip")
                elif nome.endswith(".only"):
                    mods.add("only")
                elif nome.endswith(".fixme"):
                    mods.add("fixme")
                testes.append(CasoTeste(
                    test_id=_identidade_teste(node, path, describes, title),
                    title=title,
                    tags=todas,
                    assertions=assercoes,
                    start_line=node.start_point[0] + 1,
                    modifiers=mods,
                ))
                return
        for child in node.children:
            visitar(child, describes, herdadas)

    visitar(root, [], frozenset())
    return testes


def _cadeia_expect(node: Node) -> tuple[str, str, str | None]:
    """Devolve (matcher_id, locator_norm, unsupported)."""
    args = node.child_by_field_name("arguments")
    locator = normalizar_locator(_texto(args)) if args else ""
    cur, cadeia = node, []
    unsupported = None
    while cur.parent and cur.parent.type in (
        "member_expression", "call_expression", "await_expression",
    ):
        cur = cur.parent
        if cur.type == "member_expression":
            prop = cur.child_by_field_name("property")
            if prop is None:
                continue
            if not prop.is_named or prop.type not in (
                "property_identifier", "identifier",
            ):
                unsupported = "matcher computado"
            cadeia.append(_texto(prop))
        elif cur.type == "call_expression" and cadeia:
            cargs = cur.child_by_field_name("arguments")
            cadeia[-1] += _args_matcher(cargs)
    if not cadeia:
        unsupported = unsupported or "asserção sem matcher"
    return ".".join(cadeia), locator, unsupported


def _args_matcher(args: Node | None) -> str:
    if args is None:
        return ""
    named = _filhos_nomeados(args)
    if not named:
        return collapse_fora_literais(args)
    last = named[-1]
    if last.type == "object" and _eh_objeto_opcoes(last):
        kept = [n for n in named[:-1]]
        resto = _objeto_sem_timeout(last)
        partes = [collapse_fora_literais(n) for n in kept]
        if resto:
            partes.append(resto)
        corpo = ", ".join(p for p in partes if p)
        return f"({corpo})" if corpo else "()"
    return collapse_fora_literais(args)


def _eh_objeto_opcoes(obj: Node) -> bool:
    keys = _chaves_objeto(obj)
    return bool(keys) and keys <= OPTION_KEYS


def _chaves_objeto(obj: Node) -> set[str]:
    keys: set[str] = set()
    for child in obj.children:
        if child.type != "pair":
            continue
        key = child.child_by_field_name("key")
        if key is None:
            continue
        keys.add(_texto(key).strip("\"'"))
    return keys


def _objeto_sem_timeout(obj: Node) -> str:
    pares = []
    for child in obj.children:
        if child.type != "pair":
            continue
        key = child.child_by_field_name("key")
        val = child.child_by_field_name("value")
        if key is None:
            continue
        if _texto(key).strip("\"'") == "timeout":
            continue
        pares.append(
            f"{collapse_fora_literais(key)}: {collapse_fora_literais(val) if val else ''}"
        )
    if not pares:
        return ""
    return "{ " + ", ".join(pares) + " }"


def collapse_fora_literais(node: Node | None) -> str:
    """Colapsa whitespace fora de string/template/regex; literais ficam literais."""
    if node is None:
        return ""
    raw = _texto(node)
    start = node.start_byte
    spans: list[tuple[int, int]] = []

    def coletar(n: Node) -> None:
        if n.type in LITERAL_TYPES:
            spans.append((n.start_byte - start, n.end_byte - start))
            return
        for c in n.children:
            coletar(c)

    coletar(node)
    spans.sort()
    out: list[str] = []
    i = 0
    for a, b in spans:
        out.append(re.sub(r"\s+", " ", raw[i:a]))
        out.append(raw[a:b])
        i = b
    out.append(re.sub(r"\s+", " ", raw[i:]))
    return "".join(out).strip()


def _wrapper_de(expect_node: Node, corpo: Node | None) -> str | None:
    if corpo is None:
        return None
    cur: Node | None = expect_node
    while cur is not None and cur != corpo:
        parent = cur.parent
        if parent is None:
            break
        if parent.type == "if_statement":
            return "condicional impede prova"
        if parent.type in ("try_statement", "catch_clause", "finally_clause"):
            return "catch/try envolve asserção"
        if parent.type == "ternary_expression":
            return "condicional impede prova"
        if parent.type == "binary_expression":
            op = parent.child_by_field_name("operator")
            if op is None:
                for c in parent.children:
                    if not c.is_named and _texto(c).strip() in {"&&", "||", "??"}:
                        return "condicional impede prova"
            elif _texto(op).strip() in {"&&", "||", "??"}:
                return "condicional impede prova"
        if parent.type in (
            "arrow_function", "function_expression", "function_declaration",
        ) and parent != corpo:
            return "callback envolve asserção"
        if parent.type == "return_statement" and parent != expect_node.parent:
            # `return expect(...)` no callback do teste ainda executa a prova.
            # return que envolve um bloco maior é tratado pelo walk de irmãos.
            pass
        cur = parent
    if _retorno_antecipado(corpo, expect_node):
        return "retorno antecipado impede prova"
    return None


def _retorno_antecipado(corpo: Node, expect_node: Node) -> bool:
    """Return que precede o expect no mesmo bloco do callback do teste."""
    bloco = corpo.child_by_field_name("body") or corpo
    expect_start = expect_node.start_byte

    def varrer(n: Node) -> bool:
        if n.start_byte >= expect_start:
            return False
        if n.type == "return_statement" and n.start_byte < expect_start:
            # return do próprio expect (return expect(...)) não impede
            if "expect(" in _texto(n) and n.end_byte >= expect_start:
                return False
            return True
        for c in n.children:
            if varrer(c):
                return True
        return False

    return varrer(bloco)


def _assercoes_no(escopo: Node | None, corpo: Node | None) -> list[AssercaoModelo]:
    if escopo is None:
        return []
    out: list[AssercaoModelo] = []
    for node in QueryCursor(Q_EXPECT).captures(escopo).get("call", []):
        matcher, locator, uns = _cadeia_expect(node)
        out.append(AssercaoModelo(
            matcher=matcher,
            locator=locator,
            line=node.start_point[0] + 1,
            wrapped=_wrapper_de(node, corpo),
            unsupported=uns,
        ))
    return out


def _modificadores(root: Node) -> set[str]:
    return {n.text.decode() for n in QueryCursor(Q_MOD).captures(root).get("p", [])}


def _contar_steps(root: Node) -> int:
    awaits = QueryCursor(Q_AWAIT).captures(root).get("a", [])
    return sum(1 for n in awaits if "expect(" not in n.text.decode())


def _parse_numero(texto: str) -> int | None:
    s = texto.strip().replace("_", "")
    if not s or not RE_NUMERIC.match(texto.strip()):
        return None
    try:
        return int(s, 10)
    except ValueError:
        return None


def _timeouts_ajuste(root: Node) -> list[int]:
    """Timeouts de opção de matcher/caso — não literais dentro de dado."""
    valores: list[int] = []

    def visitar(n: Node) -> None:
        if n.type == "pair":
            key = n.child_by_field_name("key")
            val = n.child_by_field_name("value")
            if key is not None and _texto(key).strip("\"'") == "timeout" and val is not None:
                obj = n.parent
                if obj is not None and obj.type == "object" and _eh_objeto_opcoes(obj):
                    parsed = _parse_numero(_texto(val))
                    if parsed is not None:
                        valores.append(parsed)
                    else:
                        valores.append(MAX_TIMEOUT_MS + 1)
        if n.type == "call_expression" and _callee(n) in {
            "test.setTimeout", "setTimeout",
        }:
            args = n.child_by_field_name("arguments")
            named = _filhos_nomeados(args) if args is not None else []
            if named:
                parsed = _parse_numero(_texto(named[0]))
                if parsed is not None:
                    valores.append(parsed)
        for c in n.children:
            visitar(c)

    visitar(root)
    return valores


def timeouts_acima_do_teto(source: bytes) -> list[int]:
    tree, erro = parse_source(source)
    if erro:
        return []
    return [v for v in _timeouts_ajuste(tree.root_node) if v > MAX_TIMEOUT_MS]


def _expect_rebound(root: Node) -> bool:
    for n in _andar(root):
        if n.type == "variable_declarator":
            name = n.child_by_field_name("name")
            if name is not None and _contem_expect(name):
                return True
        if n.type == "assignment_expression":
            left = n.child_by_field_name("left")
            if left is not None and _texto(left) == "expect":
                return True
        if n.type == "import_specifier":
            name = n.child_by_field_name("name")
            alias = n.child_by_field_name("alias")
            if alias is not None and _texto(name) == "expect":
                return True
            if alias is None and _texto(name) == "expect":
                # import { expect } é o binding canônico — não é rebind
                continue
        if n.type == "import_clause":
            default = next(
                (c for c in n.children if c.type == "identifier"), None
            )
            if default is not None and _texto(default) == "expect":
                return True
    return False


def _contem_expect(node: Node) -> bool:
    if node.type in ("identifier", "property_identifier", "shorthand_property_identifier"):
        return _texto(node) == "expect"
    return any(_contem_expect(c) for c in node.children if c.is_named)


def _formas_nao_suportadas(root: Node) -> list[str]:
    achados: list[str] = []
    for node in QueryCursor(Q_CALL).captures(root).get("call", []):
        fn = node.child_by_field_name("function")
        if fn is None:
            continue
        if fn.type == "import":
            achados.append("import dinâmico")
            continue
        nome = _texto(fn)
        if nome in {"eval", "Function"} or nome.endswith(".Function"):
            achados.append("eval/Function")
        if fn.type == "member_expression":
            obj = fn.child_by_field_name("object")
            prop = fn.child_by_field_name("property")
            if _texto(obj) == "expect" and _texto(prop) in {"soft", "poll"}:
                achados.append(f"expect.{_texto(prop)}")
            if prop is not None and not prop.is_named:
                if _texto(obj) == "expect":
                    achados.append("matcher computado")
    return achados


def _coletar_bindings(root: Node) -> dict[str, str]:
    binds: dict[str, str] = {}
    for n in _andar(root):
        if n.type == "variable_declarator":
            name = n.child_by_field_name("name")
            value = n.child_by_field_name("value")
            if name is not None and name.type == "identifier":
                binds[_texto(name)] = collapse_fora_literais(value) if value else ""
        elif n.type == "assignment_expression":
            left = n.child_by_field_name("left")
            right = n.child_by_field_name("right")
            if left is not None and left.type == "identifier":
                binds[_texto(left)] = collapse_fora_literais(right) if right else ""
    return binds


def enriquecer_matcher(matcher: str, locator_bruto: str, bindings: dict[str, str]) -> str:
    ids = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", matcher))
    extras = []
    for name in sorted(ids):
        if name in bindings and name not in {
            "expect", "page", "test", "toBeVisible", "toHaveText",
            "toBeAttached", "toHaveValue", "toBeEnabled", "toBeDisabled",
            "toBeHidden", "toContainText", "toHaveCount", "not",
        }:
            extras.append(f"{name}={bindings[name]}")
    if extras:
        return matcher + "|" + ",".join(extras)
    return matcher


def _andar(node: Node):
    yield node
    for c in node.children:
        yield from _andar(c)


def extrair_imports(
    source: bytes,
    file_path: Path | None,
    authorized_root: Path | None,
) -> list[ImportRef]:
    tree, erro = parse_source(source)
    if erro:
        return []
    refs: list[ImportRef] = []
    for n in _andar(tree.root_node):
        if n.type == "import_statement":
            src_node = n.child_by_field_name("source")
            src = _string_titulo(src_node)
            names: list[str] = []
            for c in _andar(n):
                if c.type in ("import_specifier", "identifier", "namespace_import"):
                    ident = c.child_by_field_name("name") if c.type == "import_specifier" else None
                    if ident is not None:
                        names.append(_texto(ident))
            resolved, outside = _resolver_local(src, file_path, authorized_root)
            refs.append(ImportRef(src, tuple(names), False, resolved, outside))
        elif n.type == "call_expression" and _callee(n) == "import":
            args = n.child_by_field_name("arguments")
            named = _filhos_nomeados(args) if args is not None else []
            src = _string_titulo(named[0]) if named else ""
            refs.append(ImportRef(src, (), True, None, False))
    return refs


def _resolver_local(
    spec: str,
    file_path: Path | None,
    authorized_root: Path | None,
) -> tuple[Path | None, bool]:
    if not spec or not spec.startswith("."):
        return None, False
    if file_path is None:
        return None, False
    base = (file_path.parent / spec).resolve()
    candidatos = [
        base,
        Path(str(base) + ".ts"),
        Path(str(base) + ".tsx"),
        Path(str(base) + ".js"),
        base / "index.ts",
    ]
    achado = next((c for c in candidatos if c.is_file()), None)
    if achado is None:
        return None, False
    if authorized_root is not None:
        try:
            achado.resolve().relative_to(authorized_root.resolve())
        except ValueError:
            return achado, True
    return achado, False


def casos_por_id(suite: Suite) -> dict[str, CasoTeste]:
    return {c.test_id: c for c in suite.tests}


def eh_smoke_caso(caso: CasoTeste) -> bool:
    return "@smoke" in caso.tags
