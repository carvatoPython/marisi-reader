import json
from flask import request, jsonify, session
from database import get_db
from auth import login_required

# ─────────────────────────────────────────────────────────────
# FASE 1: Preguntas estructuradas (opción múltiple)
# ─────────────────────────────────────────────────────────────
ONBOARDING_QUESTIONS = [
    # PARTE 1: Cómo piensas
    {
        "id": "disagreement_reaction",
        "part": "¿Cómo piensas?",
        "question": "Cuando lees algo con lo que no estás de acuerdo, normalmente:",
        "options": [
            {"value": "reject", "label": "Lo rechazo inmediatamente"},
            {"value": "understand", "label": "Intento entender por qué el autor piensa así"},
            {"value": "evidence", "label": "Busco pruebas para ver quién tiene razón"},
            {"value": "flexible", "label": "Cambio de opinión fácilmente"}
        ]
    },
    {
        "id": "core_value",
        "part": "¿Cómo piensas?",
        "question": "¿Qué valoras más?",
        "options": [
            {"value": "logic", "label": "La lógica"},
            {"value": "empathy", "label": "La empatía"},
            {"value": "freedom", "label": "La libertad"},
            {"value": "discipline", "label": "La disciplina"},
            {"value": "truth", "label": "La verdad"}
        ]
    },
    {
        "id": "learning_trigger",
        "part": "¿Cómo piensas?",
        "question": "Cuando aprendes algo nuevo:",
        "options": [
            {"value": "examples", "label": "Necesito ejemplos prácticos"},
            {"value": "theory", "label": "Prefiero teoría primero"},
            {"value": "debate", "label": "Me gusta debatirlo"},
            {"value": "experience", "label": "Necesito experimentarlo"}
        ]
    },
    # PARTE 2: Perfil emocional
    {
        "id": "impact_reaction",
        "part": "Perfil emocional",
        "question": "Cuando una historia te impacta:",
        "options": [
            {"value": "analyze", "label": "Analizo el mensaje"},
            {"value": "identify", "label": "Me identifico con los personajes"},
            {"value": "apply", "label": "Pienso cómo aplicarla a mi vida"},
            {"value": "context", "label": "Me interesa el contexto histórico"}
        ]
    },
    {
        "id": "emotional_trigger",
        "part": "Perfil emocional",
        "question": "¿Qué te afecta más?",
        "options": [
            {"value": "injustice", "label": "Una injusticia"},
            {"value": "betrayal", "label": "Una traición"},
            {"value": "failure", "label": "Un fracaso"},
            {"value": "loss", "label": "Una pérdida"},
            {"value": "suffering", "label": "Ver sufrir a otros"}
        ]
    },
    {
        "id": "book_memory",
        "part": "Perfil emocional",
        "question": "¿Qué recuerdas más de un libro?",
        "options": [
            {"value": "data", "label": "Los datos"},
            {"value": "phrases", "label": "Las frases"},
            {"value": "characters", "label": "Los personajes"},
            {"value": "ideas", "label": "Las ideas"},
            {"value": "emotions", "label": "Las emociones"}
        ]
    },
    # PARTE 3: Comprensión lectora
    {
        "id": "reading_style",
        "part": "Comprensión lectora",
        "question": "Si un libro tiene 500 páginas:",
        "options": [
            {"value": "full", "label": "Leo todo"},
            {"value": "selective", "label": "Busco lo importante"},
            {"value": "mixed", "label": "Alterno entre ambas"},
            {"value": "depends", "label": "Depende del tema"}
        ]
    },
    {
        "id": "content_preference",
        "part": "Comprensión lectora",
        "question": "¿Qué disfrutas más?",
        "options": [
            {"value": "summaries", "label": "Resúmenes claros"},
            {"value": "deep", "label": "Explicaciones profundas"},
            {"value": "diagrams", "label": "Diagramas"},
            {"value": "debates", "label": "Debates"},
            {"value": "cases", "label": "Casos prácticos"}
        ]
    },
    {
        "id": "complexity_approach",
        "part": "Comprensión lectora",
        "question": "Cuando una idea es compleja:",
        "options": [
            {"value": "examples", "label": "Necesito ejemplos"},
            {"value": "analogies", "label": "Necesito analogías"},
            {"value": "discuss", "label": "Necesito discutirla"},
            {"value": "applied", "label": "Necesito verla aplicada"}
        ]
    },
    # PARTE 4: Pensamiento crítico
    {
        "id": "author_trust",
        "part": "Pensamiento crítico",
        "question": "Cuando un autor afirma algo:",
        "options": [
            {"value": "authority", "label": "Lo acepto si tiene experiencia"},
            {"value": "evidence", "label": "Busco evidencia"},
            {"value": "critics", "label": "Busco críticas"},
            {"value": "refute", "label": "Intento refutarlo"}
        ]
    },
    {
        "id": "first_action",
        "part": "Pensamiento crítico",
        "question": "¿Qué haces primero?",
        "options": [
            {"value": "errors", "label": "Buscar errores"},
            {"value": "applications", "label": "Buscar aplicaciones"},
            {"value": "contradictions", "label": "Buscar contradicciones"},
            {"value": "opportunities", "label": "Buscar oportunidades"}
        ]
    },
    {
        "id": "identity_phrase",
        "part": "Pensamiento crítico",
        "question": "¿Cuál frase te representa más?",
        "options": [
            {"value": "question_all", "label": "Todo debe cuestionarse"},
            {"value": "experience", "label": "La experiencia enseña más"},
            {"value": "pragmatic", "label": "Las ideas valen si funcionan"},
            {"value": "nuance", "label": "La verdad está en los matices"}
        ]
    },
    # PARTE 5: Objetivos
    {
        "id": "reading_goal",
        "part": "Objetivos",
        "question": "¿Por qué lees?",
        "options": [
            {"value": "exams", "label": "Aprobar exámenes"},
            {"value": "professional", "label": "Crecer profesionalmente"},
            {"value": "world", "label": "Entender el mundo"},
            {"value": "personal", "label": "Crecer personalmente"},
            {"value": "curiosity", "label": "Curiosidad"}
        ]
    },
    {
        "id": "app_goal",
        "part": "Objetivos",
        "question": "¿Qué buscas en esta aplicación?",
        "options": [
            {"value": "time", "label": "Ahorrar tiempo"},
            {"value": "understand", "label": "Comprender mejor"},
            {"value": "remember", "label": "Recordar más"},
            {"value": "debate", "label": "Debatir ideas"},
            {"value": "all", "label": "Todo lo anterior"}
        ]
    },
]

