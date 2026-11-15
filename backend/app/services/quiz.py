"""Generación determinista de cuestionarios de opción múltiple («completar la oración»).

Misma filosofía que el mapa conceptual: reglas sobre el texto extraído, sin IA generativa y sin inventar
contenido. Cada pregunta es una oración REAL del documento con un término oculto.

Flujo
  1. Oraciones clave: se buscan oraciones declarativas con
       * definición explícita («X es un…», «X se define como…», «X consiste en…», «X se denomina…»),
       * formato «Término: explicación» (muy común en listas),
       * relación explícita entre dos entidades del documento («A afecta a B», «A reduce B»…).
  2. Pregunta: se oculta el término principal (en definiciones y «Término: …») o la entidad objeto de la
     relación, y se reemplaza por «______». Esa respuesta es la correcta.
  3. Distractores: otras entidades del MISMO documento (conceptos del mapa y frases nominales frecuentes),
     elegidas con longitud parecida a la respuesta y sin aparecer en la propia oración.
  4. Las opciones se mezclan con una semilla derivada del contenido del documento: parecen aleatorias, pero
     el mismo documento produce siempre el mismo cuestionario.
"""
from __future__ import annotations

import hashlib
import random
import re
from collections import Counter
from dataclasses import dataclass

from ..schemas import ConceptMap, QuizQuestion
from .concept_map import (
    colon_term, contains_words, find_definition, match_relation_connector, ngram_candidates,
)
from .text_utils import STOPWORDS, capitalize_first, collapse, normalize, split_sentences

BLANK = "______"
MIN_WORDS, MAX_WORDS, MAX_CHARS = 8, 40, 300
MIN_CONTEXT_WORDS = 5          # palabras que deben quedar visibles además del espacio en blanco
N_DISTRACTORS = 3
MAX_POOL_NGRAMS = 40
_PRIORITY = {"definicion": 0, "termino": 1, "relacion": 2}
MIN_POOL = 12                  # con menos entidades se amplía el conjunto (palabras clave y frases frecuentes)
MAX_COLON_WORDS = 30
_STOP_NORM = frozenset(normalize(w) for w in STOPWORDS)
# Títulos «estructurales»: no son conceptos del tema y serían malos distractores
_STRUCTURAL = frozenset(normalize(x) for x in (
    "introducción conclusiones conclusión resumen objetivos referencias bibliografía índice antecedentes "
    "metodología resultados justificación anexos presentación agradecimientos"
).split())


@dataclass(frozen=True)
class _Entity:
    norm: str
    text: str


@dataclass
class _Candidate:
    tipo: str
    sentence: str          # oración completa original
    question: str          # oración con el espacio en blanco
    answer: str
    page: int | None
    section: str | None
    order: int


# --------------------------------------------------------------------------- entidades (respuestas y distractores)
def _entity_pool(blocks: list[dict], cmap: ConceptMap) -> list[_Entity]:
    """Entidades del documento. Primero conceptos confiables (definiciones, listas, secciones); solo si son
    pocas se amplía con palabras clave y frases nominales frecuentes."""
    pool: dict[str, _Entity] = {}

    def add(raw: str) -> None:
        text = collapse(raw).strip(" .:;,")
        norm = normalize(text)
        if (len(text) < 4 or len(text) > 60 or len(text.split()) > 6 or text.endswith("…")
                or any(ch.isdigit() for ch in text)           # «Actividad 1», «Figura 2»…: enumeraciones
                or norm in pool or norm in _STRUCTURAL or not any(ch.isalpha() for ch in text)):
            return
        pool[norm] = _Entity(norm, text)

    for kinds in (("definition", "list_item", "section", "manual"), ("keyword",)):
        if len(pool) >= MIN_POOL:
            break
        for node in cmap.nodes:
            if node.kind in kinds:
                add(node.label)

    if len(pool) < MIN_POOL:
        freq: Counter[str] = Counter()
        support: Counter[str] = Counter()
        for block in blocks:
            for sentence in split_sentences(block["text"]):
                for term, nominal in ngram_candidates(sentence):
                    freq[term] += 1
                    support[term] += nominal
        ranked = sorted(
            (t for t, f in freq.items()
             if (" " in t and f >= 2 and support[t] >= 1) or (" " not in t and f >= 3 and support[t] >= 2)),
            key=lambda t: (-freq[t], t),
        )
        for term in ranked[:MAX_POOL_NGRAMS]:
            add(term)
    return list(pool.values())


