import os, json, re, base64
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import pdfplumber

MAX_CHARS = 80000

CONTENT_TYPES = {
    'legal': {
        'label': 'Jurídico / Derecho',
        'fields': ['key_concepts','norms','jurisprudence','exam_questions','chapter_map'],
        'extra_prompt': '''Extrae con profundidad:
- key_concepts: mínimo 8, máximo 20 conceptos jurídicos clave. Para cada uno: término, definición rigurosa, contexto de aplicación real
- norms: TODAS las leyes, decretos, artículos, códigos citados con su contenido relevante
- jurisprudence: TODOS los fallos, sentencias, autos mencionados con su aporte doctrinal
- exam_questions: exactamente 10 preguntas tipo parcial universitario que requieran análisis, no memorización
- chapter_map: estructura por capítulos con los temas y subtemas reales'''
    },
    'tech': {
        'label': 'Tecnología / Programación',
        'fields': ['key_concepts','tools_frameworks','exam_questions','chapter_map'],
        'extra_prompt': '''Extrae con profundidad:
- key_concepts: mínimo 8 conceptos técnicos con definición clara, ejemplo de uso real y por qué importa
- tools_frameworks: herramientas, lenguajes, librerías con para qué sirven, cuándo usarlos y alternativas
- exam_questions: 10 preguntas/ejercicios prácticos que obliguen a aplicar el conocimiento
- chapter_map: estructura real del libro con temas por capítulo'''
    },
    'data_science': {
        'label': 'Data Science / IA / ML',
        'fields': ['key_concepts','tools_frameworks','exam_questions','chapter_map'],
        'extra_prompt': '''Extrae con profundidad:
- key_concepts: mínimo 8 conceptos de ML/estadística con definición, intuición matemática y caso de uso
- tools_frameworks: librerías, algoritmos, técnicas con cuándo usarlos y sus limitaciones
- exam_questions: 10 problemas prácticos que incluyan casos de análisis y decisiones de modelado
- chapter_map: estructura real del libro'''
    },
    'personal': {
        'label': 'Desarrollo personal / Negocios',
        'fields': ['key_concepts','action_items','exam_questions','chapter_map'],
        'extra_prompt': '''Extrae con profundidad:
- key_concepts: mínimo 8 ideas o principios centrales con su argumento real y por qué el autor lo sostiene
- action_items: acciones concretas y específicas que propone el libro, con contexto de cuándo aplicarlas
- exam_questions: 10 preguntas de reflexión profunda que obliguen a cuestionar creencias propias
- chapter_map: estructura real del libro'''
    },
    'philosophy': {
        'label': 'Filosofía / Pensamiento',
        'fields': ['key_concepts','norms','exam_questions','chapter_map'],
        'extra_prompt': '''Extrae con profundidad filosófica real:
- key_concepts: mínimo 10 conceptos filosóficos centrales. Para cada uno: el término exacto del autor,
  la definición precisa según el texto (no Wikipedia), el problema que resuelve o plantea, y cómo se
  relaciona con otros conceptos del libro
- norms: autores, obras y corrientes filosóficas que el autor cita, critica o con las que dialoga.
  Incluye la posición del autor frente a cada uno
- exam_questions: 10 preguntas que obliguen a tomar posición filosófica propia y argumentarla,
  no solo describir el pensamiento del autor
- chapter_map: estructura real de la obra con los argumentos principales de cada sección'''
    },
    'article': {
        'label': 'Artículo / Ensayo / Paper',
        'fields': ['key_concepts','norms','exam_questions'],
        'extra_prompt': '''Extrae con profundidad analítica:
- key_concepts: los 5-10 argumentos o tesis centrales con la evidencia o razones que usa el autor
- norms: fuentes citadas, datos estadísticos, autores mencionados y cómo los usa el autor
- exam_questions: 5 preguntas de análisis crítico que obliguen a evaluar los argumentos'''
    }
}