# ─────────────────────────────────────────────────────────────
# FASE 2: Preguntas abiertas profundas
# ─────────────────────────────────────────────────────────────
OPEN_QUESTIONS = [
    {
        "id": "transformative_reference",
        "question": "Nombra un libro, película o persona que haya cambiado tu forma de pensar. ¿Por qué?"
    },
    {
        "id": "contrarian_belief",
        "question": "¿Cuál es una idea que la mayoría de las personas cree y tú no?"
    },
    {
        "id": "obsession_topic",
        "question": "¿Qué tema te obsesiona aprender?"
    },
    {
        "id": "lifetime_question",
        "question": "¿Qué te gustaría entender antes de morir?"
    },
    {
        "id": "admiration",
        "question": "¿Qué admiras profundamente en una persona?"
    },
    {
        "id": "intolerance",
        "question": "¿Qué comportamiento te cuesta tolerar?"
    },
]


# ─────────────────────────────────────────────────────────────
# Construir instrucciones de perfil (para el sistema de chat)
# ─────────────────────────────────────────────────────────────
def build_profile_instructions(profile):
    level_map = {
        'beginner': 'Es un estudiante que está comenzando, explica los conceptos desde cero sin asumir conocimiento previo. Usa un lenguaje accesible.',
        'intermediate': 'Es un estudiante de nivel medio. Puede usar terminología técnica pero acompañada de contexto.',
        'advanced': 'Es un estudiante avanzado. Puede usar terminología técnica directamente y hacer referencias cruzadas con otros conceptos.',
        'professional': 'Es un profesional o autodidacta. Responde con profundidad técnica y rigor académico.'
    }
    style_map = {
        'examples': 'Siempre acompaña cada concepto o definición con un ejemplo concreto de la vida real o una analogía cotidiana.',
        'structured': 'Presenta la información con estructura clara: definición formal primero, luego características, luego aplicaciones.',
        'cases': 'Prioriza los casos prácticos y situaciones concretas para ilustrar cada concepto.',
        'mixed': 'Combina definiciones formales con ejemplos cotidianos y casos prácticos según el contexto.'
    }
    depth_map = {
        'quick': 'Sé conciso. Prioriza lo esencial. Máximo 150 palabras por respuesta a menos que se pida más.',
        'standard': 'Respuestas balanceadas con buen nivel de detalle. Máximo 300 palabras.',
        'deep': 'Respuestas completas y detalladas. Incluye matices, excepciones y conexiones con otros conceptos.'
    }
    goal_map = {
        'exams': 'El usuario estudia principalmente para exámenes. Cuando expliques, anticipa posibles preguntas de parcial.',
        'understand': 'El usuario quiere entender a fondo. Enfócate en el "por qué" detrás de cada concepto.',
        'review': 'El usuario usa esto como referencia. Estructura las respuestas para que sean fáciles de releer rápidamente.',
        'research': 'El usuario investiga. Conecta conceptos con sus fuentes originales y sugiere relaciones con otros temas.'
    }

    parts = []
    if profile.get('level'): parts.append(level_map.get(profile['level'], ''))
    if profile.get('style'): parts.append(style_map.get(profile['style'], ''))
    if profile.get('depth'): parts.append(depth_map.get(profile['depth'], ''))
    if profile.get('goal'): parts.append(goal_map.get(profile['goal'], ''))

    interests = profile.get('interests', [])
    if interests:
        parts.append(f"Las áreas de interés del usuario son: {', '.join(interests)}. Conecta el contenido con estas áreas cuando sea relevante.")

    custom = profile.get('custom_instructions', '')
    if custom:
        parts.append(f"Instrucciones adicionales del usuario: {custom}")

    # Agregar perfil intelectual si existe
    mind = profile.get('reader_mind', {})
    if mind.get('thinking_style'):
        parts.append(f"Estilo de pensamiento del lector: {mind['thinking_style']}")
    if mind.get('intellectual_type'):
        parts.append(f"Tipo intelectual: {mind['intellectual_type']}")
    if mind.get('main_bias'):
        parts.append(f"Sesgo principal detectado: {mind['main_bias']}")
    if mind.get('thinker_affinities'):
        try:
            affinities = json.loads(mind['thinker_affinities']) if isinstance(mind['thinker_affinities'], str) else mind['thinker_affinities']
            if affinities:
                parts.append(f"Autores/pensadores con los que resuena: {', '.join(affinities)}")
        except Exception:
            pass
    if mind.get('detected_values'):
        try:
            values = json.loads(mind['detected_values']) if isinstance(mind['detected_values'], str) else mind['detected_values']
            if values:
                parts.append(f"Valores detectados en el lector: {', '.join(values[:5])}")
        except Exception:
            pass

    return '\n'.join(p for p in parts if p)


