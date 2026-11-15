"""API REST: carga, validaciones, procesamiento, guardado, restablecer y eliminar."""
import pymupdf
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

from conftest import upload


def test_flujo_completo_pdf_a_mapa_guardado_y_reapertura(client, processed):
    doc, project_id = processed
    assert [s["state"] for s in doc["stages"]] == ["done"] * 5
    assert doc["extractionMethod"] == "text"

    projects = client.get("/api/projects").json()
    assert [p["id"] for p in projects] == [project_id]
    assert projects[0]["documentName"] == "ejemplo.pdf" and projects[0]["resourceType"] == "mapa_conceptual"

    cmap = client.get(f"/api/projects/{project_id}/map").json()
    assert cmap["title"] == "Fundamentos del Aprendizaje Multimedia"
    assert len(cmap["nodes"]) >= 15 and cmap["documentId"] == doc["id"]

    # Edición: renombrar un nodo, agregar un concepto hijo y una relación transversal
    root = next(n for n in cmap["nodes"] if n["parentId"] is None)
    first = next(n for n in cmap["nodes"] if n["kind"] == "list_item")
    first["label"] = "Memoria sensorial (editado)"
    cmap["nodes"].append({"id": "concepto-900", "label": "Concepto manual", "description": "", "sourceText": "",
                          "parentId": root["id"], "kind": "manual", "provisional": False})
    cmap["edges"].append({"id": "relacion-900", "source": "concepto-900", "target": first["id"],
                          "label": "se vincula con", "kind": "manual"})
    saved = client.put(f"/api/projects/{project_id}/map", json=cmap)
    assert saved.status_code == 200
    # normalize_hierarchy agrega la arista jerárquica faltante del concepto manual
    assert any(e["target"] == "concepto-900" and e["kind"] == "hierarchy" for e in saved.json()["edges"])

    # "Volver a abrirlo": los cambios persisten
    again = client.get(f"/api/projects/{project_id}/map").json()
    assert any(n["label"] == "Memoria sensorial (editado)" for n in again["nodes"])
    assert any(e["id"] == "relacion-900" and e["label"] == "se vincula con" for e in again["edges"])
    assert client.get("/api/projects").json()[0]["edited"] is True

    # Restablecer devuelve el mapa generado originalmente
    reset = client.post(f"/api/projects/{project_id}/map/reset").json()
    assert not any(n["id"] == "concepto-900" for n in reset["nodes"])
    assert any(n["label"] == "Memoria sensorial" for n in reset["nodes"])
    assert client.get("/api/projects").json()[0]["edited"] is False


def test_rechaza_guardar_mapa_invalido(client, processed):
    _, project_id = processed
    cmap = client.get(f"/api/projects/{project_id}/map").json()
    cmap["edges"].append({"id": "relacion-999", "source": cmap["nodes"][0]["id"], "target": "no-existe",
                          "label": "x", "kind": "manual"})
    r = client.put(f"/api/projects/{project_id}/map", json=cmap)
    assert r.status_code == 422 and "no existe" in r.text
    # el mapa guardado no cambió
    ok = client.get(f"/api/projects/{project_id}/map").json()
    assert all(e["id"] != "relacion-999" for e in ok["edges"])


def test_el_cliente_no_puede_cambiar_la_identidad_del_mapa(client, processed):
    doc, project_id = processed
    cmap = client.get(f"/api/projects/{project_id}/map").json()
    cmap["id"], cmap["documentId"] = "otro", "otro-documento"
    saved = client.put(f"/api/projects/{project_id}/map", json=cmap).json()
    assert saved["id"] == project_id and saved["documentId"] == doc["id"]


def test_eliminar_proyecto_borra_pdf_y_registros(client, processed, settings):
    doc, project_id = processed
    stored = list(settings.upload_dir.glob("documento-*.pdf"))
    assert len(stored) == 1
    assert client.delete(f"/api/projects/{project_id}").status_code == 204
    assert client.get(f"/api/projects/{project_id}/map").status_code == 404
    assert client.get(f"/api/documents/{doc['id']}").status_code == 404
    assert client.get("/api/projects").json() == []
    assert not list(settings.upload_dir.glob("documento-*.pdf"))


def test_no_se_procesa_dos_veces(client, processed):
    doc, _ = processed
    assert client.post(f"/api/documents/{doc['id']}/process").status_code == 409


