"""Algoritmo de mapa conceptual: determinismo, procedencia y validación del grafo."""
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.schemas import ConceptMap, MapEdge, MapNode
from app.services.concept_map import _definition, build_concept_map, normalize_hierarchy
from app.services.pdf_extractor import extract_document
from app.services.structure import analyze_structure
from app.services.text_utils import split_sentences


@pytest.fixture(scope="module")
def cmap(sample_pdf):
    ex = extract_document(sample_pdf, Settings())
    st = analyze_structure(ex, "respaldo")
    return build_concept_map(st, project_id="p1", document_id="d1", extraction_method=ex.method)


def labels(m, kind=None):
    return {n.label for n in m.nodes if kind is None or n.kind == kind}


def test_genera_nodos_y_relaciones_del_documento(cmap):
    assert len(cmap.nodes) >= 15 and len(cmap.edges) >= 15
    root = [n for n in cmap.nodes if n.parentId is None]
    assert [r.label for r in root] == ["Fundamentos del Aprendizaje Multimedia"]
    assert {"Introducción", "Carga cognitiva", "Principios de diseño"} <= labels(cmap, "section")
    assert {"Memoria sensorial", "Memoria de trabajo", "Carga extrínseca"} <= labels(cmap, "list_item")
    assert {"Canal visual", "Mapa conceptual", "Principio de coherencia"} <= labels(cmap, "definition")


def test_relaciones_con_conectores_explicitos(cmap):
    by_id = {n.id: n.label for n in cmap.nodes}
    triples = {(by_id[e.source], e.label, by_id[e.target]) for e in cmap.edges if e.kind == "explicit"}
    assert ("Carga extrínseca", "afecta a", "Memoria de trabajo") in triples
    assert ("Principio de coherencia", "reduce", "Carga cognitiva") in triples
    for e in cmap.edges:
        if e.kind == "explicit":
            assert e.sourceText and e.sourcePage, "toda relación explícita conserva su oración de origen"


def test_conserva_procedencia_de_cada_concepto(cmap):
    for n in cmap.nodes:
        assert n.sourceText, f"{n.label} no tiene texto de origen"
        assert n.sourcePage in (1, 2)
    defn = next(n for n in cmap.nodes if n.label == "Canal visual")
    assert "sistema de procesamiento" in defn.description
    assert "imágenes" in defn.sourceText


def test_los_terminos_repetidos_son_provisionales(cmap):
    keywords = [n for n in cmap.nodes if n.kind == "keyword"]
    assert keywords and all(k.provisional for k in keywords)
    assert any("provisionales" in w for w in cmap.warnings)


def test_es_determinista(sample_pdf):
    runs = []
    for _ in range(2):
        ex = extract_document(sample_pdf, Settings())
        st = analyze_structure(ex, "respaldo")
        runs.append(build_concept_map(st, project_id="p1", document_id="d1",
                                      extraction_method=ex.method).model_dump_json())
    assert runs[0] == runs[1]


def test_no_usa_ia_generativa():
    forbidden = re.compile(r"^\s*(?:import|from)\s+(openai|anthropic|google\.generativeai|cohere|transformers|langchain)", re.M)
    for path in (Path(__file__).parents[1] / "app").rglob("*.py"):
        assert not forbidden.search(path.read_text(encoding="utf-8")), path


@pytest.mark.parametrize("sentence,expected", [
    ("El canal visual es un sistema de procesamiento de imágenes.", ("canal visual", "es")),
    ("Se entiende por carga cognitiva, el esfuerzo mental de la memoria.", ("carga cognitiva", "se entiende como")),
    ("Un mapa conceptual consiste en una red de nodos y enlaces.", ("mapa conceptual", "consiste en")),
])
def test_detecta_definiciones_explicitas(sentence, expected):
    term, rel = _definition(sentence)
    assert (term.lower(), rel) == expected


@pytest.mark.parametrize("sentence", [
    "Esto es un problema frecuente en los materiales.",
    "Mayer (2021) afirma que las personas aprenden más.",
    "Cuando el material es un texto largo, la atención baja.",
    "Por ejemplo, un mapa es una herramienta útil.",
])
def test_no_inventa_definiciones(sentence):
    assert _definition(sentence) is None


def test_division_de_oraciones_respeta_abreviaturas():
    text = "Mayer et al. propusieron la teoría. R. E. Mayer la publicó en 2021. Funciona bien."
    assert split_sentences(text) == [
        "Mayer et al. propusieron la teoría.", "R. E. Mayer la publicó en 2021.", "Funciona bien.",
    ]


# ------------------------------------------------------------------ validación del grafo
def _node(i, parent=None, **kw):
    return MapNode(id=f"n{i}", label=f"Concepto {i}", parentId=parent, **kw)


def test_rechaza_relaciones_con_nodos_inexistentes():
    with pytest.raises(ValidationError, match="destino que no existe"):
        ConceptMap(id="m", documentId="d", title="t", nodes=[_node(1), _node(2, "n1")],
                   edges=[MapEdge(id="e1", source="n1", target="fantasma")])
    with pytest.raises(ValidationError, match="origen que no existe"):
        ConceptMap(id="m", documentId="d", title="t", nodes=[_node(1)],
                   edges=[MapEdge(id="e1", source="fantasma", target="n1")])


def test_rechaza_ids_repetidos_dos_raices_y_ciclos():
    with pytest.raises(ValidationError, match="repetidos"):
        ConceptMap(id="m", documentId="d", title="t", nodes=[_node(1), _node(1, "n1")])
    with pytest.raises(ValidationError, match="exactamente un concepto central"):
        ConceptMap(id="m", documentId="d", title="t", nodes=[_node(1), _node(2)])
    with pytest.raises(ValidationError, match="ciclo"):
        ConceptMap(id="m", documentId="d", title="t", nodes=[_node(1), _node(2, "n3"), _node(3, "n2")])
    with pytest.raises(ValidationError, match="consigo mismo"):
        ConceptMap(id="m", documentId="d", title="t", nodes=[_node(1)],
                   edges=[MapEdge(id="e1", source="n1", target="n1")])


def test_normalize_hierarchy_alinea_aristas_con_parentid():
    m = ConceptMap(
        id="m", documentId="d", title="t",
        nodes=[_node(1), _node(2, "n1"), _node(3, "n1")],
        edges=[MapEdge(id="relacion-001", source="n2", target="n3", kind="hierarchy"),   # obsoleta
               MapEdge(id="relacion-002", source="n1", target="n2", kind="hierarchy", label="incluye")],
    )
    fixed = normalize_hierarchy(m)
    pairs = {(e.source, e.target) for e in fixed.edges if e.kind == "hierarchy"}
    assert pairs == {("n1", "n2"), ("n1", "n3")}
    assert next(e for e in fixed.edges if e.target == "n2").label == "incluye"