def detect_content_type(text, api_key):
    client = OpenAI(api_key=api_key)
    snippet = text[:3000]
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":f"""Clasifica este texto en UNA de estas categorías y responde SOLO con la clave:
- legal (derecho, jurídico, leyes, códigos, jurisprudencia, constitucional)
- tech (programación, software, sistemas, ingeniería de software, DevOps)
- data_science (machine learning, IA, estadística, datos, python para análisis)
- philosophy (filosofía, pensamiento crítico, ensayo filosófico, ética, metafísica, existencialismo, fenomenología)
- personal (desarrollo personal, negocios, emprendimiento, psicología popular, finanzas personales, autoayuda)
- article (artículo académico, paper científico, ensayo corto, nota periodística de análisis)

TEXTO:
{snippet}

Responde SOLO con una de las claves: legal, tech, data_science, philosophy, personal, article"""}],
        temperature=0, max_tokens=15
    )
    detected = response.choices[0].message.content.strip().lower()
    return detected if detected in CONTENT_TYPES else 'personal'

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
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role":"user","content":[
            {"type":"image_url","image_url":{"url":f"data:image/{mime};base64,{b64}"}},
            {"type":"text","text":"Transcribe TODO el texto que aparece en esta imagen de forma completa y ordenada. Incluye títulos, párrafos, listas, tablas. Solo el texto, sin comentarios."}
        ]}],
        max_tokens=4000
    )
    return response.choices[0].message.content.strip(), 1

def extract_from_url(url, api_key):
    headers = {'User-Agent':'Mozilla/5.0 (compatible; MarisiReader/2.0)'}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        for tag in soup(['script','style','nav','footer','header','aside','ads']):
            tag.decompose()
        text = soup.get_text(separator='\n', strip=True)
        lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 30]
        clean = '\n'.join(lines)[:MAX_CHARS]
        return clean, 1
    except Exception as e:
        raise ValueError(f"No se pudo acceder a la URL: {str(e)}")

def extract_from_epub(filepath):
    try:
        import ebooklib  # type: ignore[import]
        from ebooklib import epub  # type: ignore[import]
    except ImportError:
        raise ValueError("EbookLib no está instalado. Verifica requirements.txt")
    book_epub = epub.read_epub(filepath)
    texts = []
    for item in book_epub.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), 'html.parser')
        t = soup.get_text(separator='\n', strip=True)
        if t: texts.append(t)
    full_text = '\n'.join(texts)[:MAX_CHARS]
    pages = max(1, len(full_text.split()) // 250)
    return full_text, pages

def extract_from_docx(filepath):
    try:
        from docx import Document  # type: ignore[import]
    except ImportError:
        raise ValueError("python-docx no está instalado. Verifica requirements.txt")
    doc = Document(filepath)
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    full_text = '\n'.join(paragraphs)[:MAX_CHARS]
    pages = max(1, len(full_text.split()) // 250)
    return full_text, pages

def _build_reader_context(profile_instructions: str) -> str:
    """Convierte las instrucciones de perfil en un bloque de contexto para el prompt."""
    if not profile_instructions:
        return ''
    return f"""
═══════════════════════════════════════════════════════
PERFIL DEL LECTOR — Lee esto con atención antes de analizar
═══════════════════════════════════════════════════════
{profile_instructions}