# --------------------------------------------------------------------------- oraciones clave
def _usable(sentence: str) -> bool:
    words = sentence.split()
    if not (MIN_WORDS <= len(words) <= MAX_WORDS) or len(sentence) > MAX_CHARS:
        return False
    if not sentence.endswith(".") or sentence.startswith("¿") or "http" in sentence.lower():
        return False
    if not (sentence[0].isupper() or sentence[0].isdigit()):
        return False
    digits = sum(c.isdigit() for c in sentence)
    return digits <= 0.1 * max(1, sum(c.isalpha() for c in sentence))


def _count(sentence: str, answer: str) -> int:
    return len(re.findall(rf"(?<!\w){re.escape(normalize(answer))}(?!\w)", normalize(sentence)))


def _visible_words(question: str) -> int:
    return len(question.replace(BLANK, " ").split())


def _is_complete_phrase(norm: str, start: int, end: int) -> bool:
    """El término no debe ser parte de un sintagma mayor («aprendizaje» dentro de «aprendizaje significativo»):
    la palabra vecina inmediata, si existe, debe ser una palabra vacía (artículo, preposición…)."""
    before = re.search(r"([a-zñ0-9]+)\s*$", norm[:start])
    after = re.match(r"\s*([a-zñ0-9]+)", norm[end:])
    return all(m is None or m.group(1) in _STOP_NORM for m in (before, after))


def _relation_target(sentence: str, entities: list[_Entity]) -> tuple[int, int] | None:
    """Posición de la entidad objeto en «A <conector> B» (solo si el conector es explícito)."""
    norm = normalize(sentence)
    if len(norm) != len(sentence):                      # la normalización cambió longitudes: no es seguro
        return None
    claimed: list[tuple[int, int, str]] = []
    for ent in entities:                                # ya ordenadas de la más larga a la más corta
        if ent.norm not in norm:
            continue
        for m in re.finditer(rf"(?<!\w){re.escape(ent.norm)}(?!\w)", norm):
            if not any(m.start() < e and m.end() > s for s, e, _ in claimed):
                claimed.append((m.start(), m.end(), ent.norm))
    claimed.sort()
    for (_, end_a, a), (start_b, end_b, b) in zip(claimed, claimed[1:]):
        if (a != b and match_relation_connector(norm[end_a:start_b].strip())
                and _is_complete_phrase(norm, start_b, end_b)):
            return start_b, end_b
    return None


def _candidates(blocks: list[dict], pool: list[_Entity]) -> list[_Candidate]:
    entities = sorted(pool, key=lambda e: (-len(e.norm), e.norm))
    out: list[_Candidate] = []

    def push(tipo: str, sentence: str, question: str, answer: str, block: dict) -> None:
        if (_count(sentence, answer) == 1 and _visible_words(question) >= MIN_CONTEXT_WORDS
                and 4 <= len(answer) <= 60 and len(answer.split()) <= 6):
            out.append(_Candidate(tipo, sentence, question, answer, block.get("page"), block.get("section"), len(out)))

    for block in blocks:
        text = collapse(block["text"])
        colon = colon_term(text, 6 if block["kind"] == "list_item" else 4)
        if colon:
            term, rest = colon
            sentence = text if text.endswith(".") else text + "."
            if (MIN_CONTEXT_WORDS <= len(rest.split()) <= MAX_COLON_WORDS and ";" not in rest
                    and len(split_sentences(rest)) == 1 and _count(rest, term) == 0):
                push("termino", sentence, f"{BLANK}: {rest.rstrip('.')}.", term, block)
                continue
        for sentence in split_sentences(text):
            if not _usable(sentence):
                continue
            found = find_definition(sentence)
            if found:
                _, _, start, end = found
                push("definicion", sentence, sentence[:start] + BLANK + sentence[end:], sentence[start:end], block)
                continue
            target = _relation_target(sentence, entities)
            if target:
                start, end = target
                push("relacion", sentence, sentence[:start] + BLANK + sentence[end:], sentence[start:end], block)
    return out


