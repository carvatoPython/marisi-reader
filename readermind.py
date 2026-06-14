"""
reader_mind.py — El cerebro del lector

Módulo central que:
1. Genera preguntas de reflexión personalizadas por libro
2. Guarda y analiza las reflexiones del lector
3. Actualiza el perfil intelectual acumulativo (reader_mind)
4. Genera debates históricos entre autores
5. Simula personajes/autores
6. Detecta gaps de memoria (recuerdo inteligente)
7. Expone el perfil intelectual completo y la evolución

Endpoints registrados:
    POST /api/books/<id>/reflection/questions    → genera preguntas de reflexión
    POST /api/books/<id>/reflection/save         → guarda respuestas + actualiza mente
    GET  /api/books/<id>/reflection              → devuelve reflexiones guardadas
    GET  /api/books/<id>/debate                  → genera debate entre autores relacionados
    GET  /api/books/<id>/character-sim           → simula autor/personaje respondiendo algo
    POST /api/books/<id>/memory-check            → detecta qué recuerda realmente el lector
    GET  /api/reader/mind                        → perfil intelectual completo
    GET  /api/reader/evolution                   → línea de tiempo del pensamiento
    GET  /api/reader/affinities                  → mapa de autores afines y conflictivos
"""

import json
import urllib.request
from flask import jsonify, session, request
from database import get_db
from auth import login_required


