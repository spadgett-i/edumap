"""Utilidades de texto deterministas: normalización, oraciones, tokens y palabras vacías."""
from __future__ import annotations

import re
import unicodedata

LETTERS = "A-Za-zÁÉÍÓÚÜÑáéíóúüñ"
WORD_RE = re.compile(rf"[{LETTERS}]+|[^\s{LETTERS}]+")

STOPWORDS = frozenset(
    """
    a al algo algunas algunos ante antes aquel aquella aquello aquellos aquí asi así aun aún aunque
    cada casi como cómo con contra cual cuales cuando cuándo cuyo de del desde donde dónde dos durante
    e el él ella ellas ello ellos en entre era eran es esa esas ese eso esos esta está están estar estas
    este esto estos fue fueron ha había han hasta hay la las le les lo los mas más me mi mientras muy
    ni no nos nosotros nuestra nuestro o os otra otras otro otros para pero poco por porque pues que qué
    quien quién se sea sean según ser si sí sido siempre sin sobre solo sólo son su sus también tan tanto
    te tiene tienen todo todos tras tu tus un una uno unas unos usted va vamos van vez y ya yo
    puede pueden puedan permite permiten debe deben debería sería serán será ser tener tiene hacer hace
    cómo así además entonces luego incluso mediante través forma manera parte partes tipo tipos caso casos
    primer primera primero segundo segunda tercer tercera cuatro cinco seis siete ocho nueve diez
    the of and to in is are for on with as by an be this that or from at it its
    """.split()
)
ARTICLES = frozenset("el la los las un una unos unas lo".split())
# Palabras que delatan que el "término" es en realidad una cláusula, no un concepto
CLAUSE_WORDS = frozenset("que cuando donde porque si mientras pero aunque también además como".split())

_BOUNDARY = re.compile(r'(?<=[.!?…])(["”»)]?)\s+(?=["“«¿¡(]?[A-ZÁÉÍÓÚÑ0-9])')
_JOIN_PREV = re.compile(
    r"(?:\b(?:vs|dr|dra|sr|sra|ing|lic|núm|pp|fig|cap|ej|aprox|art)\.|\bet al\.|\b[A-ZÁÉÍÓÚÑ]\.|^\d+[.)])$",
    re.IGNORECASE,
)
_NUM_PREFIX = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.)]?|[IVXLC]+[.)]|[A-Za-z][.)])\s+")
_BULLET_PREFIX = re.compile(r"^\s*(?:[•●▪◦‣∙·*]|[-–—])\s*")


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize(text: str) -> str:
    """Minúsculas, sin acentos y con espacios colapsados: sirve para comparar etiquetas."""
    return collapse(strip_accents(text).lower())


def split_sentences(text: str) -> list[str]:
    text = collapse(text)
    if not text:
        return []
    pieces: list[str] = []
    last = 0
    for m in _BOUNDARY.finditer(text):
        pieces.append(text[last : m.end(1)])
        last = m.end()
    pieces.append(text[last:])
    merged: list[str] = []
    for piece in (p.strip() for p in pieces):
        if not piece:
            continue
        if merged and _JOIN_PREV.search(merged[-1]):
            merged[-1] = f"{merged[-1]} {piece}"
        else:
            merged.append(piece)
    return merged


def strip_numbering(text: str) -> str:
    return _NUM_PREFIX.sub("", text, count=1)


def strip_bullet(text: str) -> str:
    return _BULLET_PREFIX.sub("", text, count=1)


def truncate(text: str, max_len: int) -> str:
    text = collapse(text)
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0].rstrip(",;:- ")
    return (cut or text[:max_len]) + "…"


def clean_label(text: str, max_len: int = 90) -> str:
    text = strip_bullet(strip_numbering(collapse(text))).strip(" \t:;,-–—")
    text = text.rstrip(".")
    return truncate(text, max_len)


def capitalize_first(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def tokens_with_breaks(sentence: str) -> list[str | None]:
    """Palabras en minúscula; None marca una interrupción (puntuación, número)."""
    out: list[str | None] = []
    for m in WORD_RE.finditer(sentence):
        chunk = m.group(0)
        out.append(chunk.lower() if chunk[0].isalpha() else None)
    return out