def _select(candidates: list[_Candidate], limit: int) -> list[_Candidate]:
    """Una pregunta por respuesta; se prefieren definiciones, luego «término: …» y luego relaciones.
    El resultado se presenta en el orden del documento."""
    best: dict[str, _Candidate] = {}
    for c in sorted(candidates, key=lambda c: (_PRIORITY[c.tipo], c.order)):
        best.setdefault(normalize(c.answer), c)
    ranked = sorted(best.values(), key=lambda c: (_PRIORITY[c.tipo], c.order))[:limit]
    return sorted(ranked, key=lambda c: c.order)


# --------------------------------------------------------------------------- distractores y ensamblado
def _stable(seed: str, *parts: str) -> str:
    return hashlib.sha1(":".join((seed, *parts)).encode("utf-8")).hexdigest()


def _stem(norm: str) -> str:
    """Raíz tosca para tratar singular/plural como lo mismo («formato»/«formatos», «conceptual»/«conceptuales»)."""
    words = []
    for w in norm.split():
        if len(w) > 5 and w.endswith("es"):
            w = w[:-2]
        elif len(w) > 3 and w.endswith("s"):
            w = w[:-1]
        words.append(w)
    return " ".join(words)


def _related(a: str, b: str) -> bool:
    a, b = _stem(a), _stem(b)
    return contains_words(a, b) or contains_words(b, a)


def _pick_distractors(c: _Candidate, pool: list[_Entity], usage: Counter[str], seed: str) -> list[_Entity]:
    answer_norm, sentence_norm = normalize(c.answer), normalize(c.sentence)
    words = len(c.answer.split())
    valid = [
        e for e in pool
        if not _related(answer_norm, e.norm) and not contains_words(_stem(sentence_norm), _stem(e.norm))
    ]
    valid.sort(key=lambda e: (abs(len(e.text.split()) - words), usage[e.norm], _stable(seed, answer_norm, e.norm)))
    chosen: list[_Entity] = []
    for e in valid:
        if all(not _related(e.norm, other.norm) for other in chosen):
            chosen.append(e)
        if len(chosen) == N_DISTRACTORS:
            break
    return chosen


def build_quiz(blocks: list[dict], cmap: ConceptMap, max_questions: int = 10) -> list[QuizQuestion]:
    seed = _stable("edumap-quiz", "\n".join(b["text"] for b in blocks))[:16]
    pool = _entity_pool(blocks, cmap)
    chosen = _select(_candidates(blocks, pool), max_questions)

    usage: Counter[str] = Counter()
    questions: list[QuizQuestion] = []
    for c in chosen:
        distractors = _pick_distractors(c, pool, usage, seed)
        if len(distractors) < N_DISTRACTORS:
            continue                                    # sin distractores razonables no se genera la pregunta
        for d in distractors:
            usage[d.norm] += 1
        # Todas las opciones se muestran con la misma capitalización para que no delate la correcta
        correct = capitalize_first(c.answer)
        options = sorted([correct] + [capitalize_first(d.text) for d in distractors], key=normalize)
        random.Random(_stable(seed, normalize(c.answer))).shuffle(options)
        questions.append(QuizQuestion(
            id=f"pregunta-{len(questions) + 1:03d}", pregunta=c.question, opciones=options,
            respuestaCorrecta=correct, tipo=c.tipo, seccion=c.section, paginaOrigen=c.page,
            oracionOriginal=c.sentence,
        ))
    return questions