# ─────────────────────────────────────────────────────────────
# Utilidad: llamar a OpenAI
# ─────────────────────────────────────────────────────────────
def _openai(api_key: str, prompt: str, max_tokens: int = 1200, temperature: float = 0.5) -> str:
    payload = json.dumps({
        "model": "gpt-4o-mini",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"].strip()


def _parse_json(raw: str) -> dict | list:
    raw = raw.strip().lstrip('```json').lstrip('```').rstrip('```').strip()
    return json.loads(raw)


def _get_api_key(db, user_id: int) -> str:
    import os
    env_key = os.environ.get('OPENAI_API_KEY', '').strip()
    if env_key:
        return env_key
    user = db.execute('SELECT api_key_enc FROM users WHERE id=?', (user_id,)).fetchone()
    return (user['api_key_enc'] if user else '') or ''


def _get_reader_mind(db, user_id: int) -> dict:
    row = db.execute('SELECT * FROM reader_mind WHERE user_id=?', (user_id,)).fetchone()
    if not row:
        return {}
    d = dict(row)
    for field in ('core_values', 'detected_values', 'recurring_tensions',
                  'intellectual_evolution', 'thinker_affinities', 'thinker_conflicts'):
        try:
            d[field] = json.loads(d[field]) if isinstance(d[field], str) else d[field]
        except Exception:
            d[field] = []
    try:
        d['memory_snapshots'] = json.loads(d.get('memory_snapshots') or '{}')
    except Exception:
        d['memory_snapshots'] = {}
    return d


def _save_reader_mind(db, user_id: int, updates: dict):
    """Merge updates into existing reader_mind row."""
    existing = _get_reader_mind(db, user_id)
    if not existing:
        db.execute(
            'INSERT OR IGNORE INTO reader_mind (user_id) VALUES (?)', (user_id,)
        )
        db.commit()
        existing = _get_reader_mind(db, user_id)

    # Merge list fields (append unique items)
    list_fields = ('detected_values', 'recurring_tensions', 'intellectual_evolution',
                   'thinker_affinities', 'thinker_conflicts', 'core_values')
    for field in list_fields:
        if field in updates:
            current = existing.get(field, [])
            if not isinstance(current, list):
                current = []
            new_items = updates[field] if isinstance(updates[field], list) else []
            merged = current + [i for i in new_items if i not in current]
            updates[field] = merged

    # Merge memory_snapshots (dict)
    if 'memory_snapshots' in updates:
        current_snaps = existing.get('memory_snapshots', {})
        current_snaps.update(updates['memory_snapshots'])
        updates['memory_snapshots'] = current_snaps

    set_parts = []
    values = []
    json_fields = set(list_fields) | {'memory_snapshots'}

    for key, val in updates.items():
        set_parts.append(f'{key}=?')
        values.append(json.dumps(val, ensure_ascii=False) if key in json_fields else val)

    if set_parts:
        set_parts.append('updated_at=CURRENT_TIMESTAMP')
        values.append(user_id)
        db.execute(
            f"UPDATE reader_mind SET {', '.join(set_parts)} WHERE user_id=?",
            values
        )
        db.commit()


# ─────────────────────────────────────────────────────────────
# 1. Generar preguntas de reflexión personalizadas
# ─────────────────────────────────────────────────────────────
def generate_reflection_questions(book: dict, mind: dict, api_key: str, phase: str = 'after') -> list:
    """
    Genera 6-8 preguntas de reflexión profunda sobre el libro,
    personalizadas al perfil intelectual del lector.
    """
    mind_context = ''
    if mind.get('intellectual_type'):
        mind_context = f"""
Perfil del lector:
- Tipo intelectual: {mind.get('intellectual_type', '')}
- Estilo de pensamiento: {mind.get('thinking_style', '')}
- Sesgo principal: {mind.get('main_bias', '')}
- Valores detectados: {', '.join(mind.get('detected_values', [])[:5])}
- Tensiones recurrentes: {', '.join(mind.get('recurring_tensions', [])[:3])}
"""

    phase_instruction = {
        'before': 'El lector AÚN NO ha leído el libro. Las preguntas deben capturar sus opiniones y prejuicios PREVIOS.',
        'after': 'El lector ACABA DE TERMINAR el libro. Las preguntas deben explorar su reacción, acuerdos, desacuerdos e impacto.',
        'revisit': 'El lector está REVISITANDO el libro meses después. Las preguntas deben explorar qué recuerda, qué cambió y cómo evolucionó su visión.'
    }.get(phase, 'after')

    prompt = f"""Eres un filósofo socrático especializado en facilitar reflexión profunda sobre libros.

LIBRO: {book.get('title', '')} — {book.get('author', '')}
RAMA: {book.get('branch', '')}
RESUMEN: {(book.get('summary') or '')[:600]}
{mind_context}

FASE: {phase_instruction}

Genera exactamente 7 preguntas de reflexión. Deben ser:
- Específicas al contenido real del libro (no genéricas)
- Diseñadas para revelar el pensamiento PROPIO del lector, no solo si entendió el libro
- Provocadoras pero no agresivas
- Algunas deben confrontar directamente el perfil del lector si lo conoces
- Mezcla: preguntas de acuerdo/desacuerdo, impacto emocional, aplicación personal, conexión con otras ideas

Responde SOLO con JSON (sin markdown):
[
  {{
    "id": "q1",
    "question": "...",
    "type": "agreement|emotion|application|connection|challenge",
    "why": "Por qué esta pregunta es relevante para este lector específicamente"
  }},
  ...
]"""

    try:
        raw = _openai(api_key, prompt, max_tokens=1000)
        questions = _parse_json(raw)
        return questions if isinstance(questions, list) else []
    except Exception as e:
        print(f"⚠ Error generando preguntas de reflexión: {e}")
        return [
            {"id": "q1", "question": f"¿Estás de acuerdo con la tesis principal de {book.get('author', 'el autor')}? ¿Por qué?", "type": "agreement"},
            {"id": "q2", "question": "¿Qué parte del libro te generó más incomodidad o resistencia?", "type": "challenge"},
            {"id": "q3", "question": "¿Cómo cambió (o no cambió) tu forma de pensar después de leerlo?", "type": "emotion"},
            {"id": "q4", "question": "¿Qué harías diferente en tu vida a partir de este libro?", "type": "application"},
            {"id": "q5", "question": "¿Qué idea del libro te parece más débil o difícil de defender?", "type": "challenge"},
            {"id": "q6", "question": "¿Con qué otro libro o autor conectas esto que leíste?", "type": "connection"},
            {"id": "q7", "question": "Si pudieras hablar con el autor, ¿qué le preguntarías?", "type": "emotion"},
        ]


# ─────────────────────────────────────────────────────────────
# 2. Analizar reflexiones y actualizar reader_mind
# ─────────────────────────────────────────────────────────────
def analyze_reflections_and_update_mind(book: dict, reflections: list, mind: dict, api_key: str) -> dict:
    """
    Analiza las respuestas del lector sobre un libro y extrae
    nuevas dimensiones para actualizar su perfil intelectual.
    """
    reflections_text = '\n'.join(
        f"P: {r['question']}\nR: {r['answer']}" for r in reflections
    )

    existing_evolution = mind.get('intellectual_evolution', [])
    existing_values = mind.get('detected_values', [])
    existing_tensions = mind.get('recurring_tensions', [])

    prompt = f"""Eres un psicólogo cognitivo analizando cómo un lector respondió a un libro.

LIBRO: {book.get('title', '')} — {book.get('author', '')}

RESPUESTAS DEL LECTOR:
{reflections_text}

PERFIL ACTUAL DEL LECTOR (para detectar evolución):
- Valores ya detectados: {', '.join(existing_values[:8])}
- Tensiones ya detectadas: {', '.join(existing_tensions[:5])}
- Evolución previa: {json.dumps(existing_evolution[-3:], ensure_ascii=False)}

Analiza profundamente. Responde SOLO con JSON (sin markdown):
{{
  "new_detected_values": ["nuevos valores o creencias que emergen de estas respuestas, no repetir los ya existentes"],
  "new_tensions": ["nuevas contradicciones o tensiones intelectuales detectadas"],
  "evolution_entry": "Una oración que describa cómo este libro movió el pensamiento del lector. Ej: 'Tras leer a Camus, rechazó el nihilismo pero admitió la honestidad de Meursault.'",
  "new_thinker_affinities": ["pensadores/autores con los que el lector demostró resonar en estas respuestas"],
  "new_thinker_conflicts": ["pensadores/autores con los que el lector claramente chocó o se distanció"],
  "mind_change": "¿Cambió su forma de pensar? Descripción breve o null si no hay evidencia",
  "emotional_impact": "Impacto emocional de este libro en este lector específico",
  "memory_snapshot": {{
    "strong_concepts": ["conceptos que claramente dominó o interiorizó"],
    "weak_concepts": ["conceptos que parece no haber entendido bien o ignoró"],
    "personal_connection": "cómo conectó el libro con su vida"
  }},
  "cross_book_insight": "Si hay conexión con libros o ideas que el lector mencionó, descríbela. Si no, pon null."
}}"""

    try:
        raw = _openai(api_key, prompt, max_tokens=1200, temperature=0.4)
        return _parse_json(raw)
    except Exception as e:
        print(f"⚠ Error analizando reflexiones: {e}")
        return {}


# ─────────────────────────────────────────────────────────────
# 3. Debate histórico entre autores
# ─────────────────────────────────────────────────────────────
def generate_historical_debate(book: dict, api_key: str, opponent: str = None) -> dict:
    """
    Genera un debate filosófico entre el autor del libro y otro pensador.
    Si no se especifica oponente, la IA elige el más interesante.
    """
    author = book.get('author', 'el autor')
    title = book.get('title', '')
    summary = (book.get('summary') or '')[:500]

    opponent_instruction = f"El debate es entre {author} y {opponent}." if opponent else \
        f"Elige el pensador histórico o contemporáneo que más interesantemente contrastaría con {author} sobre estas ideas. Justifica la elección."

    prompt = f"""Eres un experto en historia de las ideas. Genera un debate filosófico fascinante.

LIBRO: {title} — {author}
IDEAS CENTRALES: {summary}

{opponent_instruction}

El debate debe:
- Tener mínimo 6 intercambios (3 por pensador)
- Usar el lenguaje y estilo real de cada pensador
- Abordar las ideas centrales del libro, no trivialidades
- Incluir momentos de acuerdo parcial, no solo contradicción
- Ser intelectualmente riguroso y emocionalmente vívido

Responde SOLO con JSON (sin markdown):
{{
  "participant_a": "{author}",
  "participant_b": "Nombre del oponente elegido",
  "why_this_opponent": "Por qué este debate es particularmente revelador",
  "central_tension": "La tensión filosófica central del debate en una oración",
  "exchanges": [
    {{
      "speaker": "nombre",
      "text": "Lo que dice, en su estilo auténtico",
      "subtext": "Lo que realmente está defendiendo filosóficamente"
    }}
  ],
  "conclusion": "Síntesis: qué revela este debate sobre las ideas del libro"
}}"""

    try:
        raw = _openai(api_key, prompt, max_tokens=2000, temperature=0.7)
        return _parse_json(raw)
    except Exception as e:
        print(f"⚠ Error generando debate: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────
# 4. Simulación de autor/personaje
# ─────────────────────────────────────────────────────────────
def simulate_character(book: dict, character_name: str, user_question: str, api_key: str) -> dict:
    """
    Simula cómo respondería un autor o personaje del libro
    a una situación o pregunta del usuario.
    """
    prompt = f"""Eres {character_name}, del libro "{book.get('title', '')}" de {book.get('author', '')}.

Contexto del libro: {(book.get('summary') or '')[:400]}

El lector te pregunta: "{user_question}"

Responde:
1. En primera persona, como {character_name}, con su voz y filosofía auténtica
2. Basándote en lo que el personaje/autor realmente pensaría según la obra
3. Con profundidad filosófica, no superficialmente

Luego, FUERA del personaje, da una nota del narrador explicando qué revela esta respuesta sobre la filosofía de {character_name}.

Responde SOLO con JSON (sin markdown):
{{
  "character": "{character_name}",
  "in_character_response": "Respuesta en primera persona, como el personaje/autor hablaría",
  "narrator_note": "Análisis de qué revela esta respuesta sobre la filosofía del personaje",
  "follow_up_question": "Una pregunta que este personaje le haría al lector a su vez"
}}"""

    try:
        raw = _openai(api_key, prompt, max_tokens=800, temperature=0.7)
        return _parse_json(raw)
    except Exception as e:
        print(f"⚠ Error en simulación de personaje: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────
# 5. Recuerdo inteligente (memory check)
# ─────────────────────────────────────────────────────────────
def check_memory(book: dict, user_answers: dict, mind: dict, api_key: str) -> dict:
    """
    El usuario responde preguntas sobre un libro que leyó antes.
    La IA detecta qué recuerda bien, qué olvidó y qué tiene confuso.
    """
    key_concepts = book.get('key_concepts') or []
    if isinstance(key_concepts, str):
        try:
            key_concepts = json.loads(key_concepts)
        except Exception:
            key_concepts = []

    existing_snapshot = mind.get('memory_snapshots', {}).get(str(book.get('id')), {})

    prompt = f"""Eres un experto en memoria y aprendizaje. Analiza qué tan bien recuerda este lector el libro.

LIBRO: {book.get('title', '')} — {book.get('author', '')}
CONCEPTOS CLAVE DEL LIBRO: {json.dumps(key_concepts[:10], ensure_ascii=False)}
RESUMEN: {(book.get('summary') or '')[:400]}

RESPUESTAS ACTUALES DEL LECTOR (lo que dice recordar):
{json.dumps(user_answers, ensure_ascii=False, indent=2)}

SNAPSHOT ANTERIOR (si existe): {json.dumps(existing_snapshot, ensure_ascii=False)}

Analiza y responde SOLO con JSON (sin markdown):
{{
  "mastered_concepts": ["conceptos que claramente domina y recuerda bien"],
  "forgotten_concepts": ["conceptos importantes que claramente olvidó o no mencionó"],
  "confused_concepts": ["conceptos que recuerda pero tiene confusos o distorsionados"],
  "retention_score": <número del 1 al 10>,
  "retention_label": "Excelente|Buena|Regular|Débil|Muy débil",
  "personalized_review": [
    {{
      "concept": "concepto olvidado o confuso",
      "quick_reminder": "recordatorio breve y claro en 2-3 oraciones",
      "memory_hook": "una analogía o imagen mental para recordarlo mejor"
    }}
  ],
  "evolution_note": "¿Cómo cambió su retención vs el snapshot anterior? (o null si es el primero)"
}}"""

    try:
        raw = _openai(api_key, prompt, max_tokens=1200, temperature=0.3)
        return _parse_json(raw)
    except Exception as e:
        print(f"⚠ Error en memory check: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────
# Registrar todas las rutas
# ─────────────────────────────────────────────────────────────
def register_reader_mind_routes(app):

    # ── Preguntas de reflexión ──────────────────────────────
    @app.route('/api/books/<int:book_id>/reflection/questions', methods=['POST'])
    @login_required
    def get_reflection_questions(book_id):
        db = get_db()
        user_id = session['user_id']
        body = request.get_json() or {}
        phase = body.get('phase', 'after')

        book = db.execute('SELECT * FROM books WHERE id=? AND user_id=?', (book_id, user_id)).fetchone()
        if not book:
            return jsonify({'error': 'Libro no encontrado'}), 404

        api_key = _get_api_key(db, user_id)
        if not api_key:
            return jsonify({'error': 'No hay API key configurada'}), 400

        mind = _get_reader_mind(db, user_id)
        book_dict = dict(book)
        for f in ['key_concepts', 'summary']:
            if book_dict.get(f) and isinstance(book_dict[f], str):
                try:
                    book_dict[f] = json.loads(book_dict[f])
                except Exception:
                    pass

        questions = generate_reflection_questions(book_dict, mind, api_key, phase)
        return jsonify({'questions': questions, 'phase': phase})

    # ── Guardar reflexiones y actualizar mente ──────────────
    @app.route('/api/books/<int:book_id>/reflection/save', methods=['POST'])
    @login_required
    def save_reflections(book_id):
        db = get_db()
        user_id = session['user_id']
        body = request.get_json() or {}
        phase = body.get('phase', 'after')
        answers = body.get('answers', [])

        if not answers:
            return jsonify({'error': 'No hay respuestas para guardar'}), 400

        book = db.execute('SELECT * FROM books WHERE id=? AND user_id=?', (book_id, user_id)).fetchone()
        if not book:
            return jsonify({'error': 'Libro no encontrado'}), 404

        # Guardar cada respuesta
        for item in answers:
            db.execute(
                'INSERT INTO reader_reflections (user_id, book_id, phase, question, answer) VALUES (?,?,?,?,?)',
                (user_id, book_id, phase, item.get('question', ''), item.get('answer', ''))
            )
        db.commit()

        api_key = _get_api_key(db, user_id)
        analysis = {}
        if api_key:
            book_dict = dict(book)
            mind = _get_reader_mind(db, user_id)
            try:
                analysis = analyze_reflections_and_update_mind(book_dict, answers, mind, api_key)
            except Exception as e:
                print(f"⚠ Error analizando reflexiones: {e}")

            if analysis and not analysis.get('error'):
                mind_updates = {}
                if analysis.get('new_detected_values'):
                    mind_updates['detected_values'] = analysis['new_detected_values']
                if analysis.get('new_tensions'):
                    mind_updates['recurring_tensions'] = analysis['new_tensions']
                if analysis.get('evolution_entry'):
                    mind_updates['intellectual_evolution'] = [analysis['evolution_entry']]
                if analysis.get('new_thinker_affinities'):
                    mind_updates['thinker_affinities'] = analysis['new_thinker_affinities']
                if analysis.get('new_thinker_conflicts'):
                    mind_updates['thinker_conflicts'] = analysis['new_thinker_conflicts']
                if analysis.get('memory_snapshot'):
                    mind_updates['memory_snapshots'] = {str(book_id): analysis['memory_snapshot']}

                if mind_updates:
                    _save_reader_mind(db, user_id, mind_updates)

        return jsonify({
            'ok': True,
            'analysis': analysis,
            'cross_book_insight': analysis.get('cross_book_insight'),
            'mind_change': analysis.get('mind_change'),
            'emotional_impact': analysis.get('emotional_impact')
        })

    # ── Ver reflexiones guardadas ───────────────────────────
    @app.route('/api/books/<int:book_id>/reflection', methods=['GET'])
    @login_required
    def get_reflections(book_id):
        db = get_db()
        user_id = session['user_id']
        phase = request.args.get('phase', '')

        query = 'SELECT * FROM reader_reflections WHERE book_id=? AND user_id=?'
        params = [book_id, user_id]
        if phase:
            query += ' AND phase=?'
            params.append(phase)
        query += ' ORDER BY created_at ASC'

        rows = db.execute(query, params).fetchall()
        return jsonify([dict(r) for r in rows])

    # ── Debate histórico ────────────────────────────────────
    @app.route('/api/books/<int:book_id>/debate', methods=['GET'])
    @login_required
    def get_debate(book_id):
        db = get_db()
        user_id = session['user_id']
        opponent = request.args.get('opponent', None)

        book = db.execute('SELECT * FROM books WHERE id=? AND user_id=?', (book_id, user_id)).fetchone()
        if not book:
            return jsonify({'error': 'Libro no encontrado'}), 404

        # Retornar debate guardado si existe y no se pide regenerar
        force = request.args.get('force', 'false').lower() == 'true'
        if not force and not opponent:
            cached = db.execute(
                'SELECT * FROM historical_debates WHERE book_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1',
                (book_id, user_id)
            ).fetchone()
            if cached:
                try:
                    return jsonify({'debate': json.loads(cached['debate_text']), 'cached': True})
                except Exception:
                    pass

        api_key = _get_api_key(db, user_id)
        if not api_key:
            return jsonify({'error': 'No hay API key configurada'}), 400

        book_dict = dict(book)
        debate = generate_historical_debate(book_dict, api_key, opponent)

        if not debate.get('error'):
            participants = f"{debate.get('participant_a', '')} vs {debate.get('participant_b', '')}"
            db.execute(
                'INSERT INTO historical_debates (user_id, book_id, participants, debate_text) VALUES (?,?,?,?)',
                (user_id, book_id, participants, json.dumps(debate, ensure_ascii=False))
            )
            db.commit()

        return jsonify({'debate': debate, 'cached': False})

    # ── Simulación de personaje/autor ───────────────────────
    @app.route('/api/books/<int:book_id>/character-sim', methods=['POST'])
    @login_required
    def character_simulation(book_id):
        db = get_db()
        user_id = session['user_id']
        body = request.get_json() or {}
        character_name = body.get('character', '')
        user_question = body.get('question', '')

        if not character_name or not user_question:
            return jsonify({'error': 'Se requieren character y question'}), 400

        book = db.execute('SELECT * FROM books WHERE id=? AND user_id=?', (book_id, user_id)).fetchone()
        if not book:
            return jsonify({'error': 'Libro no encontrado'}), 404

        api_key = _get_api_key(db, user_id)
        if not api_key:
            return jsonify({'error': 'No hay API key configurada'}), 400

        result = simulate_character(dict(book), character_name, user_question, api_key)
        return jsonify(result)

    # ── Recuerdo inteligente ────────────────────────────────
    @app.route('/api/books/<int:book_id>/memory-check', methods=['POST'])
    @login_required
    def memory_check(book_id):
        db = get_db()
        user_id = session['user_id']
        body = request.get_json() or {}
        user_answers = body.get('answers', {})

        book = db.execute('SELECT * FROM books WHERE id=? AND user_id=?', (book_id, user_id)).fetchone()
        if not book:
            return jsonify({'error': 'Libro no encontrado'}), 404

        api_key = _get_api_key(db, user_id)
        if not api_key:
            return jsonify({'error': 'No hay API key configurada'}), 400

        mind = _get_reader_mind(db, user_id)
        book_dict = dict(book)
        for f in ['key_concepts']:
            if book_dict.get(f) and isinstance(book_dict[f], str):
                try:
                    book_dict[f] = json.loads(book_dict[f])
                except Exception:
                    pass

        result = check_memory(book_dict, user_answers, mind, api_key)

        # Actualizar snapshot en reader_mind
        if result and not result.get('error'):
            _save_reader_mind(db, user_id, {
                'memory_snapshots': {
                    str(book_id): {
                        'mastered': result.get('mastered_concepts', []),
                        'forgotten': result.get('forgotten_concepts', []),
                        'confused': result.get('confused_concepts', []),
                        'score': result.get('retention_score', 0),
                        'last_checked': 'now'
                    }
                }
            })

        return jsonify(result)

    # ── Perfil intelectual completo ─────────────────────────
    @app.route('/api/reader/mind', methods=['GET'])
    @login_required
    def get_reader_mind_profile():
        db = get_db()
        user_id = session['user_id']
        mind = _get_reader_mind(db, user_id)
        if not mind:
            return jsonify({'exists': False})

        # Contar libros leídos y reflexionados
        total_books = db.execute(
            'SELECT COUNT(*) as c FROM books WHERE user_id=?', (user_id,)
        ).fetchone()['c']
        reflected_books = db.execute(
            'SELECT COUNT(DISTINCT book_id) as c FROM reader_reflections WHERE user_id=?', (user_id,)
        ).fetchone()['c']

        mind['exists'] = True
        mind['stats'] = {
            'total_books': total_books,
            'reflected_books': reflected_books,
            'evolution_entries': len(mind.get('intellectual_evolution', [])),
        }
        return jsonify(mind)

    # ── Línea de tiempo intelectual ─────────────────────────
    @app.route('/api/reader/evolution', methods=['GET'])
    @login_required
    def get_intellectual_evolution():
        db = get_db()
        user_id = session['user_id']
        mind = _get_reader_mind(db, user_id)

        evolution = mind.get('intellectual_evolution', [])

        # Enriquecer con datos de libros y reflexiones
        reflections = db.execute(
            '''SELECT rr.book_id, rr.phase, rr.created_at, b.title, b.author
               FROM reader_reflections rr
               JOIN books b ON b.id = rr.book_id
               WHERE rr.user_id=?
               ORDER BY rr.created_at ASC''',
            (user_id,)
        ).fetchall()

        books_timeline = []
        seen = set()
        for r in reflections:
            key = (r['book_id'], r['phase'])
            if key not in seen:
                seen.add(key)
                books_timeline.append({
                    'book_id': r['book_id'],
                    'title': r['title'],
                    'author': r['author'],
                    'phase': r['phase'],
                    'date': r['created_at']
                })

        return jsonify({
            'evolution_entries': evolution,
            'books_timeline': books_timeline,
            'tensions': mind.get('recurring_tensions', []),
            'intellectual_type': mind.get('intellectual_type', ''),
        })

    # ── Mapa de afinidades ──────────────────────────────────
    @app.route('/api/reader/affinities', methods=['GET'])
    @login_required
    def get_affinities():
        db = get_db()
        user_id = session['user_id']
        mind = _get_reader_mind(db, user_id)

        return jsonify({
            'affinities': mind.get('thinker_affinities', []),
            'conflicts': mind.get('thinker_conflicts', []),
            'core_values': mind.get('core_values', []),
            'detected_values': mind.get('detected_values', []),
            'intellectual_type': mind.get('intellectual_type', ''),
            'main_bias': mind.get('main_bias', ''),
            'profile_summary': mind.get('profile_summary', ''),
        })