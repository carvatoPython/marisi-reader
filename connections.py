"""
connections.py — Nivel 5: Conexión entre libros

Detects when a newly ingested book shares concepts, contradicts, or
extends ideas already in the user's library. Called after a book is
inserted so it doesn't block the upload response.

Usage (from app.py after db.commit() on upload):
    from connections import build_connections
    build_connections(db, user_id, new_book_id, api_key)
"""

import json
from database import get_db


# ── helpers ──────────────────────────────────────────────────────────────

def _concepts_str(book_row: dict) -> str:
    """Return a compact text representation of a book's key ideas."""
    parts = [
        f"Título: {book_row.get('title', '')}",
        f"Autor: {book_row.get('author', '')}",
        f"Rama: {book_row.get('branch', '')}",
        f"Resumen: {(book_row.get('summary') or '')[:400]}",
    ]
    for field in ('key_concepts', 'norms', 'jurisprudence', 'tools_frameworks'):
        raw = book_row.get(field)
        if raw:
            try:
                items = json.loads(raw) if isinstance(raw, str) else raw
                parts.append(f"{field}: {', '.join(str(i) for i in items[:10])}")
            except Exception:
                pass
    return '\n'.join(parts)


def _call_openai(api_key: str, prompt: str, max_tokens: int = 800) -> str:
    import urllib.request
    payload = json.dumps({
        "model": "gpt-4o-mini",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"].strip()


# ── main public function ──────────────────────────────────────────────────

def build_connections(db, user_id: int, new_book_id: int, api_key: str) -> None:
    """
    Compare *new_book_id* against all other books of *user_id* and
    write rows into *book_connections* for every meaningful relationship
    found.
    """
    new_book = db.execute(
        'SELECT * FROM books WHERE id=? AND user_id=?', (new_book_id, user_id)
    ).fetchone()
    if not new_book:
        return

    others = db.execute(
        'SELECT * FROM books WHERE user_id=? AND id!=?', (user_id, new_book_id)
    ).fetchall()
    if not others:
        return  # nothing to compare against yet

    new_text = _concepts_str(dict(new_book))

    # Compare against each existing book (batch up to avoid huge prompts)
    for other in others:
        other_dict = dict(other)
        other_text = _concepts_str(other_dict)

        prompt = f"""Eres un asistente académico experto. Analiza si estos dos libros/textos tienen una relación intelectual significativa.

=== LIBRO A ===
{new_text}

=== LIBRO B ===
{other_text}

Responde SOLO con un objeto JSON con esta estructura (sin markdown):
{{
  "relation_type": "<coincide|contradice|complementa|ninguna>",
  "strength": <1-3>,
  "summary": "<una oración en español explicando la relación, o null si no hay relación>",
  "shared_concepts": ["<concepto1>", "<concepto2>"]
}}

- "coincide": ambos defienden ideas similares o el mismo marco teórico
- "contradice": sus posiciones o tesis se oponen directamente
- "complementa": uno amplía, profundiza o aplica ideas del otro
- "ninguna": no hay relación relevante
- strength 1=débil, 2=moderada, 3=fuerte
- Si relation_type es "ninguna", pon strength:0 y summary:null"""

        try:
            raw = _call_openai(api_key, prompt, max_tokens=300)
            # strip possible markdown fences
            raw = raw.strip().lstrip('```json').lstrip('```').rstrip('```').strip()
            result = json.loads(raw)
        except Exception as e:
            print(f"⚠ connections: error comparing {new_book_id} vs {other_dict['id']}: {e}")
            continue

        if result.get('relation_type', 'ninguna') == 'ninguna':
            continue

        # Upsert: one row per ordered pair (smaller id first) to avoid duplicates
        a_id, b_id = sorted([new_book_id, other_dict['id']])
        db.execute('''
            INSERT INTO book_connections
                (user_id, book_a_id, book_b_id, relation_type, strength, summary, shared_concepts)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(user_id, book_a_id, book_b_id) DO UPDATE SET
                relation_type=excluded.relation_type,
                strength=excluded.strength,
                summary=excluded.summary,
                shared_concepts=excluded.shared_concepts,
                updated_at=CURRENT_TIMESTAMP
        ''', (
            user_id, a_id, b_id,
            result.get('relation_type', 'complementa'),
            result.get('strength', 1),
            result.get('summary', ''),
            json.dumps(result.get('shared_concepts', [])),
        ))

    db.commit()
    print(f"✓ Connections built for book {new_book_id}")


def get_connections_for_book(db, user_id: int, book_id: int) -> list:
    """Return all connections involving *book_id*, with the other book's title."""
    rows = db.execute('''
        SELECT
            bc.*,
            CASE WHEN bc.book_a_id = ? THEN b_b.title ELSE b_a.title END AS other_title,
            CASE WHEN bc.book_a_id = ? THEN bc.book_b_id ELSE bc.book_a_id END AS other_id,
            CASE WHEN bc.book_a_id = ? THEN b_b.author ELSE b_a.author END AS other_author
        FROM book_connections bc
        JOIN books b_a ON b_a.id = bc.book_a_id
        JOIN books b_b ON b_b.id = bc.book_b_id
        WHERE bc.user_id = ?
          AND (bc.book_a_id = ? OR bc.book_b_id = ?)
        ORDER BY bc.strength DESC
    ''', (book_id, book_id, book_id, user_id, book_id, book_id)).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        try:
            d['shared_concepts'] = json.loads(d.get('shared_concepts') or '[]')
        except Exception:
            d['shared_concepts'] = []
        result.append(d)
    return result


def semantic_search(db, user_id: int, query: str, api_key: str) -> list:
    """
    Cross-book semantic search.
    Fetches all books, asks the AI which ones are relevant to *query*,
    returns ranked results.
    """
    books = db.execute(
        'SELECT id, title, author, branch, summary, key_concepts FROM books WHERE user_id=?',
        (user_id,)
    ).fetchall()
    if not books:
        return []

    books_text = "\n\n".join(
        f"[ID:{b['id']}] {b['title']} ({b['author']}) — {(b['summary'] or '')[:200]}"
        for b in books
    )

    prompt = f"""El usuario busca: "{query}"

Aquí está su biblioteca:
{books_text}

Devuelve SOLO un JSON (sin markdown) con los libros más relevantes, ordenados de mayor a menor relevancia:
[
  {{"id": <book_id>, "relevance": "<breve razón en español>"}},
  ...
]
Incluye solo libros que tengan contenido genuinamente relacionado con la búsqueda. Máximo 5."""

    try:
        raw = _call_openai(api_key, prompt, max_tokens=400)
        raw = raw.strip().lstrip('```json').lstrip('```').rstrip('```').strip()
        ranked = json.loads(raw)
    except Exception as e:
        print(f"⚠ semantic_search error: {e}")
        return []

    # Enrich with full book data
    book_map = {b['id']: dict(b) for b in books}
    results = []
    for item in ranked:
        bid = item.get('id')
        if bid in book_map:
            entry = book_map[bid].copy()
            entry['relevance'] = item.get('relevance', '')
            results.append(entry)
    return results