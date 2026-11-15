"""Cuestionarios: generación determinista, calidad de las preguntas y endpoint."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import Database
from app.main import create_app
from app.schemas import ConceptMap, MapNode
from app.services.concept_map import build_concept_map
from app.services.pdf_extractor import extract_document
from app.services.quiz import BLANK, build_quiz
from app.services.structure import analyze_structure, flatten_blocks
from app.services.text_utils import normalize
from conftest import upload


def _build(pdf, project_id="p1"):
    ex = extract_document(pdf, Settings())
    st = analyze_structure(ex, "respaldo")
    cmap = build_concept_map(st, project_id=project_id, document_id="d1", extraction_method=ex.method)
    return flatten_blocks(st), cmap


@pytest.fixture(scope="module")
def source(sample_pdf):
    return _build(sample_pdf)


@pytest.fixture(scope="module")
def quiz(source):
    return build_quiz(*source, max_questions=10)


def test_estructura_de_cada_pregunta(quiz):
    assert len(quiz) >= 8
    assert [q.id for q in quiz] == [f"pregunta-{i:03d}" for i in range(1, len(quiz) + 1)]
    for q in quiz:
        assert q.pregunta.count(BLANK) == 1
        assert len(q.opciones) == 4 and len(set(q.opciones)) == 4
        assert q.respuestaCorrecta in q.opciones
        assert q.tipo in ("definicion", "termino", "relacion")
        assert q.paginaOrigen in (1, 2) and q.oracionOriginal


def test_la_pregunta_es_una_oracion_real_del_documento(quiz):
    for q in quiz:
        completed = q.pregunta.replace(BLANK, q.respuestaCorrecta)
        assert normalize(completed).rstrip(".") == normalize(q.oracionOriginal).rstrip("."), q.pregunta


def test_la_respuesta_no_se_filtra_en_la_pregunta(quiz):
    for q in quiz:
        assert normalize(q.respuestaCorrecta) not in normalize(q.pregunta)


def test_los_distractores_son_entidades_del_mismo_documento(source, quiz):
    _, cmap = source
    known = {normalize(n.label) for n in cmap.nodes}
    for q in quiz:
        for option in q.opciones:
            assert normalize(option) in known, f"«{option}» no es una entidad del documento"


def test_opciones_con_la_misma_capitalizacion_y_correcta_en_posiciones_distintas(quiz):
    assert all(o[0].isupper() for q in quiz for o in q.opciones)
    positions = {q.opciones.index(q.respuestaCorrecta) for q in quiz}
    assert len(positions) >= 2, "las opciones deben estar mezcladas"


def test_es_determinista_aunque_cambien_los_ids(sample_pdf):
    a = build_quiz(*_build(sample_pdf, "proyecto-aaa"), max_questions=10)
    b = build_quiz(*_build(sample_pdf, "proyecto-bbb"), max_questions=10)
    assert [q.model_dump() for q in a] == [q.model_dump() for q in b]


def test_respeta_el_maximo_y_prioriza_definiciones(source):
    few = build_quiz(*source, max_questions=3)
    assert len(few) == 3 and all(q.tipo == "definicion" for q in few)


def _cmap(labels):
    nodes = [MapNode(id="c0", label="Documento", kind="root", parentId=None)]
    nodes += [MapNode(id=f"c{i}", label=l, kind="definition", parentId="c0") for i, l in enumerate(labels, 1)]
    return ConceptMap(id="p", documentId="d", title="Documento", nodes=nodes)


ENTITIES = ["Carga cognitiva", "Memoria de trabajo", "Canal visual", "Canal auditivo", "Mapa conceptual",
            "Principio de coherencia", "Carga extrínseca", "Memoria sensorial", "Señalización", "Contigüidad espacial",
            "Aprendizaje", "Teoría multimedia"]


def test_pregunta_de_relacion_oculta_la_entidad_objeto():
    blocks = [{"kind": "paragraph", "page": 3, "section": "Diseño",
               "text": "El principio de coherencia reduce la carga cognitiva en todo el material del curso."}]
    qs = build_quiz(blocks, _cmap(ENTITIES))
    assert len(qs) == 1 and qs[0].tipo == "relacion"
    assert qs[0].respuestaCorrecta == "Carga cognitiva"
    assert qs[0].pregunta == f"El principio de coherencia reduce la {BLANK} en todo el material del curso."
    assert qs[0].paginaOrigen == 3 and qs[0].seccion == "Diseño"


def test_no_oculta_fragmentos_de_un_termino_mas_largo():
    blocks = [{"kind": "paragraph", "page": 1, "section": None,
               "text": "El mapa conceptual facilita el aprendizaje significativo del contenido completo."}]
    assert build_quiz(blocks, _cmap(ENTITIES)) == []        # «aprendizaje» es parte de «aprendizaje significativo»


def test_sin_distractores_suficientes_no_inventa_preguntas():
    blocks = [{"kind": "paragraph", "page": 1, "section": None,
               "text": "El canal visual es un sistema de procesamiento que recibe imágenes e ilustraciones."}]
    assert build_quiz(blocks, _cmap(["Canal visual", "Canal auditivo"])) == []


def test_no_toma_como_definicion_oraciones_ambiguas():
    blocks = [{"kind": "paragraph", "page": 1, "section": None,
               "text": "Esto es un problema frecuente en los materiales didácticos de nivel superior."}]
    assert build_quiz(blocks, _cmap(ENTITIES)) == []


# ------------------------------------------------------------------ API
def test_endpoint_devuelve_arreglo_de_preguntas(client, processed):
    _, project_id = processed
    r = client.post(f"/api/projects/{project_id}/quiz")
    assert r.status_code == 200
    questions = r.json()
    assert isinstance(questions, list) and len(questions) >= 8
    assert set(questions[0]) >= {"id", "pregunta", "opciones", "respuestaCorrecta"}
    assert client.post(f"/api/projects/{project_id}/quiz").json() == questions      # determinista


def test_endpoint_respeta_maxpreguntas_y_valida(client, processed):
    _, project_id = processed
    assert len(client.post(f"/api/projects/{project_id}/quiz", json={"maxPreguntas": 4}).json()) == 4
    assert client.post(f"/api/projects/{project_id}/quiz", json={"maxPreguntas": 0}).status_code == 422
    assert client.post(f"/api/projects/{project_id}/quiz", json={"maxPreguntas": 99}).status_code == 422


def test_endpoint_404_si_el_proyecto_no_existe(client):
    assert client.post("/api/projects/no-existe/quiz").status_code == 404


def test_documento_sin_oraciones_aptas_devuelve_lista_vacia(client, sample_pdf):
    doc = upload(client, sample_pdf, "vacio.pdf").json()
    text = ("Titulo del texto\n\nEstas palabras sueltas forman un párrafo largo sin ninguna definición clara ni "
            "relación explícita entre conceptos concretos del tema tratado aquí hoy mismo. Después aparecen otras palabras "
            "igualmente sueltas que tampoco forman ninguna oración útil para construir preguntas con espacios en blanco.\n")
    client.put(f"/api/documents/{doc['id']}/text", json={"text": text})
    client.post(f"/api/documents/{doc['id']}/process")
    project_id = client.get(f"/api/documents/{doc['id']}").json()["projectId"]
    r = client.post(f"/api/projects/{project_id}/quiz")
    assert r.status_code == 200 and r.json() == []


def test_reconstruye_los_bloques_de_proyectos_anteriores_al_modulo(client, processed):
    doc, project_id = processed
    db = client.app.state.db
    db.update_document(doc["id"], blocks_json=None)                   # como un proyecto creado antes del quiz
    assert db.get_document(doc["id"])["blocks_json"] is None
    assert len(client.post(f"/api/projects/{project_id}/quiz").json()) >= 8
    assert db.get_document(doc["id"])["blocks_json"] is not None      # quedó guardado para la próxima vez


def test_migra_bases_de_datos_antiguas(tmp_path):
    path = tmp_path / "vieja.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""CREATE TABLE documents (id TEXT PRIMARY KEY, original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL, size_bytes INTEGER NOT NULL, page_count INTEGER NOT NULL, status TEXT NOT NULL,
            extraction_method TEXT, stages TEXT NOT NULL, message TEXT, extracted_text TEXT, text_override TEXT,
            project_id TEXT, created_at TEXT NOT NULL);""")
    Database(path).init()
    with sqlite3.connect(path) as conn:
        assert "blocks_json" in {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