# ─────────────────────────────────────────────────────────────
# Interpretar respuestas con IA y generar perfil inicial
# ─────────────────────────────────────────────────────────────
def _interpret_onboarding_with_ai(structured_answers: dict, open_answers: dict, api_key: str) -> dict:
    """
    Llama a GPT para interpretar todas las respuestas y generar
    el perfil intelectual inicial del lector.
    """
    import urllib.request

    all_answers = {
        "respuestas_estructuradas": structured_answers,
        "respuestas_abiertas": open_answers
    }

    prompt = f"""Eres un psicólogo cognitivo y experto en perfiles intelectuales. 
Analiza estas respuestas de onboarding de un nuevo lector y genera su perfil intelectual inicial.

RESPUESTAS DEL USUARIO:
{json.dumps(all_answers, ensure_ascii=False, indent=2)}

Genera un perfil profundo. Responde SOLO con JSON válido (sin markdown):
{{
  "intellectual_type": "Una etiqueta de 2-4 palabras que capture la esencia (ej: 'Analítico-Pragmático', 'Humanista-Crítico', 'Empirista-Reflexivo')",
  "thinking_style": "Descripción de 2-3 oraciones de cómo procesa el conocimiento este lector",
  "emotional_profile": "Descripción de 2-3 oraciones de su perfil emocional como lector",
  "critical_tendency": "Descripción de cómo ejerce el pensamiento crítico",
  "learning_preference": "Descripción de cómo aprende mejor",
  "main_bias": "El sesgo cognitivo o tendencia más notable (ej: 'Busca aplicaciones antes que teoría', 'Tiende a rechazar ideas antes de comprenderlas')",
  "core_values": ["valor1", "valor2", "valor3"],
  "detected_values": ["valor o creencia detectada 1", "valor o creencia detectada 2", "..."],
  "thinker_affinities": ["Pensador o autor con el que probablemente resuene 1", "..."],
  "thinker_conflicts": ["Pensador o autor que probablemente lo desafíe 1", "..."],
  "profile_summary": "Párrafo de 4-6 oraciones que describe quién es este lector intelectualmente, qué lo mueve, cómo piensa y qué busca",
  "intellectual_evolution": ["Punto de partida intelectual detectado a partir de sus respuestas"]
}}

Sé específico y perspicaz. No seas genérico. Si menciona una referencia concreta (libro, persona, film), úsala para personalizar el análisis."""

    payload = json.dumps({
        "model": "gpt-4o-mini",
        "max_tokens": 1500,
        "temperature": 0.4,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        data = json.loads(resp.read())

    raw = data["choices"][0]["message"]["content"].strip()
    raw = raw.lstrip('```json').lstrip('```').rstrip('```').strip()
    return json.loads(raw)


# ─────────────────────────────────────────────────────────────
# Registrar rutas
# ─────────────────────────────────────────────────────────────
def register_onboarding_routes(app):

    @app.route('/api/onboarding/questions', methods=['GET'])
    def get_questions():
        return jsonify(ONBOARDING_QUESTIONS)

    @app.route('/api/onboarding/open-questions', methods=['GET'])
    def get_open_questions():
        return jsonify(OPEN_QUESTIONS)

    @app.route('/api/onboarding/save', methods=['POST'])
    @login_required
    def save_onboarding():
        db = get_db()
        body = request.get_json()
        user_id = session['user_id']

        # Datos básicos de perfil (compatibilidad con lo existente)
        level = body.get('level', 'intermediate')
        style = body.get('style', 'mixed')
        depth = body.get('depth', 'standard')
        interests = body.get('interests', [])
        goal = body.get('goal', 'understand')
        custom = body.get('custom_instructions', '')

        profile_data = {'level': level, 'style': style, 'depth': depth,
                        'interests': interests, 'goal': goal}
        instructions = build_profile_instructions(profile_data)

        db.execute('''
            INSERT INTO user_profiles (user_id, level, learning_style, depth, goal, interests, custom_instructions, onboarding_done)
            VALUES (?,?,?,?,?,?,?,1)
            ON CONFLICT(user_id) DO UPDATE SET
                level=excluded.level, learning_style=excluded.learning_style,
                depth=excluded.depth, goal=excluded.goal,
                interests=excluded.interests, custom_instructions=excluded.custom_instructions,
                onboarding_done=1, updated_at=CURRENT_TIMESTAMP
        ''', (user_id, level, style, depth, goal, json.dumps(interests), custom))
        db.commit()
        return jsonify({'ok': True, 'instructions': instructions})

    @app.route('/api/onboarding/save-full', methods=['POST'])
    @login_required
    def save_full_onboarding():
        """
        Recibe todas las respuestas (estructuradas + abiertas),
        llama a la IA para interpretarlas y guarda el perfil en reader_mind.
        """
        import os
        db = get_db()
        body = request.get_json()
        user_id = session['user_id']

        structured_answers = body.get('structured', {})
        open_answers = body.get('open', {})

        # Derivar campos básicos de user_profiles a partir de las respuestas
        level_map = {'exams': 'beginner', 'professional': 'advanced'}
        goal_raw = structured_answers.get('reading_goal', 'understand')
        level = level_map.get(goal_raw, 'intermediate')

        learning_map = {
            'examples': 'examples', 'experience': 'cases',
            'theory': 'structured', 'debate': 'mixed'
        }
        style = learning_map.get(structured_answers.get('learning_trigger', 'mixed'), 'mixed')

        content_pref = structured_answers.get('content_preference', 'deep')
        depth = 'deep' if content_pref in ('deep', 'debates') else 'standard'

        goal_app = structured_answers.get('app_goal', 'understand')
        goal = goal_app if goal_app in ('exams', 'understand', 'review', 'research') else 'understand'

        # Guardar en user_profiles (compatibilidad)
        db.execute('''
            INSERT INTO user_profiles (user_id, level, learning_style, depth, goal, interests, onboarding_done)
            VALUES (?,?,?,?,?,?,1)
            ON CONFLICT(user_id) DO UPDATE SET
                level=excluded.level, learning_style=excluded.learning_style,
                depth=excluded.depth, goal=excluded.goal,
                onboarding_done=1, updated_at=CURRENT_TIMESTAMP
        ''', (user_id, level, style, depth, goal, '[]'))

        # Intentar interpretación con IA
        env_key = os.environ.get('OPENAI_API_KEY', '').strip()
        user_row = db.execute('SELECT api_key_enc FROM users WHERE id=?', (user_id,)).fetchone()
        api_key = env_key or (user_row['api_key_enc'] if user_row else '') or ''

        mind_data = {}
        if api_key:
            try:
                mind_data = _interpret_onboarding_with_ai(structured_answers, open_answers, api_key)
            except Exception as e:
                print(f"⚠ Error interpretando onboarding con IA: {e}")
                mind_data = {}

        all_answers = {'structured': structured_answers, 'open': open_answers}

        db.execute('''
            INSERT INTO reader_mind (
                user_id, onboarding_answers, thinking_style, emotional_profile,
                critical_tendency, learning_preference, core_values,
                detected_values, recurring_tensions, intellectual_evolution,
                thinker_affinities, thinker_conflicts, profile_summary,
                intellectual_type, main_bias
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
                onboarding_answers=excluded.onboarding_answers,
                thinking_style=excluded.thinking_style,
                emotional_profile=excluded.emotional_profile,
                critical_tendency=excluded.critical_tendency,
                learning_preference=excluded.learning_preference,
                core_values=excluded.core_values,
                detected_values=excluded.detected_values,
                intellectual_evolution=excluded.intellectual_evolution,
                thinker_affinities=excluded.thinker_affinities,
                thinker_conflicts=excluded.thinker_conflicts,
                profile_summary=excluded.profile_summary,
                intellectual_type=excluded.intellectual_type,
                main_bias=excluded.main_bias,
                updated_at=CURRENT_TIMESTAMP
        ''', (
            user_id,
            json.dumps(all_answers, ensure_ascii=False),
            mind_data.get('thinking_style', ''),
            mind_data.get('emotional_profile', ''),
            mind_data.get('critical_tendency', ''),
            mind_data.get('learning_preference', ''),
            json.dumps(mind_data.get('core_values', []), ensure_ascii=False),
            json.dumps(mind_data.get('detected_values', []), ensure_ascii=False),
            json.dumps([], ensure_ascii=False),
            json.dumps(mind_data.get('intellectual_evolution', []), ensure_ascii=False),
            json.dumps(mind_data.get('thinker_affinities', []), ensure_ascii=False),
            json.dumps(mind_data.get('thinker_conflicts', []), ensure_ascii=False),
            mind_data.get('profile_summary', ''),
            mind_data.get('intellectual_type', ''),
            mind_data.get('main_bias', ''),
        ))
        db.commit()

        return jsonify({
            'ok': True,
            'profile': mind_data,
            'intellectual_type': mind_data.get('intellectual_type', ''),
            'profile_summary': mind_data.get('profile_summary', '')
        })

    @app.route('/api/onboarding/profile', methods=['GET'])
    @login_required
    def get_profile():
        db = get_db()
        user_id = session['user_id']
        profile = db.execute('SELECT * FROM user_profiles WHERE user_id=?', (user_id,)).fetchone()
        if not profile:
            return jsonify({'onboarding_done': False})
        data = dict(profile)
        try: data['interests'] = json.loads(data['interests'])
        except: data['interests'] = []
        return jsonify(data)


# ─────────────────────────────────────────────────────────────
# Helpers públicos usados por otros módulos
# ─────────────────────────────────────────────────────────────
def get_user_profile_instructions(user_id):
    db = get_db()
    profile = db.execute('SELECT * FROM user_profiles WHERE user_id=?', (user_id,)).fetchone()
    mind = db.execute('SELECT * FROM reader_mind WHERE user_id=?', (user_id,)).fetchone()

    if not profile:
        return ''

    profile_dict = dict(profile)
    try: interests = json.loads(profile_dict['interests'])
    except: interests = []

    mind_dict = dict(mind) if mind else {}

    return build_profile_instructions({
        'level': profile_dict.get('level'),
        'style': profile_dict.get('learning_style'),
        'depth': profile_dict.get('depth', 'standard'),
        'interests': interests,
        'custom_instructions': profile_dict.get('custom_instructions') or '',
        'reader_mind': mind_dict
    })