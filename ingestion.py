"""
ingestion.py — Motor de análisis en 4 pasos

Paso 1: Extraer hechos (trama, personajes, eventos, estructura)
Paso 2: Extraer temas (conflictos, preguntas filosóficas, tesis)
Paso 3: Enriquecer con lo que dicen lectores reales (Reddit, Goodreads, comunidades)
Paso 4: Sintetizar todo conectando conflicto del libro + conflicto del lector
"""

import os, json, re, base64
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import pdfplumber

MAX_CHARS = 80000

CONTENT_TYPES = {
    'legal':        {'label': 'Jurídico / Derecho'},
    'tech':         {'label': 'Tecnología / Programación'},
    'data_science': {'label': 'Data Science / IA / ML'},
    'philosophy':   {'label': 'Filosofía / Pensamiento'},
    'personal':     {'label': 'Desarrollo personal / Negocios'},
    'article':      {'label': 'Artículo / Ensayo / Paper'},
}

# ─── EXTRACCIÓN DE TEXTO ──────────────────────────────────────────────────────

def extract_from_pdf(filepath):
    text = ''; pages = 0
    with pdfplumber.open(filepath) as pdf:
        pages = len(pdf.pages)
        for page in pdf.pages:
            t = page.extract_text()
            if t: text += t + '\n'
            if len(text) >= MAX_CHARS: break
    return text[:MAX_CHARS], pages

def extract_from_image(filepath, api_key):
    client = OpenAI(api_key=api_key)
    with open(filepath, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    ext = filepath.rsplit('.',1)[-1].lower()
    mime = {'jpg':'jpeg','jpeg':'jpeg','png':'png','webp':'webp'}.get(ext,'jpeg')
    r = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role":"user","content":[
            {"type":"image_url","image_url":{"url":f"data:image/{mime};base64,{b64}"}},
            {"type":"text","text":"Transcribe TODO el texto de la imagen completa y ordenadamente. Solo el texto."}
        ]}], max_tokens=4000)
    return r.choices[0].message.content.strip(), 1

def extract_from_url(url, api_key):
    headers = {'User-Agent':'Mozilla/5.0 (compatible; MarisiReader/2.0)'}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        for tag in soup(['script','style','nav','footer','header','aside']): tag.decompose()
        lines = [l.strip() for l in soup.get_text('\n',strip=True).split('\n') if len(l.strip())>30]
        return '\n'.join(lines)[:MAX_CHARS], 1
    except Exception as e:
        raise ValueError(f"No se pudo acceder a la URL: {str(e)}")

