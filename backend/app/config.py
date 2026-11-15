"""Configuración del backend. Se construye una sola vez al arrancar (y se puede inyectar en pruebas)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path = BASE_DIR / ".env") -> None:
    """Carga backend/.env si existe (KEY=valor). Las variables ya definidas en el sistema tienen prioridad."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    data_dir: Path = BASE_DIR / "data"
    max_upload_mb: int = 25
    max_pages: int = 300
    max_ocr_pages: int = 40
    ocr_languages: tuple[str, ...] = ("spa", "eng")
    ocr_dpi: int = 300
    tesseract_cmd: str | None = None
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    frontend_dist: Path | None = None

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "edumap.db"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        dist = BASE_DIR.parent / "frontend" / "dist"
        langs = tuple(x for x in os.environ.get("EDUMAP_OCR_LANGS", "spa+eng").split("+") if x)
        origins = tuple(
            x.strip()
            for x in os.environ.get(
                "EDUMAP_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
            if x.strip()
        )
        return cls(
            data_dir=Path(os.environ.get("EDUMAP_DATA_DIR", BASE_DIR / "data")).resolve(),
            max_upload_mb=_int_env("EDUMAP_MAX_UPLOAD_MB", 25),
            max_pages=_int_env("EDUMAP_MAX_PAGES", 300),
            max_ocr_pages=_int_env("EDUMAP_MAX_OCR_PAGES", 40),
            ocr_languages=langs or ("spa", "eng"),
            tesseract_cmd=os.environ.get("EDUMAP_TESSERACT_CMD") or None,
            cors_origins=origins,
            frontend_dist=dist if dist.is_dir() else None,
        )
