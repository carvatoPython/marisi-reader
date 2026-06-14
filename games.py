import json, re
from flask import request, jsonify, session
from database import get_db
from auth import login_required
from onboarding import get_user_profile_instructions

def generate_game(book_data, api_key, profile_instructions=''):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    for f in ['key_concepts','chapter_map','summary']:
        if isinstance(book_data.get(f), str):
            try: book_data[f] = json.loads(book_data[f])
            except: pass

    prompt = f"""Eres un diseñador de juegos educativos. Crea un mini-juego de comprensión e interpretación basado en este libro/contenido:

TÍTULO: {book_data.get('title','')}
RESUMEN: {book_data.get('summary','')}
CONCEPTOS CLAVE: {json.dumps(book_data.get('key_concepts',[])[:8], ensure_ascii=False)}
ESTRUCTURA: {json.dumps(book_data.get('chapter_map',[])[:5], ensure_ascii=False)}

{f"PERFIL DEL USUARIO: {profile_instructions}" if profile_instructions else ''}

Genera SOLO un JSON válido con esta estructura exacta:
{{
  "category": "Una categoría temática breve y atractiva relacionada con el libro (ej: 'Relaciones humanas en El Principito')",
  "fragment_text": "Un fragmento, cita o escena representativa del libro (3-6 oraciones, en español, fiel al contenido y tono del libro)",
  "questions": [
    {{
      "type": "comprehension",
      "question": "Pregunta sobre QUÉ pasa o significa el fragmento/concepto (tiene respuesta correcta objetiva)",
      "options": ["opción A", "opción B", "opción C", "opción D"],
      "correct_index": 0,
      "explanation": "Breve explicación de por qué es correcta"
    }},
    {{
      "type": "comprehension",
      "question": "...",
      "options": ["...","...","...","..."],
      "correct_index": 2,
      "explanation": "..."
    }},
    {{
      "type": "comprehension",
      "question": "...",
      "options": ["...","...","...","..."],
      "correct_index": 1,
      "explanation": "..."
    }},
    {{
      "type": "interpretation",
      "question": "Pregunta de interpretación personal SIN respuesta correcta — explora cómo el usuario interpreta el fragmento, con qué se identifica, o qué haría en esa situación",
      "options": ["opción A (un tipo de interpretación/valor)", "opción B (otro tipo)", "opción C (otro tipo)", "opción D (otro tipo)"]
    }},
    {{
      "type": "interpretation",
      "question": "Otra pregunta de interpretación personal diferente",
      "options": ["...","...","...","..."]
    }}
  ]
}}

Reglas:
- Exactamente 5 preguntas: 3 de tipo "comprehension" (con correct_index y explanation) y 2 de tipo "interpretation" (sin correct_index ni explanation, las 4 opciones representan distintas formas válidas de pensar/interpretar, ninguna es "correcta").
- Las preguntas de interpretación deben revelar valores, prioridades o estilo de pensamiento del usuario (ej: qué admira, cómo resuelve conflictos, qué prioriza).
- Todo en español, tono cercano y motivador.
- Responde SOLO el JSON, nada más.
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0.7, max_tokens=2000
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r'^```(?:json)?\s*','',raw)
    raw = re.sub(r'\s*```$','',raw)
    return json.loads(raw)


def generate_insights(book_title, questions, answers, api_key, profile_instructions=''):
    """After a game session, analyze interpretation answers to extract cognitive/personality insights."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    interpretation_data = []
    for i, q in enumerate(questions):
        if q.get('type') == 'interpretation':
            ans_idx = answers.get(str(i))
            if ans_idx is not None and 0 <= ans_idx < len(q.get('options', [])):
                interpretation_data.append({
                    'question': q['question'],
                    'chosen_option': q['options'][ans_idx]
                })

    if not interpretation_data:
        return ''

    prompt = f"""Eres un analista de perfiles cognitivos. Un usuario jugó un juego de comprensión sobre el libro "{book_title}" y respondió estas preguntas de interpretación personal:

{json.dumps(interpretation_data, ensure_ascii=False, indent=2)}

{f"PERFIL PREVIO DEL USUARIO: {profile_instructions}" if profile_instructions else ''}

Basándote en estas respuestas, escribe 2-4 frases breves (en español) que describan rasgos del perfil cognitivo/de pensamiento del usuario que se revelan aquí — qué valora, cómo interpreta situaciones, qué prioriza. Sé específico y evita generalidades vagas. Estas frases se usarán para personalizar futuras interacciones con el usuario.

Responde solo con las frases, sin introducción ni comentarios adicionales."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0.5, max_tokens=300
    )
    return response.choices[0].message.content.strip()


def register_game_routes(app):

    @app.route('/api/books/<int:book_id>/game', methods=['POST'])
    @login_required
    def create_game(book_id):
        from app import get_api_key
        user_id = session['user_id']
        db = get_db()
        api_key = get_api_key(db, user_id)
        if not api_key:
            return jsonify({'error':'No hay una API key de OpenAI configurada'}), 400

        book = db.execute('SELECT * FROM books WHERE id=? AND user_id=?', (book_id, user_id)).fetchone()
        if not book:
            return jsonify({'error':'Libro no encontrado'}), 404

        profile_instructions = get_user_profile_instructions(user_id)

        try:
            game = generate_game(dict(book), api_key, profile_instructions)
        except Exception as e:
            app.logger.exception('Error generating game')
            return jsonify({'error': f'Error al generar el juego: {str(e)}'}), 500

        max_score = sum(1 for q in game['questions'] if q.get('type') == 'comprehension')

        cur = db.execute('''
            INSERT INTO game_sessions (user_id, book_id, category, fragment_text, questions_json, max_score)
            VALUES (?,?,?,?,?,?)
        ''', (user_id, book_id, game['category'], game['fragment_text'], json.dumps(game['questions']), max_score))
        db.commit()

        return jsonify({
            'ok': True,
            'session_id': cur.lastrowid,
            'category': game['category'],
            'fragment_text': game['fragment_text'],
            'questions': [
                {k:v for k,v in q.items() if k not in ('correct_index','explanation')}
                for q in game['questions']
            ]
        })

    @app.route('/api/games/<int:session_id>/answer', methods=['POST'])
    @login_required
    def submit_game_answer(session_id):
        user_id = session['user_id']
        db = get_db()
        body = request.get_json()
        question_index = body.get('question_index')
        answer_index = body.get('answer_index')

        game_session = db.execute('SELECT * FROM game_sessions WHERE id=? AND user_id=?', (session_id, user_id)).fetchone()
        if not game_session:
            return jsonify({'error':'Sesión no encontrada'}), 404

        answers = json.loads(game_session['answers_json'] or '{}')
        answers[str(question_index)] = answer_index
        db.execute('UPDATE game_sessions SET answers_json=? WHERE id=?', (json.dumps(answers), session_id))
        db.commit()

        questions = json.loads(game_session['questions_json'])
        q = questions[question_index]
        result = {'ok': True}
        if q.get('type') == 'comprehension':
            correct = answer_index == q.get('correct_index')
            result['correct'] = correct
            result['correct_index'] = q.get('correct_index')
            result['explanation'] = q.get('explanation', '')

        return jsonify(result)

    @app.route('/api/games/<int:session_id>/finish', methods=['POST'])
    @login_required
    def finish_game(session_id):
        from app import get_api_key
        user_id = session['user_id']
        db = get_db()
        api_key = get_api_key(db, user_id)

        game_session = db.execute('SELECT * FROM game_sessions WHERE id=? AND user_id=?', (session_id, user_id)).fetchone()
        if not game_session:
            return jsonify({'error':'Sesión no encontrada'}), 404

        questions = json.loads(game_session['questions_json'])
        answers = json.loads(game_session['answers_json'] or '{}')

        score = 0
        for i, q in enumerate(questions):
            if q.get('type') == 'comprehension':
                if answers.get(str(i)) == q.get('correct_index'):
                    score += 1

        book = db.execute('SELECT title FROM books WHERE id=?', (game_session['book_id'],)).fetchone()
        profile_instructions = get_user_profile_instructions(user_id)

        insights = ''
        if api_key:
            try:
                insights = generate_insights(book['title'], questions, answers, api_key, profile_instructions)
            except Exception:
                app.logger.exception('Error generating insights')

        db.execute('''UPDATE game_sessions SET score=?, completed=1, interpretation_insights=? WHERE id=?''',
                   (score, insights, session_id))
        db.commit()

        if insights:
            profile = db.execute('SELECT interpretation_profile FROM user_profiles WHERE user_id=?', (user_id,)).fetchone()
            existing = (profile['interpretation_profile'] if profile else '') or ''
            updated = (existing + '\n' + insights).strip()
            # keep last ~2000 chars to avoid unbounded growth
            if len(updated) > 2000:
                updated = updated[-2000:]
            db.execute('UPDATE user_profiles SET interpretation_profile=? WHERE user_id=?', (updated, user_id))
            db.commit()

        return jsonify({
            'ok': True,
            'score': score,
            'max_score': game_session['max_score'],
            'insights': insights
        })

    @app.route('/api/books/<int:book_id>/games', methods=['GET'])
    @login_required
    def list_games(book_id):
        user_id = session['user_id']
        db = get_db()
        rows = db.execute('''SELECT id, category, score, max_score, completed, created_at
                              FROM game_sessions WHERE book_id=? AND user_id=? ORDER BY created_at DESC''',
                           (book_id, user_id)).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.route('/api/profile/insights', methods=['GET'])
    @login_required
    def get_profile_insights():
        user_id = session['user_id']
        db = get_db()
        profile = db.execute('SELECT interpretation_profile FROM user_profiles WHERE user_id=?', (user_id,)).fetchone()
        return jsonify({'interpretation_profile': (profile['interpretation_profile'] if profile else '') or ''})