def extract_from_epub(filepath):
    try:
        import ebooklib  # type: ignore[import]
        from ebooklib import epub  # type: ignore[import]
    except ImportError:
        raise ValueError("EbookLib no está instalado.")
    b = epub.read_epub(filepath)
    texts = []
    for item in b.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), 'html.parser')
        t = soup.get_text('\n', strip=True)
        if t: texts.append(t)
    full = '\n'.join(texts)[:MAX_CHARS]
    return full, max(1, len(full.split())//250)

def extract_from_docx(filepath):
    try:
        from docx import Document  # type: ignore[import]
    except ImportError:
        raise ValueError("python-docx no está instalado.")
    doc = Document(filepath)
    full = '\n'.join(p.text.strip() for p in doc.paragraphs if p.text.strip())[:MAX_CHARS]
    return full, max(1, len(full.split())//250)

# ─── LLAMADA A GPT ────────────────────────────────────────────────────────────

def _gpt(client, prompt, max_tokens=2000, temperature=0.3, json_mode=True):
    kwargs = dict(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    r = client.chat.completions.create(**kwargs)
    raw = r.choices[0].message.content.strip()
    if json_mode:
        raw = re.sub(r'^```(?:json)?\s*','',raw)
        raw = re.sub(r'\s*```$','',raw)
        return json.loads(raw)
    return raw

# ─── DETECCIÓN ───────────────────────────────────────────────────────────────

def detect_content_type(text: str, api_key: str) -> str:
    client = OpenAI(api_key=api_key)
    snippet = text[:2500]
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":f"""Clasifica en UNA categoría:
legal / tech / data_science / philosophy / personal / article

TEXTO:
{snippet}

Responde SOLO con la clave."""}],
        temperature=0, max_tokens=15)
    detected = r.choices[0].message.content.strip().lower()
    return detected if detected in CONTENT_TYPES else 'personal'

# ─── PASO 1: HECHOS ──────────────────────────────────────────────────────────

def _step1_facts(text: str, content_type: str, client) -> dict:
    """
    Extrae los hechos objetivos del libro:
    estructura, personajes, eventos, normas, conceptos técnicos.
    Sin interpretación. Solo lo que hay.
    """
    type_instructions = {
        'philosophy': """Extrae:
- structure: lista de partes/capítulos con los argumentos reales de cada sección
- key_figures: filósofos, obras y corrientes que aparecen y qué posición tienen
- central_arguments: los argumentos principales en orden lógico
- key_terms: términos técnicos con la definición EXACTA del autor (no Wikipedia)
- what_gets_missed: detalles, matices o argumentos que los lectores suelen ignorar""",
        'legal': """Extrae:
- structure: capítulos/secciones con los temas jurídicos de cada uno
- norms: TODAS las normas citadas (ley, decreto, artículo) con contenido exacto
- cases: todos los fallos y sentencias con su ratio decidendi
- key_concepts: conceptos jurídicos con definición doctrinal rigurosa y fuente
- doctrinal_debates: posiciones doctrinales encontradas que menciona el texto
- what_gets_missed: matices jurídicos, excepciones o casos límite que suelen pasarse por alto""",
        'tech': """Extrae:
- structure: capítulos con los temas técnicos de cada uno
- concepts: conceptos técnicos con definición, ejemplo de código/uso y cuándo NO usar
- tools: herramientas/librerías con casos de uso reales y limitaciones honestas
- prerequisites: qué conocimiento previo asume el libro
- what_gets_missed: errores comunes, edge cases o limitaciones que el libro menciona pero los lectores pasan por alto""",
        'data_science': """Extrae:
- structure: capítulos con los conceptos ML/estadística de cada uno
- algorithms: algoritmos con intuición, caso de uso y cuándo fallan
- tools: librerías/frameworks con trade-offs reales
- math_concepts: conceptos matemáticos con intuición (sin fórmulas pesadas)
- what_gets_missed: supuestos que los modelos hacen y que los lectores suelen ignorar""",
        'personal': """Extrae:
- structure: capítulos con las ideas principales de cada uno
- core_claims: las afirmaciones centrales del autor (puede ser polémicas)
- evidence: qué evidencia usa el autor para cada afirmación
- exercises: ejercicios o acciones concretas que propone
- what_gets_missed: matices, excepciones o advertencias que el autor incluye pero los lectores ignoran""",
        'article': """Extrae:
- thesis: la tesis exacta del artículo
- arguments: los argumentos en orden con su evidencia
- sources: fuentes citadas y cómo se usan
- limitations: limitaciones que el propio autor reconoce
- what_gets_missed: supuestos no explicitados""",
    }

    instructions = type_instructions.get(content_type, type_instructions['personal'])

    prompt = f"""Eres un lector extremadamente preciso. Tu trabajo es extraer los HECHOS del siguiente texto.
No interpretes. No evalúes. No conectes con el lector.
Solo extrae lo que hay, con la mayor precisión y completitud posible.

{instructions}

EXTRAE TAMBIÉN (para todos los tipos de contenido):

JERARQUÍA DE IMPORTANCIA — clasifica los conceptos/ideas en 3 niveles:
  Nivel A: lo fundamental — si solo recuerdas 3 cosas, son estas
  Nivel B: importante pero secundario
  Nivel C: detalle o contexto

EVOLUCIÓN / PROGRESIÓN — ¿hay una transformación, argumento que avanza, o narrativa que cambia?
  Si es ficción/filosofía: cómo evoluciona el protagonista o el argumento
  Si es jurídico: cómo progresa la doctrina o el razonamiento
  Si es técnico: cómo progresa la complejidad del conocimiento

PREGUNTAS QUE EL LIBRO INTENTA RESPONDER — no el tema, sino las preguntas reales:
  Ej: No "trata sobre la muerte" sino "¿puede alguien ser juzgado por quién es y no por lo que hizo?"

EVIDENCIA TEXTUAL — para los conceptos más importantes, extrae fragmentos textuales exactos
  con indicación de dónde aparecen (capítulo, sección o contexto aproximado)

Responde SOLO con JSON válido:
{{
  "title": "título exacto",
  "author": "autor o '---'",
  "year": "año o '---'",
  "structure": [
    {{"section": "nombre de la sección/capítulo", "content": "qué argumenta o desarrolla esta sección"}}
  ],
  "key_concepts": [
    {{"term": "término", "definition": "definición exacta del autor, no Wikipedia", "source": "de dónde en el texto"}}
  ],
  "importance_hierarchy": {{
    "level_a": ["idea o concepto fundamental — las 3 cosas que no puedes olvidar"],
    "level_b": ["idea importante pero secundaria"],
    "level_c": ["detalle o contexto complementario"]
  }},
  "evolution": [
    {{"stage": "inicio|desarrollo|punto de quiebre|resolución", "description": "qué ocurre o cómo cambia el argumento/personaje en esta etapa"}}
  ],
  "real_questions": [
    "pregunta concreta y humana que el libro intenta responder (no el tema, la pregunta)"
  ],
  "textual_evidence": [
    {{"concept": "a qué concepto pertenece", "fragment": "fragmento textual exacto del libro", "location": "capítulo/sección/contexto aproximado"}}
  ],
  "supporting_elements": [
    {{"type": "norma|caso|herramienta|evidencia|ejercicio", "name": "nombre", "detail": "detalle relevante"}}
  ],
  "what_gets_missed": [
    "detalle importante que los lectores suelen pasar por alto"
  ]
}}

TEXTO DEL LIBRO:
{text[:60000]}"""

    try:
        return _gpt(client, prompt, max_tokens=4000)
    except Exception as e:
        print(f"⚠ Paso 1 falló: {e}")
        return {}

# ─── PASO 2: TEMAS Y CONFLICTOS ──────────────────────────────────────────────

def _step2_themes(text: str, content_type: str, facts: dict, client) -> dict:
    """
    Extrae los temas profundos: conflictos centrales, preguntas sin respuesta,
    tensiones filosóficas, debates que genera.
    """
    facts_summary = json.dumps(facts, ensure_ascii=False)[:3000]

    prompt = f"""A partir de los hechos extraídos de este libro, identifica los conflictos y tensiones profundas.

HECHOS DEL LIBRO:
{facts_summary}

Analiza:

1. CONFLICTO CENTRAL DEL LIBRO:
   ¿Cuál es la tensión fundamental que el libro intenta resolver o explorar?
   No el tema (ej: "la muerte") sino el conflicto (ej: "la sociedad juzga a las personas por
   cómo expresan sus emociones, no por sus acciones reales").

2. LA PREGUNTA QUE EL LIBRO REALMENTE HACE:
   No la pregunta académica. La pregunta humana.
   Ej: No "¿qué es el absurdo?" sino "¿cómo vivir cuando nada parece tener sentido?"

3. LA IDEA QUE MÁS INCOMODA:
   La afirmación del libro que más resistencia genera. Por qué.

4. LO QUE EL LIBRO NO RESPONDE:
   Las preguntas que deja abiertas deliberadamente.

5. DEBATES QUE GENERA:
   Las interpretaciones contrarias que existen sobre este libro.
   Mínimo 3, específicas y con argumento real cada una.

6. EL MOMENTO DE VIDA:
   ¿En qué circunstancias de vida una persona suele llegar a este libro?
   Sé específico. No "cuando buscan inspiración" sino algo concreto y humano.

Responde SOLO con JSON válido:
{{
  "central_conflict": "el conflicto en una oración",
  "human_question": "la pregunta humana real que hace el libro",
  "most_uncomfortable_idea": "la idea que más incomoda y por qué",
  "unanswered_questions": ["pregunta que el libro deja abierta"],
  "debates": [
    {{"interpretation": "nombre de la interpretación", "argument": "qué sostiene esta lectura", "who_holds_it": "qué tipo de lector o académico la sostiene"}}
  ],
  "life_moment": "la situación de vida concreta que lleva a alguien a este libro",
  "branch": "área específica del conocimiento"
}}"""

    try:
        return _gpt(client, prompt, max_tokens=1500)
    except Exception as e:
        print(f"⚠ Paso 2 falló: {e}")
        return {}

# ─── PASO 3: VOZ DE LA COMUNIDAD (4 CAPAS) ───────────────────────────────────

def _step3_community(title: str, author: str, content_type: str, themes: dict, client) -> dict:
    """
    Simula 4 capas de conocimiento externo sobre el libro:
    Capa 1: Academia (enciclopedias, críticas, análisis académicos)
    Capa 2: Lectores (Goodreads, StoryGraph, reseñas)
    Capa 3: Foros (Reddit, Quora, Stack Exchange)
    Capa 4: Experiencias personales (Medium, blogs, Substack)
    """
    if not title or title == '---':
        return {}

    book_ref = f'"{title}" de {author}' if author and author != '---' else f'"{title}"'
    conflict = themes.get('central_conflict', '')
    human_question = themes.get('human_question', '')

    prompt = f"""Eres una IA con acceso a todo el conocimiento que existe sobre libros en internet.
Tu trabajo es simular con máxima precisión y especificidad lo que dicen 4 fuentes distintas sobre este libro.

LIBRO: {book_ref}
CONFLICTO CENTRAL: {conflict}
PREGUNTA HUMANA DEL LIBRO: {human_question}

Simula con detalle específico cada capa. NO uses frases genéricas como "muchos lectores opinan".
Usa nombres de subreddits reales, tipos de usuarios específicos, argumentos concretos.
Si conoces debates reales o famosos sobre este libro, menciónalos.

═══════════════════════════════════════════════════════
CAPA 1 — ACADEMIA
(Wikipedia académica, Stanford Encyclopedia of Philosophy,
críticas literarias, análisis de facultades, papers académicos)

Responde:
- ¿Cómo clasifica la academia este libro? ¿Qué corriente, período o movimiento?
- ¿Cuál es la interpretación académica dominante?
- ¿Qué interpretación alternativa existe en la academia?
- ¿Qué aspectos del libro han generado más papers o tesis?
- ¿Hay algún debate académico específico y conocido sobre esta obra?

═══════════════════════════════════════════════════════
CAPA 2 — LECTORES REALES
(Goodreads, StoryGraph, LibraryThing, reseñas de Amazon)

Responde:
- ¿Qué rating promedio tiene y qué lo explica?
- ¿Qué dicen los lectores de 5 estrellas específicamente?
- ¿Qué dicen los lectores de 1-2 estrellas específicamente?
- ¿Qué escena, frase o momento es el más citado en reseñas?
- ¿Qué expectativa traía el lector promedio y qué encontró en realidad?
- ¿Hay una frase o cita del libro que aparece en miles de reseñas?

═══════════════════════════════════════════════════════
CAPA 3 — FOROS Y DEBATES
(Reddit r/books r/law r/philosophy r/learnprogramming, Quora, Stack Exchange)

Responde:
- ¿Cuál es el thread o debate más recurrente sobre este libro en Reddit?
- ¿Qué pregunta hace la gente en Quora sobre este libro?
- ¿Hay alguna interpretación "controversial" que divide a los lectores?
- ¿Qué defienden los fans más acérrimos?
- ¿Qué critican los detractores con más fuerza?

═══════════════════════════════════════════════════════
CAPA 4 — EXPERIENCIAS PERSONALES
(Medium, Substack, blogs personales, comentarios de YouTube)

Responde:
- ¿Qué tipo de experiencia personal comparte la gente al hablar de este libro?
- ¿En qué momento de vida suele llegar la gente a este libro?
- ¿Qué cambio concreto dice la gente que produjo en su forma de pensar?
- ¿Hay alguna historia de "este libro cambió mi vida" recurrente?
- ¿Qué idea del libro aparece más en ensayos personales?

Responde SOLO con JSON válido:
{{
  "academic_layer": {{
    "classification": "cómo clasifica la academia este libro",
    "dominant_interpretation": "interpretación académica dominante",
    "alternative_interpretation": "interpretación académica alternativa",
    "most_studied_aspects": ["aspecto que más genera papers o análisis académicos"],
    "known_academic_debate": "debate académico específico y conocido si existe"
  }},
  "readers_layer": {{
    "avg_rating_context": "rating aproximado y qué lo explica",
    "five_star_says": "qué dicen específicamente los fans",
    "one_star_says": "qué dicen específicamente los detractores",
    "most_cited_moment": "escena, frase o momento más citado en reseñas",
    "expectation_vs_reality": "qué esperaba el lector promedio vs qué encontró",
    "viral_quote": "frase del libro que aparece en miles de reseñas si existe"
  }},
  "forums_layer": {{
    "recurring_reddit_debate": "debate más recurrente en Reddit sobre este libro",
    "common_quora_question": "pregunta más frecuente en Quora",
    "controversial_interpretation": "interpretación que más divide a los lectores",
    "defenders_argue": "qué defienden los fans más acérrimos",
    "critics_argue": "qué critican los detractores con más fuerza"
  }},
  "personal_layer": {{
    "life_moment": "en qué momento de vida llega la gente a este libro",
    "reported_change": "qué cambio concreto dice la gente que produjo en su forma de pensar",
    "recurring_personal_story": "historia de impacto personal recurrente si existe",
    "most_cited_idea_in_essays": "idea del libro que más aparece en ensayos personales"
  }},
  "synthesis": {{
    "most_cited_moment": "el momento más memorable para la comunidad en general",
    "common_misconception": "el malentendido más frecuente sobre este libro",
    "community_debate": "el debate más importante que genera en la comunidad",
    "what_nobody_tells_you": "lo que nadie te dice sobre este libro antes de leerlo"
  }}
}}"""

    try:
        return _gpt(client, prompt, max_tokens=2500)
    except Exception as e:
        print(f"⚠ Paso 3 falló: {e}")
        return {}

# ─── PASO 4: SÍNTESIS FINAL ──────────────────────────────────────────────────

def _step4_synthesis(
    text: str, content_type: str, pages: int,
    facts: dict, themes: dict, community: dict,
    profile_instructions: str, client
) -> dict:
    """
    Sintetiza todo en el análisis final.
    Conecta: conflicto del libro + voz de la comunidad + conflicto del lector.
    """
    ctype_label = CONTENT_TYPES[content_type]['label']

    # Construir contexto comprimido de los pasos anteriores
    facts_block = json.dumps({
        'title': facts.get('title','---'),
        'author': facts.get('author','---'),
        'year': facts.get('year','---'),
        'structure': facts.get('structure',[])[:6],
        'what_gets_missed': facts.get('what_gets_missed',[]),
    }, ensure_ascii=False)

    themes_block = json.dumps(themes, ensure_ascii=False)
    
    # Inyectar las 4 capas de comunidad con estructura clara
    if community:
        community_block = f"""
CAPA 1 — ACADEMIA:
{json.dumps(community.get('academic_layer', {}), ensure_ascii=False)}

CAPA 2 — LECTORES REALES (Goodreads/StoryGraph):
{json.dumps(community.get('readers_layer', {}), ensure_ascii=False)}

CAPA 3 — FOROS (Reddit/Quora):
{json.dumps(community.get('forums_layer', {}), ensure_ascii=False)}

CAPA 4 — EXPERIENCIAS PERSONALES (Medium/blogs):
{json.dumps(community.get('personal_layer', {}), ensure_ascii=False)}

SÍNTESIS COMUNITARIA:
{json.dumps(community.get('synthesis', {}), ensure_ascii=False)}"""
    else:
        community_block = '{}'

    reader_block = ''
    if profile_instructions:
        reader_block = f"""
╔══════════════════════════════════════════════════════════╗
  QUIÉN ES EL LECTOR — Esto cambia TODO el análisis
╚══════════════════════════════════════════════════════════╝
{profile_instructions}

ALGORITMO CENTRAL:
Conflicto del lector + Conflicto del libro = Interpretación que solo existe para esta persona.

Identifica:
1. ¿Cuál es el conflicto actual de este lector que resuena con el libro?
2. ¿Qué va a encontrar que no esperaba?
3. ¿Dónde va a estar de acuerdo y dónde va a chocar?
4. ¿Qué parte del libro lo va a incomodar más?
5. ¿Qué frase o idea del libro probablemente le quede dando vueltas?
═══════════════════════════════════════════════════════════
"""

    # Construir instrucciones específicas por tipo para la síntesis
    synthesis_instructions = {
        'philosophy': """
MODO ESTUDIO — key_concepts (mínimo 12):
  Cada concepto: término exacto del autor, definición según el texto (no Wikipedia),
  qué problema resuelve dentro del sistema del autor, cómo se conecta con otros conceptos.
  Muestra la cadena: de qué premisa a qué conclusión.

MODO MENTOR — summary:
  Estructura así (no como un párrafo plano):
  - El conflicto central del libro en 1-2 oraciones directas
  - Por qué llegó a ser importante para millones (específico, no genérico)
  - Lo que la mayoría no nota (usa what_gets_missed y community si están disponibles)
  - Si hay perfil del lector: qué va a encontrar esta persona específicamente

exam_questions (10): Que obliguen a tomar posición propia, no a describir al autor.
""",
        'legal': """
MODO ESTUDIO — key_concepts (mínimo 12):
  Definición doctrinal rigurosa, fuente normativa o jurisprudencial,
  aplicación práctica real, debates que genera en la doctrina.
  Mostrar encadenamiento: de qué principio a qué consecuencia jurídica.

supporting_elements → norms y jurisprudence: con identificación exacta y ratio decidendi real.

MODO MENTOR — summary:
  - El problema jurídico real que aborda (no el título)
  - Por qué importa en la práctica (caso real o situación concreta)
  - Lo que los estudiantes suelen pasar por alto (what_gets_missed)
  - El debate doctrinal real que genera
  - Si hay perfil del lector: conexión con su área específica

exam_questions (10): Análisis de casos hipotéticos, no memorización de normas.
""",
        'tech': """
MODO ESTUDIO — key_concepts (mínimo 10):
  Qué es, para qué sirve, ejemplo de uso real, cuándo NO usar, alternativas.
  Progresión de lo más básico a lo más avanzado.

tools_frameworks: Con casos de uso reales, limitaciones honestas, cuándo preferir alternativas.

MODO MENTOR — summary:
  - Qué problema real resuelve este conocimiento
  - Por qué importa aprenderlo ahora (contexto del mercado/industria)
  - Lo que los tutoriales suelen omitir (what_gets_missed + community)
  - Si hay perfil del lector: conexión con lo que está construyendo

exam_questions (10): Problemas reales que un dev encontraría en producción.
""",
        'data_science': """
MODO ESTUDIO — key_concepts (mínimo 10):
  Definición técnica, intuición matemática accesible, caso de uso real, cuándo falla.
  Progresión lógica de conceptos.

tools_frameworks: Con trade-offs reales de la industria.

MODO MENTOR — summary:
  - Qué problema de datos/ML resuelve este libro
  - Lo que los cursos de YouTube no enseñan (what_gets_missed)
  - Lo que dice la comunidad (Kaggle, r/ML) sobre este libro
  - Si hay perfil del lector: conexión con sus proyectos

exam_questions (10): Decisiones de modelado reales con trade-offs.
""",
        'personal': """
MODO ESTUDIO — key_concepts (mínimo 8):
  La afirmación real del autor (puede ser polémica), la evidencia que usa,
  cuándo funciona y cuándo no. Cadena de ideas del libro.

action_items: Concretos y con contexto real de cuándo aplicarlos.

MODO MENTOR — summary:
  - La promesa real del libro (no la del título)
  - La idea que más incomoda y por qué
  - Lo que la gente ama y lo que critica (usa community)
  - Si hay perfil del lector: qué va a resonar y qué va a chocar

exam_questions (10): Preguntas que cuestionen creencias propias.
""",
        'article': """
key_concepts (5-10): El argumento real con su lógica interna y su punto más débil.
norms: Fuentes citadas y cómo las usa el autor (¿fielmente o selectivamente?).
summary: El argumento real, la evidencia, los límites y los debates que genera.
exam_questions (5): Análisis crítico de los argumentos, no descripción.
""",
    }

    synth_inst = synthesis_instructions.get(content_type, synthesis_instructions['personal'])

    prompt = f"""Eres un intérprete intelectual de élite. Tienes 4 fuentes de información:

1. LOS HECHOS DEL LIBRO (extraídos en Paso 1):
{facts_block}

2. LOS CONFLICTOS Y TEMAS PROFUNDOS (extraídos en Paso 2):
{themes_block}

3. LO QUE DICE LA COMUNIDAD REAL (Reddit, Goodreads, Medium — Paso 3):
{community_block}

{reader_block}

Tu trabajo: sintetizar todo en el análisis final.

LA DIFERENCIA QUE IMPORTA:
✗ "Meursault es el hombre absurdo que vive sin ilusiones."
✓ "Meursault no es juzgado por matar. Es juzgado por no llorar.
   El tribunal usa el funeral como prueba moral. Eso es lo que escandaliza a la sociedad —
   no el crimen, sino la negativa a fingir emociones que no siente.
   Y esa es exactamente la pregunta que Camus quiere que te lleves: ¿nos juzgan por lo que hacemos
   o por lo que los demás esperan que sintamos?"

Tipo de contenido: {ctype_label}

{synth_inst}

Responde SOLO con JSON válido:
{{
  "title": "{facts.get('title','---')}",
  "author": "{facts.get('author','---')}",
  "year": "{facts.get('year','---')}",
  "branch": "área específica y precisa",
  "content_type": "{content_type}",

  "summary": "Interpretación profunda — NO resumen. Ver instrucciones de MODO MENTOR arriba.",

  "author_thesis": "La tesis exacta que el autor intenta demostrar — en 2-3 oraciones directas. No el tema: la afirmación.",

  "transformative_ideas": [
    {{"idea": "idea concreta que puede cambiar la forma de ver el mundo", "why": "por qué esta idea específicamente transforma al lector"}}
  ],

  "importance_hierarchy": {{
    "level_a": ["si solo recuerdas 3 cosas de este libro, son estas"],
    "level_b": ["importante pero secundario"],
    "level_c": ["detalle o contexto complementario"]
  }},

  "character_profiles": [
    {{
      "name": "nombre del personaje/autor/figura central",
      "motivations": "qué lo mueve realmente",
      "fear": "qué evita o teme",
      "evolution": "cómo cambia a lo largo del libro — inicio → final",
      "key_insight": "la idea más importante que representa este personaje"
    }}
  ],

  "debatable_ideas": [
    {{"idea": "afirmación polémica o discutible del libro", "pro": "argumento a favor", "contra": "argumento en contra"}}
  ],

  "impact_by_profile": [
    {{"profile": "abogado|estudiante de derecho|filósofo|psicólogo|etc", "specific_impact": "qué encuentra específicamente valioso este perfil y por qué"}}
  ],

  "real_questions": [
    "pregunta humana concreta que el libro intenta responder"
  ],

  "why_this_book_matters": [
    {{"profile": "momento de vida específico", "insight": "qué encuentra ahí que no esperaba — específico y humano"}}
  ],

  "what_community_says": {{
    "most_cited_moment": "...",
    "common_misconception": "...",
    "community_debate": "..."
  }},

  "concept_map": [
    {{"from": "concepto A", "to": "concepto B", "relation": "cómo se conectan causalmente en el argumento del autor"}}
  ],

  "debate_suggestion": {{
    "natural_opponent": "pensador/autor/enfoque que contradice directamente",
    "natural_ally": "pensador/autor/enfoque que resuena",
    "central_tension": "la tensión en una oración",
    "why": "por qué ese debate específico es revelador",
    "reader_position": "dónde se ubicaría probablemente este lector (solo si hay perfil)"
  }},

  "key_concepts": [
    {{"term": "...", "definition": "definición del autor, no Wikipedia", "context": "cómo se conecta con otros conceptos del libro"}}
  ],

  "norms": [{{"norm": "...", "content": "...", "relevance": "..."}}],
  "jurisprudence": [{{"case": "...", "court": "...", "contribution": "..."}}],
  "tools_frameworks": [{{"name": "...", "purpose": "...", "when_to_use": "..."}}],
  "action_items": [{{"action": "...", "context": "...", "benefit": "..."}}],
  "exam_questions": [{{"question": "...", "hint": "..."}}],
  "chapter_map": [{{"chapter": "...", "topics": ["..."]}}]
}}
"""

    result = _gpt(client, prompt, max_tokens=6000, temperature=0.4)

    # Garantizar campos presentes
    result['pages'] = pages
    for f in ['key_concepts','norms','jurisprudence','tools_frameworks','action_items',
              'exam_questions','chapter_map','why_this_book_matters','concept_map',
              'transformative_ideas','character_profiles','debatable_ideas',
              'impact_by_profile','real_questions']:
        if f not in result:
            result[f] = []
    for f in ['debate_suggestion','what_community_says','importance_hierarchy']:
        if f not in result:
            result[f] = {}

    # Si community tiene estructura de 4 capas, enriquecer what_community_says
    if community and 'synthesis' in community:
        s = community['synthesis']
        if not result.get('what_community_says') or not result['what_community_says'].get('most_cited_moment'):
            result['what_community_says'] = {
                'most_cited_moment': s.get('most_cited_moment', ''),
                'common_misconception': s.get('common_misconception', ''),
                'community_debate': s.get('community_debate', ''),
                'what_nobody_tells_you': s.get('what_nobody_tells_you', '')
            }
        result['community_layers'] = {
            'academic': community.get('academic_layer', {}),
            'readers': community.get('readers_layer', {}),
            'forums': community.get('forums_layer', {}),
            'personal': community.get('personal_layer', {})
        }
    if 'author_thesis' not in result:
        result['author_thesis'] = ''

    return result


# ─── PROCESO COMPLETO ─────────────────────────────────────────────────────────

def process_source(source_type, filepath_or_url, api_key, profile_instructions=''):
    # Extraer texto
    if source_type == 'pdf':
        text, pages = extract_from_pdf(filepath_or_url)
    elif source_type == 'image':
        text, pages = extract_from_image(filepath_or_url, api_key)
    elif source_type == 'url':
        text, pages = extract_from_url(filepath_or_url, api_key)
    elif source_type == 'epub':
        text, pages = extract_from_epub(filepath_or_url)
    elif source_type == 'docx':
        text, pages = extract_from_docx(filepath_or_url)
    else:
        raise ValueError(f"Tipo de fuente desconocido: {source_type}")

    if len(text.strip()) < 80:
        raise ValueError("No se pudo extraer suficiente texto del contenido.")

    client = OpenAI(api_key=api_key)

    print("📖 Paso 1: Extrayendo hechos...")
    content_type = detect_content_type(text, api_key)
    facts = _step1_facts(text, content_type, client)

    print("🧠 Paso 2: Analizando conflictos y temas...")
    themes = _step2_themes(text, content_type, facts, client)

    print("👥 Paso 3: Consultando voz de la comunidad...")
    title = facts.get('title', '---')
    author = facts.get('author', '---')
    community = _step3_community(title, author, content_type, themes, client)

    print("✨ Paso 4: Sintetizando con perfil del lector...")
    result = _step4_synthesis(
        text, content_type, pages,
        facts, themes, community,
        profile_instructions, client
    )

    result['source_type'] = source_type
    print(f"✅ Análisis completo: {result.get('title','---')}")
    return result


# ─── FUNCIÓN LEGACY para compatibilidad ──────────────────────────────────────
def analyze_content(text, pages, content_type_key, api_key, profile_instructions=''):
    """Mantiene compatibilidad con llamadas directas."""
    client = OpenAI(api_key=api_key)
    facts = _step1_facts(text, content_type_key, client)
    themes = _step2_themes(text, content_type_key, facts, client)
    community = _step3_community(
        facts.get('title',''), facts.get('author',''), content_type_key, themes, client
    )
    return _step4_synthesis(text, content_type_key, pages, facts, themes, community, profile_instructions, client)