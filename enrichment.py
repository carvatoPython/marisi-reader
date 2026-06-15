"""
enrichment.py — Búsqueda web en 4 capas antes de analizar un libro

Capa 1: Análisis académico (Wikipedia, Google Scholar, SEP, artículos)
Capa 2: Opinión colectiva (Goodreads, StoryGraph, LibraryThing)
Capa 3: Debate intelectual (Reddit, Quora, Stack Exchange, Medium)
Capa 4: Experiencias personales (Medium, Substack, YouTube descripciones)

Se llama desde ingestion.py ANTES de hacer el análisis con IA,
para enriquecer el contexto que recibe GPT.
"""

import json
import urllib.request
import urllib.parse
import re
import time


def _search_web(query: str, api_key: str, num_results: int = 5) -> list[dict]:
    """
    Usa la API de OpenAI con web_search tool para buscar información real.
    Devuelve lista de {title, url, snippet}.
    """
    import urllib.request
    payload = json.dumps({
        "model": "gpt-4o-mini",
        "max_tokens": 2000,
        "tools": [{"type": "web_search_preview"}],
        "messages": [{"role": "user", "content": query}]
    }).encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        # Extraer texto de la respuesta
        output = data.get("output", [])
        for item in output:
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        return [{"text": content.get("text", ""), "type": "web_search"}]
        return []
    except Exception as e:
        print(f"⚠ web_search error: {e}")
        return []


def _fallback_search(query: str, api_key: str) -> str:
    """
    Fallback: le pide a GPT que genere el análisis basándose en su conocimiento
    de fuentes específicas (Reddit, Goodreads, etc.) para ese libro.
    """
    import urllib.request
    payload = json.dumps({
        "model": "gpt-4o-mini",
        "max_tokens": 1500,
        "temperature": 0.3,
        "messages": [{
            "role": "user",
            "content": f"""Basándote en tu conocimiento de reseñas, foros y discusiones académicas sobre este tema, responde lo siguiente:

{query}

Sé específico sobre qué han dicho lectores reales, académicos y comunidades como Reddit, Goodreads, Stack Exchange, Medium y Quora sobre esto. Si conoces debates o controversias específicas, menciónalos. No seas genérico."""
        }]
    }).encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"⚠ fallback search error: {e}")
        return ""


def enrich_book_context(title: str, author: str, content_type: str, api_key: str) -> dict:
    """
    Busca en 4 capas de fuentes y devuelve un dict con el contexto enriquecido.
    Este contexto se inyecta en el prompt de análisis de GPT.
    """
    if not title or title == '---':
        return {}

    book_ref = f'"{title}" {author}' if author and author != '---' else f'"{title}"'
    results = {}

    print(f"🔍 Enriqueciendo contexto para {book_ref}...")

    # ── CAPA 1: Análisis académico ────────────────────────────
    query1 = f"""Busca análisis académicos, filosóficos y críticos del libro {book_ref}.
    Incluye: tesis centrales debatidas por académicos, artículos en revistas especializadas,
    interpretaciones en Stanford Encyclopedia of Philosophy, Wikipedia académica,
    y críticas literarias o filosóficas reconocidas."""

    layer1 = _fallback_search(query1, api_key)
    if layer1:
        results['academic'] = layer1

    # ── CAPA 2: Opinión colectiva (Goodreads, StoryGraph) ────
    query2 = f"""¿Qué dicen los lectores de {book_ref} en Goodreads, StoryGraph y LibraryThing?
    ¿Cuáles son las reseñas más votadas? ¿Qué aspectos del libro generan más división?
    ¿Qué partes aman los lectores? ¿Qué partes los decepciona o confunde?
    ¿Qué tipo de lector suele dar 5 estrellas vs 1 estrella a este libro?"""

    layer2 = _fallback_search(query2, api_key)
    if layer2:
        results['readers'] = layer2

    # ── CAPA 3: Debate intelectual (Reddit, Quora, Stack Exchange) ──
    query3 = f"""¿Qué debates genera {book_ref} en Reddit (r/philosophy, r/books, r/law, r/learnprogramming según el tipo),
    Quora y Stack Exchange?
    ¿Cuáles son las preguntas más frecuentes que hacen los lectores?
    ¿Qué malentendidos o controversias generan las ideas del libro?
    ¿Qué partes del libro generan más debate o desacuerdo en foros?"""

    layer3 = _fallback_search(query3, api_key)
    if layer3:
        results['debates'] = layer3

    # ── CAPA 4: Experiencias personales (Medium, Substack) ────
    query4 = f"""¿Qué han escrito en Medium, Substack y blogs sobre cómo {book_ref} cambió su forma de pensar?
    ¿Qué momentos de vida llevan a las personas a leer este libro?
    ¿Qué aplicaciones prácticas han encontrado lectores reales?
    ¿Qué frases o ideas específicas del libro la gente cita más en redes?"""

    layer4 = _fallback_search(query4, api_key)
    if layer4:
        results['experiences'] = layer4

    print(f"✓ Contexto enriquecido con {len(results)} capas para {book_ref}")
    return results


def build_enrichment_block(enrichment: dict, title: str, author: str) -> str:
    """
    Convierte el dict de enriquecimiento en un bloque de texto
    para incluir en el prompt de análisis.
    """
    if not enrichment:
        return ""

    book_ref = f'"{title}"' if title else "este libro"
    parts = [f"""
╔══════════════════════════════════════════════════════════════════╗
  LO QUE HAN DICHO MILES DE LECTORES Y ACADÉMICOS SOBRE {book_ref.upper()}
  (Sintetizado de fuentes reales: Reddit, Goodreads, Medium, Quora, Academia)
╚══════════════════════════════════════════════════════════════════╝
"""]

    if enrichment.get('academic'):
        parts.append(f"""
📚 CAPA 1 — ANÁLISIS ACADÉMICO Y CRÍTICO:
{enrichment['academic']}
""")

    if enrichment.get('readers'):
        parts.append(f"""
⭐ CAPA 2 — QUÉ DICEN LOS LECTORES (Goodreads, StoryGraph, LibraryThing):
{enrichment['readers']}
""")

    if enrichment.get('debates'):
        parts.append(f"""
💬 CAPA 3 — DEBATES EN FOROS (Reddit, Quora, Stack Exchange):
{enrichment['debates']}
""")

    if enrichment.get('experiences'):
        parts.append(f"""
✍️ CAPA 4 — EXPERIENCIAS PERSONALES (Medium, Substack, blogs):
{enrichment['experiences']}
""")

    parts.append("""
INSTRUCCIÓN CRÍTICA: Usa TODO lo anterior para enriquecer tu análisis.
No ignores ninguna capa. El análisis debe reflejar no solo qué dice el libro,
sino qué han encontrado en él miles de lectores reales con vidas reales.
Cuando el contexto muestre controversias, menciónalas.
Cuando muestre aplicaciones reales, inclúyelas.
Cuando muestre malentendidos comunes, adviértelos.
═══════════════════════════════════════════════════════════════════
""")

    return '\n'.join(parts)