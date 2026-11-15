from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from make_sample_pdf import build_scanned_pdf, build_text_pdf


@pytest.fixture(scope="session")
def sample_pdf(tmp_path_factory):
    path = tmp_path_factory.mktemp("samples") / "ejemplo_aprendizaje_multimedia.pdf"
    build_text_pdf(path)
    return path


@pytest.fixture(scope="session")
def scanned_pdf(tmp_path_factory, sample_pdf):
    path = tmp_path_factory.mktemp("scans") / "ejemplo_escaneado.pdf"
    build_scanned_pdf(sample_pdf, path)
    return path


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", max_upload_mb=25)


@pytest.fixture()
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def upload(client: TestClient, path_or_bytes, name: str = "documento.pdf", content_type="application/pdf"):
    data = path_or_bytes if isinstance(path_or_bytes, bytes) else path_or_bytes.read_bytes()
    return client.post("/api/documents", files={"file": (name, data, content_type)})


@pytest.fixture()
def processed(client, sample_pdf):
    """Sube y procesa el PDF de ejemplo. Devuelve (documento, id_de_proyecto)."""
    doc = upload(client, sample_pdf, "ejemplo.pdf").json()
    assert client.post(f"/api/documents/{doc['id']}/process").status_code == 202
    doc = client.get(f"/api/documents/{doc['id']}").json()
    assert doc["status"] == "processed", doc
    return doc, doc["projectId"]
