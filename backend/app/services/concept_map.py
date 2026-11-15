"""Construcción del mapa conceptual a partir de la estructura del documento.

Todo es determinista y se basa en evidencia textual:
  1. Raíz = título del documento; cada sección/subsección = un concepto hijo (jerarquía documental).
  2. Definiciones explícitas («X se define como…», «X es un…») y elementos «Término: explicación».
  3. Elementos de lista como conceptos subordinados de su sección.
  4. Términos repetidos (palabras y frases frecuentes) como conceptos «provisionales».
  5. Relaciones transversales: conector explícito entre dos conceptos en la misma oración
     («A permite B», «A se compone de B»); si solo hay co-mención, la relación es provisional.

El algoritmo NO interpreta el significado del texto: cuando no hay evidencia clara marca
el elemento como provisional para que una persona lo revise.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from ..schemas import ConceptMap, MapEdge, MapNode
from .structure import Block, DocumentStructure, Section
from .text_utils import (
    ARTICLES, CLAUSE_WORDS, STOPWORDS, capitalize_first, clean_label, normalize,
    split_sentences, tokens_with_breaks, truncate,
)

ALGORITHM = "edumap-reglas-1"
MAX_NODES = 400
MAX_LIST_ITEMS_PER_SECTION = 25
MAX_DEFINITIONS_PER_SECTION = 8
MAX_KEYWORDS_PER_SECTION = 4
MAX_KEYWORDS_TOTAL = 20
MAX_EXPLICIT_EDGES = 60
MAX_CROSS_EDGES = 30
MAX_CROSS_PER_NODE = 2

# (conector tal como aparece en el texto, etiqueta de la relación)
_DEFINITION_CONNECTORS = [
    ("se define como", "se define como"), ("se entiende como", "se entiende como"),
    ("se entiende por", "se entiende como"), ("se denomina", "se denomina"), ("se llama", "se llama"),
    ("se conoce como", "se conoce como"), ("hace referencia a", "hace referencia a"),
    ("se refiere a", "se refiere a"), ("consiste en", "consiste en"),
    ("es una", "es"), ("es un", "es"), ("es el", "es"), ("es la", "es"), ("es lo", "es"),
    ("son los", "son"), ("son las", "son"), ("son unos", "son"), ("son unas", "son"),
    ("son un", "son"), ("son una", "son"),
]
_DEF_LABELS = {c: lab for c, lab in _DEFINITION_CONNECTORS}
_DEF_RE = re.compile(
    r"^(?P<term>[^,;:.!?]{2,90}?)\s+(?P<conn>"
    + "|".join(re.escape(c) for c, _ in sorted(_DEFINITION_CONNECTORS, key=lambda x: -len(x[0])))
    + r")\s+(?P<rest>\S.{8,})$",
    re.IGNORECASE,
)
_LEAD_RE = re.compile(
    r"^Se (?:entiende|define|denomina|llama|conoce) (?:por|como)\s+(?P<term>[^,:;]{2,70})[,:]\s+(?P<rest>\S.{8,})$",
    re.IGNORECASE,
)
_COLON_RE = re.compile(r"^(?P<term>[^:.!?]{2,60}):\s+(?P<rest>\S.{15,})$")
_COLON_BLOCKLIST = {
    "nota", "figura", "tabla", "autor", "autores", "titulo", "fuente", "ejemplo", "ejemplos",
    "por ejemplo", "importante", "observacion", "atencion", "referencias",
}

_RELATION_CONNECTORS = [
    "se compone de", "está compuesto por", "está compuesta por", "está formado por", "está formada por",
    "forma parte de", "es parte de", "se divide en", "se clasifica en", "se clasifican en", "se organiza en",
    "incluye", "incluyen", "comprende", "permite", "permiten", "facilita", "facilitan", "favorece",
    "reduce", "aumenta", "genera", "produce", "provoca", "causa", "depende de", "dependen de",
    "se basa en", "se apoya en", "se relaciona con", "se asocia con", "se integra con", "contribuye a",
    "afecta a", "requiere", "utiliza", "utilizan", "estudia", "estudian", "explica", "explican",
    "organiza", "organizan", "almacena", "almacenan", "procesa", "procesan", "recibe", "reciben",
]
_REL_LOOKUP = {normalize(c): c for c in _RELATION_CONNECTORS}
_REL_RE = re.compile(
    r"(?:(?:no|tambien|solo|siempre|puede|pueden|suele|suelen)\s+)*("
    + "|".join(re.escape(k) for k in sorted(_REL_LOOKUP, key=len, reverse=True))
    + r")(?:\s+(?:a|de|en|con|por|el|la|los|las|un|una|unos|unas|del|al|lo))*"
)


_REFERENCE_TITLE = re.compile(
    r"^(referencias?(?: bibliograficas?| apa)?|bibliografia|references|bibliography|fuentes consultadas|obras citadas)$"
)
# Palabras demasiado genéricas para ser términos clave (no aportan al mapa)
_GENERIC_TERMS = frozenset(
    """figura tabla elaboración respecto propia nota página capítulo sección apartado siguiente siguientes
    anterior presente actual actuales general generales diferentes distintos distintas mismo misma mismos
    mismas varios varias través medio ejemplo ejemplos parte partes resultado resultados""".split()
)


@dataclass
class _Passage:
    sentence: str
    paragraph: str
    page: int


@dataclass
class _SectionInfo:
    node_id: str
    title: str
    passages: list[_Passage]


# --------------------------------------------------------------------------- términos
def _valid_term(term: str) -> str | None:
    term = term.strip(" \t\"'“”«»*_")
    if re.search(r"\(\s*[^)]*\d{4}", term):          # parece una cita (Autor, 2021)
        return None
    tokens = term.split()
    while tokens and tokens[0].lower() in ARTICLES:
        tokens = tokens[1:]
    if not tokens or len(tokens) > 7:
        return None
    low = [t.lower().strip("()") for t in tokens]
    if low[0] in STOPWORDS or low[-1] in STOPWORDS:
        return None
    if any(t in CLAUSE_WORDS for t in low):
        return None
    if not any(sum(ch.isalpha() for ch in t) >= 4 for t in low):
        return None
    return " ".join(tokens)


def _colon_term(text: str, max_words: int) -> tuple[str, str] | None:
    m = _COLON_RE.match(text)
    if not m:
        return None
    term = _valid_term(m.group("term"))
    if not term or len(term.split()) > max_words or normalize(term) in _COLON_BLOCKLIST:
        return None
    if not m.group("term").strip()[:1].isupper():
        return None
    return term, m.group("rest").strip()


def find_definition(sentence: str) -> tuple[str, str, int, int] | None:
    """Si la oración es una definición explícita devuelve (término, relación, inicio, fin),
    donde inicio/fin delimitan el término dentro de la oración original."""
    m = _LEAD_RE.match(sentence)
    relation = "se entiende como"
    if not m:
        m = _DEF_RE.match(sentence)
        if not m:
            return None
        relation = _DEF_LABELS[m.group("conn").lower()]
    raw = m.group("term")
    term = _valid_term(raw)
    if not term:
        return None
    offset = raw.find(term)
    if offset < 0:
        return None
    begin = m.start("term") + offset
    return term, relation, begin, begin + len(term)


def _definition(sentence: str) -> tuple[str, str] | None:
    """Devuelve (término, etiqueta de relación) si la oración es una definición explícita."""
    found = find_definition(sentence)
    return (found[0], found[1]) if found else None


_DETERMINERS = frozenset(
    "el la los las un una unos unas del al este esta estos estas ese esa cada su sus otro otra otros otras".split()
)


def _ngrams(sentence: str, nominal: bool = False) -> list[tuple[str, bool]]:
    """Candidatos a término (palabras y frases) con un indicio de que son frases nominales:
    van precedidos por un artículo/determinante («la carga», «el estudiante»)."""
    toks = tokens_with_breaks(sentence)

    def content(t: str | None) -> bool:
        return t is not None and len(t) >= 4 and t not in STOPWORDS and t not in _GENERIC_TERMS

    out: list[tuple[str, bool]] = []
    n = len(toks)
    for i, t in enumerate(toks):
        if not content(t):
            continue
        noun = nominal or (i > 0 and toks[i - 1] in _DETERMINERS)
        out.append((t, noun))
        if i + 1 < n and content(toks[i + 1]):
            out.append((f"{t} {toks[i + 1]}", noun))
        if i + 2 < n and toks[i + 1] in ("de", "del") and content(toks[i + 2]):
            out.append((f"{t} {toks[i + 1]} {toks[i + 2]}", noun))
        if i + 3 < n and toks[i + 1] == "de" and toks[i + 2] in ("la", "el", "los", "las") and content(toks[i + 3]):
            out.append((f"{t} de {toks[i + 2]} {toks[i + 3]}", noun))
    return out


def _contains_words(haystack_norm: str, needle_norm: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(needle_norm)}(?!\w)", haystack_norm))


# --------------------------------------------------------------------------- constructor
class _Builder:
    def __init__(self, project_id: str, document_id: str):
        self.project_id = project_id
        self.document_id = document_id
        self.nodes: list[MapNode] = []
        self.edges: list[MapEdge] = []
        self.by_label: dict[str, str] = {}            # etiqueta normalizada -> id
        self.pairs: set[frozenset[str]] = set()       # pares ya conectados
        self.sections: list[_SectionInfo] = []
        self.warnings: list[str] = []
        self.capped = False

    # -- primitivas
    def add_node(self, label: str, kind: str, *, parent: str | None, description: str = "",
                 source_text: str = "", page: int | None = None, provisional: bool = False,
                 edge_label: str = "contiene", edge_provisional: bool = False) -> MapNode | None:
        if kind not in ("root", "section") and len(self.nodes) >= MAX_NODES:
            self.capped = True
            return None
        node = MapNode(id=f"concepto-{len(self.nodes) + 1:03d}", label=label, kind=kind,
                       description=truncate(description, 600) if description else "",
                       sourceText=truncate(source_text, 900) if source_text else "",
                       sourcePage=page, parentId=parent, provisional=provisional)
        self.nodes.append(node)
        self.by_label.setdefault(normalize(label), node.id)
        if parent:
            self.add_edge(parent, node.id, edge_label, "hierarchy", provisional=edge_provisional)
        return node

    def add_edge(self, source: str, target: str, label: str, kind: str, *, provisional: bool = False,
                 source_text: str = "", page: int | None = None) -> None:
        self.edges.append(MapEdge(id=f"relacion-{len(self.edges) + 1:03d}", source=source, target=target,
                                  label=label, kind=kind, provisional=provisional,
                                  sourceText=truncate(source_text, 600) if source_text else "",
                                  sourcePage=page))
        self.pairs.add(frozenset((source, target)))

    # -- contenido de una sección (o de la raíz)
    def process_blocks(self, blocks: list[Block], parent: MapNode, passages: list[_Passage]) -> None:
        definitions = 0
        list_items = 0
        skipped_items = 0
        for block in blocks:
            if block.kind == "paragraph":
                sentences = split_sentences(block.text)
                for s in sentences:
                    passages.append(_Passage(s, block.text, block.page))
                colon = _colon_term(block.text, 4)
                if colon and normalize(colon[0]) not in self.by_label:
                    self.add_node(clean_label(capitalize_first(colon[0])), "definition", parent=parent.id,
                                  description=colon[1], source_text=block.text, page=block.page,
                                  edge_label="se describe como")
                    continue
                for s in sentences:
                    if definitions >= MAX_DEFINITIONS_PER_SECTION:
                        break
                    found = _definition(s)
                    if not found or normalize(found[0]) in self.by_label:
                        continue
                    if self.add_node(clean_label(capitalize_first(found[0])), "definition", parent=parent.id,
                                     description=s, source_text=block.text, page=block.page,
                                     edge_label=found[1]):
                        definitions += 1
            else:
                passages.append(_Passage(block.text, block.text, block.page))
                if list_items >= MAX_LIST_ITEMS_PER_SECTION:
                    skipped_items += 1
                    continue
                text = block.text.strip().rstrip(".;, ")
                colon = _colon_term(text, 6)
                provisional = False
                if colon:
                    label, description = clean_label(capitalize_first(colon[0])), colon[1]
                elif len(text.split()) <= 12:
                    label, description = clean_label(capitalize_first(text), 120), ""
                else:
                    label = capitalize_first(" ".join(text.split()[:8])) + "…"
                    description, provisional = text, True
                if not label or normalize(label) in self.by_label:
                    continue
                if self.add_node(label, "list_item", parent=parent.id, description=description,
                                 source_text=block.text, page=block.page, provisional=provisional,
                                 edge_label="incluye"):
                    list_items += 1
        if skipped_items:
            self.warnings.append(
                f"La sección «{parent.label}» tiene {skipped_items} elemento(s) de lista más que no "
                f"se convirtieron en conceptos (límite de {MAX_LIST_ITEMS_PER_SECTION} por sección)."
            )

    def process_section(self, section: Section, parent: MapNode, *, provisional: bool = False) -> None:
        paragraphs = [b for b in section.blocks if b.kind == "paragraph"]
        description = ""
        if paragraphs:
            description = " ".join(split_sentences(paragraphs[0].text)[:2])
        source = " ".join(b.text for b in paragraphs[:2])
        node = self.add_node(section.title, "section", parent=parent.id, description=description,
                             source_text=source or section.raw_title, page=section.page,
                             provisional=provisional, edge_provisional=provisional)
        assert node is not None
        passages: list[_Passage] = []
        if _REFERENCE_TITLE.match(normalize(section.title)):
            self.warnings.append(f"La sección «{section.title}» es una lista de referencias y no se convirtió en conceptos.")
            self.sections.append(_SectionInfo(node.id, section.title, passages))
            return
        self.process_blocks(section.blocks, node, passages)
        self.sections.append(_SectionInfo(node.id, section.title, passages))
        for child in section.children:
            self.process_section(child, node)

    # -- términos repetidos
    def add_keywords(self) -> None:
        per_section: list[Counter[str]] = []
        support: Counter[str] = Counter()
        for info in self.sections:
            counter: Counter[str] = Counter()
            for p in info.passages:
                for term, noun in _ngrams(p.sentence):
                    counter[term] += 1
                    support[term] += noun
            for term, _ in _ngrams(info.title, nominal=True):     # los títulos pesan el doble
                counter[term] += 2
                support[term] += 2
            per_section.append(counter)
        total: Counter[str] = Counter()
        for c in per_section:
            total.update(c)
        n_tokens = sum(v for k, v in total.items() if " " not in k)
        min_uni = 3 + n_tokens // 2000
        min_multi = 2 + n_tokens // 4000

        def score(term: str) -> float:
            content = len([w for w in term.split() if w not in STOPWORDS])
            return total[term] * (1 + 0.5 * (content - 1))

        candidates = [
            t for t, f in total.items()
            if (" " not in t and f >= min_uni and support[t] >= 2)
            or (" " in t and f >= min_multi and support[t] >= 1)
        ]
        candidates.sort(key=lambda t: (-score(t), t))
        limit = min(MAX_KEYWORDS_TOTAL, max(5, len(self.sections)))
        chosen: list[str] = []
        for term in candidates:
            if len(chosen) >= limit:
                break
            norm = normalize(term)
            if any(_contains_words(label, norm) or _contains_words(norm, label) for label in self.by_label):
                continue
            if any(_contains_words(normalize(c), norm) and total[c] >= 0.7 * total[term] for c in chosen):
                continue
            chosen.append(term)

        used: Counter[int] = Counter()
        for term in chosen:
            ranking = sorted(range(len(self.sections)), key=lambda i: (-per_section[i][term], i))
            target = next((i for i in ranking
                           if per_section[i][term] > 0 and used[i] < MAX_KEYWORDS_PER_SECTION), None)
            if target is None:
                continue
            info = self.sections[target]
            norm = normalize(term)
            passage = next((p for p in info.passages if _contains_words(normalize(p.sentence), norm)), None)
            node = self.add_node(capitalize_first(term), "keyword", parent=info.node_id, provisional=True,
                                 description=passage.sentence if passage else "",
                                 source_text=passage.paragraph if passage else info.title,
                                 page=passage.page if passage else None,
                                 edge_label="término clave", edge_provisional=True)
            if node:
                used[target] += 1

    # -- relaciones transversales
    def add_relations(self) -> None:
        concept_nodes = [n for n in self.nodes
                         if n.kind != "root" and len(normalize(n.label)) >= 4 and not n.label.endswith("…")]
        by_length = sorted(concept_nodes, key=lambda n: (-len(normalize(n.label)), n.id))
        labels = {n.id: normalize(n.label) for n in concept_nodes}

        explicit = 0
        seen_sentences: set[str] = set()
        for info in self.sections:
            for p in info.passages:
                if p.sentence in seen_sentences or explicit >= MAX_EXPLICIT_EDGES:
                    continue
                seen_sentences.add(p.sentence)
                norm = normalize(p.sentence)
                claimed: list[tuple[int, int, str]] = []
                for n in by_length:
                    lab = labels[n.id]
                    if lab not in norm:
                        continue
                    for m in re.finditer(rf"(?<!\w){re.escape(lab)}(?!\w)", norm):
                        if not any(m.start() < e and m.end() > s for s, e, _ in claimed):
                            claimed.append((m.start(), m.end(), n.id))
                claimed.sort()
                for (s1, e1, a), (s2, e2, b) in zip(claimed, claimed[1:]):
                    between = norm[e1:s2].strip()
                    if a == b or len(between) > 50 or frozenset((a, b)) in self.pairs:
                        continue
                    conn = _REL_RE.fullmatch(between)
                    if conn and explicit < MAX_EXPLICIT_EDGES:
                        self.add_edge(a, b, _REL_LOOKUP[conn.group(1)], "explicit",
                                      source_text=p.sentence, page=p.page)
                        explicit += 1

        ancestors = self._ancestors()
        cross = 0
        for n in self.nodes:
            if n.kind not in ("definition", "list_item") or not n.description:
                continue
            text = normalize(n.description)
            made = 0
            for other in (c for c in concept_nodes if c.kind != "keyword"):
                if cross >= MAX_CROSS_EDGES or made >= MAX_CROSS_PER_NODE:
                    break
                if other.id == n.id or other.id in ancestors[n.id] or frozenset((n.id, other.id)) in self.pairs:
                    continue
                if _contains_words(text, labels[other.id]):
                    self.add_edge(n.id, other.id, "se relaciona con", "cross", provisional=True,
                                  source_text=n.description, page=n.sourcePage)
                    made += 1
                    cross += 1

    def _ancestors(self) -> dict[str, set[str]]:
        parent = {n.id: n.parentId for n in self.nodes}
        out: dict[str, set[str]] = {}
        for n in self.nodes:
            chain: set[str] = set()
            cur = parent[n.id]
            while cur:
                chain.add(cur)
                cur = parent[cur]
            out[n.id] = chain
        return out



def build_concept_map(structure: DocumentStructure, *, project_id: str, document_id: str,
                      extraction_method: str) -> ConceptMap:
    b = _Builder(project_id, document_id)
    preamble_paragraphs = [blk for blk in structure.preamble if blk.kind == "paragraph"]
    root = b.add_node(
        structure.title, "root", parent=None,
        description=" ".join(split_sentences(preamble_paragraphs[0].text)[:2]) if preamble_paragraphs else "",
        source_text=structure.title, page=structure.title_page,
        provisional=structure.title_source != "document",
    )
    assert root is not None

    sections = structure.sections
    preamble = structure.preamble
    pseudo = False
    if not sections and preamble:
        # Sin títulos: se agrupa por página (estructura mínima, marcada como provisional)
        pseudo = True
        pages: dict[int, list[Block]] = {}
        for blk in preamble:
            pages.setdefault(blk.page, []).append(blk)
        sections = [Section(title=f"Página {p}", raw_title=f"Página {p}", level=1, page=p, blocks=blks)
                    for p, blks in sorted(pages.items())]
        preamble = []

    root_passages: list[_Passage] = []
    b.process_blocks(preamble, root, root_passages)
    b.sections.append(_SectionInfo(root.id, structure.title, root_passages))
    for section in sections:
        b.process_section(section, root, provisional=pseudo)

    b.add_keywords()
    b.add_relations()

    warnings = list(structure.warnings)
    warnings.extend(b.warnings)
    if b.capped:
        warnings.append(f"Se alcanzó el límite de {MAX_NODES} conceptos; parte del contenido no se representó.")
    provisional = sum(n.provisional for n in b.nodes) + sum(e.provisional for e in b.edges)
    if provisional:
        warnings.append(
            f"{provisional} elemento(s) del mapa son provisionales (marcados «Revisar»): el algoritmo no "
            "tuvo evidencia explícita en el texto y se recomienda confirmarlos o corregirlos."
        )
    if len(b.nodes) <= 1:
        warnings.append("No se identificaron conceptos suficientes en el documento.")

    return ConceptMap(
        id=project_id, documentId=document_id, title=structure.title, nodes=b.nodes, edges=b.edges,
        warnings=warnings,
        meta={"algorithm": ALGORITHM, "extractionMethod": extraction_method,
              "pageCount": structure.page_count, "headingCount": structure.heading_count},
    )


def normalize_hierarchy(cmap: ConceptMap) -> ConceptMap:
    """Garantiza que las aristas jerárquicas coincidan exactamente con parentId."""
    by_id = {n.id: n for n in cmap.nodes}
    kept: list[MapEdge] = []
    have: set[tuple[str, str]] = set()
    for e in cmap.edges:
        if e.kind == "hierarchy":
            if by_id[e.target].parentId == e.source and (e.source, e.target) not in have:
                kept.append(e)
                have.add((e.source, e.target))
        else:
            kept.append(e)
    used = {e.id for e in kept}
    counter = len(kept)
    for n in cmap.nodes:
        if n.parentId and (n.parentId, n.id) not in have:
            counter += 1
            while f"relacion-{counter:03d}" in used:
                counter += 1
            eid = f"relacion-{counter:03d}"
            used.add(eid)
            kept.append(MapEdge(id=eid, source=n.parentId, target=n.id, label="contiene",
                                kind="hierarchy", provisional=True))
    return cmap.model_copy(update={"edges": kept})


# --- API pública para otros módulos (p. ej. cuestionarios): mismas reglas que usa el mapa ---------------------
colon_term = _colon_term
ngram_candidates = _ngrams
contains_words = _contains_words


def match_relation_connector(between_norm: str) -> str | None:
    """Etiqueta del conector si el tramo (normalizado) entre dos conceptos es un conector explícito."""
    m = _REL_RE.fullmatch(between_norm)
    return _REL_LOOKUP[m.group(1)] if m else None