INSTRUCCIÓN CRÍTICA: Este análisis es para esta persona específica, no para un estudiante genérico.
El resumen debe hablarle directamente. Usa "tú" cuando sea apropiado.
Conecta los conceptos con su perfil, sus valores y sus tensiones intelectuales detectadas.
Si el libro toca temas que claramente resuenan o contradicen su forma de pensar, señálalo.
═══════════════════════════════════════════════════════
"""

def analyze_content(text, pages, content_type_key, api_key, profile_instructions=''):
    client = OpenAI(api_key=api_key)
    ctype = CONTENT_TYPES[content_type_key]

    fields_template = {}
    if 'key_concepts' in ctype['fields']:
        fields_template['key_concepts'] = [{"term":"...","definition":"...","context":"..."}]
    if 'norms' in ctype['fields']:
        fields_template['norms'] = [{"norm":"...","content":"...","relevance":"..."}]
    if 'jurisprudence' in ctype['fields']:
        fields_template['jurisprudence'] = [{"case":"...","court":"...","contribution":"..."}]
    if 'tools_frameworks' in ctype['fields']:
        fields_template['tools_frameworks'] = [{"name":"...","purpose":"...","when_to_use":"..."}]
    if 'action_items' in ctype['fields']:
        fields_template['action_items'] = [{"action":"...","context":"...","benefit":"..."}]
    if 'exam_questions' in ctype['fields']:
        fields_template['exam_questions'] = [{"question":"...","hint":"..."}]
    if 'chapter_map' in ctype['fields']:
        fields_template['chapter_map'] = [{"chapter":"...","topics":["..."]}]

    reader_context = _build_reader_context(profile_instructions)

    prompt = f"""Eres un tutor intelectual de élite que analiza libros de forma profunda y personalizada.
{reader_context}
Analiza el siguiente contenido de tipo "{ctype['label']}" y responde SOLO con JSON válido.

Estructura JSON requerida:
{{
  "title": "Título exacto del contenido",
  "author": "Autor(es) o '---'",
  "year": "Año de publicación o '---'",
  "branch": "Área específica y precisa (ej: Filosofía existencialista, Derecho Civil Colombiano, Machine Learning supervisado)",
  "content_type": "{content_type_key}",
  "summary": "RESUMEN PERSONALIZADO: 5-7 oraciones. NO es un resumen de Wikipedia. Es una lectura de este libro pensando en este lector específico. Conecta la tesis central del libro con lo que sabes del lector. ¿Por qué este libro importa para esta persona en este momento? ¿Qué le va a remover? ¿Dónde va a estar de acuerdo y dónde va a chocar? Si no hay perfil del lector, escribe el resumen más honesto y directo posible sobre lo que realmente dice el libro, no un resumen escolar.",
  "debate_suggestion": {{
    "natural_opponent": "El pensador o autor que más interesantemente contrastaría con este libro",
    "why": "Por qué ese debate específico sería revelador",
    "natural_ally": "El pensador o autor que más resonaría con este libro",
    "central_tension": "La tensión filosófica/intelectual central que define el libro en una oración"
  }},
  {json.dumps(fields_template, ensure_ascii=False)[1:-1]}
}}

{ctype['extra_prompt']}

IMPORTANTE SOBRE LA CALIDAD:
- El resumen debe tener alma. Debe sonar como alguien que realmente leyó el libro y lo pensó para este lector.
- Los conceptos clave deben ir más allá de definiciones de diccionario. Explica por qué cada concepto importa y qué problema resuelve.
- Las preguntas de estudio deben obligar a pensar, no a recordar.
- debate_suggestion debe ser específico y fundamentado, no genérico.

Responde SOLO el JSON, nada más.

CONTENIDO DEL LIBRO:
{text}
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0.3,
        max_tokens=4500
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r'^```(?:json)?\s*','',raw)
    raw = re.sub(r'\s*```$','',raw)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Error en respuesta JSON: {str(e)}")
    result['pages'] = pages
    for f in ['key_concepts','norms','jurisprudence','tools_frameworks','action_items','exam_questions','chapter_map']:
        if f not in result:
            result[f] = []
    if 'debate_suggestion' not in result:
        result['debate_suggestion'] = {}
    return result

def process_source(source_type, filepath_or_url, api_key, profile_instructions=''):
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

    content_type_key = detect_content_type(text, api_key)
    result = analyze_content(text, pages, content_type_key, api_key, profile_instructions)
    result['source_type'] = source_type
    return result