def test_rechaza_archivos_que_no_son_pdf(client):
    assert upload(client, b"hola", "notas.txt", "text/plain").status_code == 415
    fake = upload(client, b"esto es texto plano disfrazado", "falso.pdf")
    assert fake.status_code == 415 and "PDF válido" in fake.json()["detail"]
    assert upload(client, b"", "vacio.pdf").status_code == 422
    corrupt = upload(client, b"%PDF-1.7\nbasura sin estructura", "roto.pdf")
    assert corrupt.status_code == 422 and "dañado" in corrupt.json()["detail"]


def test_rechaza_archivos_demasiado_grandes(tmp_path):
    small_limit = Settings(data_dir=tmp_path / "limite", max_upload_mb=1)
    with TestClient(create_app(small_limit)) as c:
        big = b"%PDF-1.4\n" + b"0" * (2 * 1024 * 1024)
        r = upload(c, big, "grande.pdf")
        assert r.status_code == 413 and "1 MB" in r.json()["detail"]
        assert not any(small_limit.upload_dir.iterdir())     # no quedan archivos parciales


def test_rechaza_pdf_cifrado(client, tmp_path):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "texto " * 30)
    path = tmp_path / "c.pdf"
    doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="x")
    r = upload(client, path)
    assert r.status_code == 422 and "contraseña" in r.json()["detail"]


def test_no_usa_rutas_del_usuario_y_no_deja_basura(client, sample_pdf, settings):
    r = upload(client, sample_pdf, "../../etc/passwd.pdf").json()
    assert r["originalName"] == "passwd.pdf"
    files = [p.name for p in settings.upload_dir.iterdir()]
    assert files == [f"{r['id']}.pdf"]                      # nombre interno generado; sin temporales
    assert not (settings.data_dir.parent / "etc").exists()


def test_pdf_escaneado_sin_ocr_falla_con_mensaje_claro(client, scanned_pdf, monkeypatch):
    from app.services import pdf_extractor
    monkeypatch.setattr(pdf_extractor, "ocr_available", lambda settings: False)
    doc = upload(client, scanned_pdf, "scan.pdf").json()
    client.post(f"/api/documents/{doc['id']}/process")
    doc = client.get(f"/api/documents/{doc['id']}").json()
    assert doc["status"] == "failed" and "Tesseract" in doc["message"]
    assert next(s for s in doc["stages"] if s["key"] == "extraccion")["state"] == "error"
    assert client.get("/api/projects").json() == []


def test_texto_revisado_a_mano_permite_procesar(client, sample_pdf):
    doc = upload(client, sample_pdf, "revisar.pdf").json()
    text = (
        "[[Página 1]]\n\nTeoría de la memoria\n\n"
        "La memoria de trabajo es un sistema de capacidad limitada que mantiene información breve. "
        "La memoria a largo plazo se define como un almacén de conocimientos previos casi ilimitado. "
        "Ambos sistemas participan cuando el estudiante lee un texto con imágenes y palabras.\n\n"
        "Aplicaciones\n\nEl diseño de materiales debe respetar la capacidad limitada de la memoria de trabajo "
        "para que el estudiante pueda comprender cada explicación sin sobrecarga.\n"
    )
    assert client.put(f"/api/documents/{doc['id']}/text", json={"text": text}).status_code == 200
    assert client.put(f"/api/documents/{doc['id']}/text", json={"text": "  "}).status_code == 422
    client.post(f"/api/documents/{doc['id']}/process")
    done = client.get(f"/api/documents/{doc['id']}").json()
    assert done["status"] == "processed" and done["extractionMethod"] == "manual"
    cmap = client.get(f"/api/projects/{done['projectId']}/map").json()
    labels = {n["label"] for n in cmap["nodes"]}
    assert {"Teoría de la memoria", "Aplicaciones", "Memoria de trabajo"} <= labels


def test_recursos_inexistentes(client):
    assert client.get("/api/documents/no-existe").status_code == 404
    assert client.post("/api/documents/no-existe/process").status_code == 404
    assert client.get("/api/projects/no-existe/map").status_code == 404
    assert client.delete("/api/projects/no-existe").status_code == 404


def test_health_informa_limites_y_ocr(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["maxUploadMb"] == 25 and isinstance(h["ocr"], bool)
