"""
flashcards.py — Nivel 4: Flashcards para repaso espaciado

Genera pares pregunta/respuesta a partir de los conceptos de un libro.
Se llama bajo demanda (no en el upload) para no ralentizar la ingesta.

Endpoints registrados:
    GET  /api/books/<id>/flashcards          → devuelve las guardadas (o genera si no hay)
    POST /api/books/<id>/flashcards/generate → regenera forzosamente
"""

import json
from flask import jsonify, session
from database import get_db
from auth import login_required


def _call_openai(api_key: str, prompt: str, max_tokens: int = 1200) -> str:
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
    with urllib.request.urlopen(req, timeout=40) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"].strip()


def generate_flashcards(book: dict, api_key: str, profile_instructions: str = '') -> list:
    """
    Returns a list of {"front": str, "back": str, "tag": str} dicts.
    """
    key_concepts = book.get('key_concepts') or '[]'
    if isinstance(key_concepts, str):
        try:
            key_concepts = json.loads(key_concepts)
        except Exception:
            key_concepts = []

    exam_questions = book.get('exam_questions') or '[]'
    if isinstance(exam_questions, str):
        try:
            exam_questions = json.loads(exam_questions)
        except Exception:
            exam_questions = []

    profile_note = f"\nPerfil del estudiante:\n{profile_instructions}" if profile_instructions else ''

    prompt = f"""Crea flashcards para repasar el siguiente contenido académico.{profile_note}

Libro: {book.get('title', '')} — {book.get('author', '')}
Rama: {book.get('branch', '')}
Resumen: {(book.get('summary') or '')[:500]}
Conceptos clave: {', '.join(str(c) for c in key_concepts[:15])}
Preguntas de examen ya generadas: {json.dumps(exam_questions[:5], ensure_ascii=False)}

Genera entre 10 y 15 flashcards de alta calidad. Cada una debe:
- Tener un FRENTE con una pregunta directa o término a definir
- Tener un REVERSO con la respuesta clara y concisa (máx. 3 oraciones)
- Tener un TAG que indique el tipo: "definición" | "aplicación" | "norma" | "jurisprudencia" | "comparación" | "proceso"

Responde SOLO con un array JSON (sin markdown):
[
  {{"front": "...", "back": "...", "tag": "..."}},
  ...
]"""

    try:
        raw = _call_openai(api_key, prompt)
        raw = raw.strip().lstrip('```json').lstrip('```').rstrip('```').strip()
        cards = json.loads(raw)
        return [c for c in cards if c.get('front') and c.get('back')]
    except Exception as e:
        print(f"⚠ flashcards generation error: {e}")
        return []


def register_flashcard_routes(app):

    def _get_api_key(db, user_id):
        """Get API key from env or user record — mirrors app.py logic."""
        import os
        env_key = os.environ.get('OPENAI_API_KEY', '').strip()
        if env_key:
            return env_key
        user = db.execute('SELECT api_key_enc FROM users WHERE id=?', (user_id,)).fetchone()
        return (user['api_key_enc'] if user else '') or ''

    @app.route('/api/books/<int:book_id>/flashcards', methods=['GET'])
    @login_required
    def get_flashcards(book_id):
        db = get_db()
        user_id = session['user_id']

        book = db.execute(
            'SELECT * FROM books WHERE id=? AND user_id=?', (book_id, user_id)
        ).fetchone()
        if not book:
            return jsonify({'error': 'Libro no encontrado'}), 404

        # Return cached cards if they exist
        cached = db.execute(
            'SELECT cards FROM flashcard_sets WHERE book_id=? AND user_id=?',
            (book_id, user_id)
        ).fetchone()
        if cached:
            try:
                return jsonify({'cards': json.loads(cached['cards']), 'cached': True})
            except Exception:
                pass

        # Generate on first access
        api_key = _get_api_key(db, user_id)
        if not api_key:
            return jsonify({'error': 'No hay API key configurada'}), 400

        from onboarding import get_user_profile_instructions
        profile = get_user_profile_instructions(user_id)
        cards = generate_flashcards(dict(book), api_key, profile)

        db.execute(
            '''INSERT INTO flashcard_sets (book_id, user_id, cards)
               VALUES (?,?,?)
               ON CONFLICT(book_id, user_id) DO UPDATE SET
                   cards=excluded.cards, updated_at=CURRENT_TIMESTAMP''',
            (book_id, user_id, json.dumps(cards, ensure_ascii=False))
        )
        db.commit()
        return jsonify({'cards': cards, 'cached': False})

    @app.route('/api/books/<int:book_id>/flashcards/generate', methods=['POST'])
    @login_required
    def regenerate_flashcards(book_id):
        db = get_db()
        user_id = session['user_id']

        book = db.execute(
            'SELECT * FROM books WHERE id=? AND user_id=?', (book_id, user_id)
        ).fetchone()
        if not book:
            return jsonify({'error': 'Libro no encontrado'}), 404

        api_key = _get_api_key(db, user_id)
        if not api_key:
            return jsonify({'error': 'No hay API key configurada'}), 400

        from onboarding import get_user_profile_instructions
        profile = get_user_profile_instructions(user_id)
        cards = generate_flashcards(dict(book), api_key, profile)

        db.execute(
            '''INSERT INTO flashcard_sets (book_id, user_id, cards)
               VALUES (?,?,?)
               ON CONFLICT(book_id, user_id) DO UPDATE SET
                   cards=excluded.cards, updated_at=CURRENT_TIMESTAMP''',
            (book_id, user_id, json.dumps(cards, ensure_ascii=False))
        )
        db.commit()
        return jsonify({'cards': cards, 'count': len(cards)})