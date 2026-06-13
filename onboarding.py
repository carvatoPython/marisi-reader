import json
from flask import request, jsonify, session
from database import get_db
from auth import login_required

ONBOARDING_QUESTIONS = [
    {
        "id": "level",
        "question": "¿En qué etapa estás en tus estudios?",
        "options": [
            {"value": "beginner", "label": "Comenzando (primeros semestres)"},
            {"value": "intermediate", "label": "En la mitad de la carrera"},
            {"value": "advanced", "label": "Ya avanzado / últimos semestres"},
            {"value": "professional", "label": "Profesional / autodidacta"}
        ]
    },
    {
        "id": "style",
        "question": "¿Cómo aprendes mejor un concepto nuevo?",
        "options": [
            {"value": "examples", "label": "Con ejemplos de la vida real y analogías"},
            {"value": "structured", "label": "Con definiciones formales y estructura clara"},
            {"value": "cases", "label": "Con casos prácticos y situaciones concretas"},
            {"value": "mixed", "label": "Una mezcla de todo lo anterior"}
        ]
    },
    {
        "id": "depth",
        "question": "¿Qué tan profundo quieres que sea el análisis?",
        "options": [
            {"value": "quick", "label": "Rápido — lo esencial para entender el tema"},
            {"value": "standard", "label": "Estándar — buenos detalles sin abrumar"},
            {"value": "deep", "label": "Profundo — quiero entender todo a fondo"}
        ]
    },
    {
        "id": "interests",
        "question": "¿Qué áreas te interesan? (puedes elegir varias)",
        "multi": True,
        "options": [
            {"value": "law", "label": "Derecho y ciencias jurídicas"},
            {"value": "tech", "label": "Tecnología y programación"},
            {"value": "data", "label": "Data science e IA"},
            {"value": "business", "label": "Negocios y emprendimiento"},
            {"value": "personal", "label": "Desarrollo personal"},
            {"value": "science", "label": "Ciencias exactas / naturales"},
            {"value": "humanities", "label": "Humanidades y ciencias sociales"}
        ]
    },
    {
        "id": "goal",
        "question": "¿Cuál es tu objetivo principal al usar Marisi Reader?",
        "options": [
            {"value": "exams", "label": "Prepararme para exámenes y parciales"},
            {"value": "understand", "label": "Entender temas complejos rápidamente"},
            {"value": "review", "label": "Tener un catálogo de referencia para repasar"},
            {"value": "research", "label": "Investigar y profundizar en temas"}
        ]
    }
]

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

    return '\n'.join(p for p in parts if p)

def register_onboarding_routes(app):

    @app.route('/api/onboarding/questions', methods=['GET'])
    def get_questions():
        return jsonify(ONBOARDING_QUESTIONS)

    @app.route('/api/onboarding/save', methods=['POST'])
    @login_required
    def save_onboarding():
        db = get_db()
        body = request.get_json()
        user_id = session['user_id']

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
            INSERT INTO user_profiles (user_id, level, learning_style, interests, custom_instructions, onboarding_done)
            VALUES (?,?,?,?,?,1)
            ON CONFLICT(user_id) DO UPDATE SET
                level=excluded.level, learning_style=excluded.learning_style,
                interests=excluded.interests, custom_instructions=excluded.custom_instructions,
                onboarding_done=1, updated_at=CURRENT_TIMESTAMP
        ''', (user_id, level, style, json.dumps(interests), custom))
        db.commit()
        return jsonify({'ok': True, 'instructions': instructions})

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

def get_user_profile_instructions(user_id):
    db = get_db()
    profile = db.execute('SELECT * FROM user_profiles WHERE user_id=?', (user_id,)).fetchone()
    if not profile:
        return ''
    try: interests = json.loads(profile['interests'])
    except: interests = []
    return build_profile_instructions({
        'level': profile['level'],
        'style': profile['learning_style'],
        'depth': profile.get('depth', 'standard'),
        'interests': interests,
        'custom_instructions': profile['custom_instructions'] or ''
    })
