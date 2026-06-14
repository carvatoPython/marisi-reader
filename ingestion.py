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
        'extra_prompt': '''Extrae:
- key_concepts: mínimo 8, máximo 20 conceptos jurídicos clave con definición y contexto
- norms: TODAS las leyes, decretos, artículos, códigos citados
- jurisprudence: TODOS los fallos, sentencias, autos mencionados ([] si ninguno)
- exam_questions: exactamente 10 preguntas tipo parcial universitario con pista
- chapter_map: estructura por capítulos con temas'''
    },
    'tech': {
        'label': 'Tecnología / Programación',
        'fields': ['key_concepts','tools_frameworks','exam_questions','chapter_map'],
        'extra_prompt': '''Extrae:
- key_concepts: mínimo 8 conceptos técnicos clave con definición clara y ejemplo de uso
- tools_frameworks: herramientas, lenguajes, librerías, frameworks mencionados con para qué sirven
- exam_questions: 10 preguntas/ejercicios prácticos que refuercen el aprendizaje
- chapter_map: estructura del libro con temas por capítulo'''
    },
    'data_science': {
        'label': 'Data Science / IA / ML',
        'fields': ['key_concepts','tools_frameworks','exam_questions','chapter_map'],
        'extra_prompt': '''Extrae:
- key_concepts: mínimo 8 conceptos de data science / ML / estadística con definición y uso práctico
- tools_frameworks: librerías (pandas, sklearn, etc.), algoritmos, técnicas y cuándo usarlos
- exam_questions: 10 preguntas/problemas prácticos incluyendo casos de análisis
- chapter_map: estructura del libro con temas por capítulo'''
    },
    'personal': {
        'label': 'Desarrollo personal / Negocios',
        'fields': ['key_concepts','action_items','exam_questions','chapter_map'],
        'extra_prompt': '''Extrae:
- key_concepts: mínimo 8 ideas, principios o conceptos clave del libro con explicación
- action_items: acciones concretas, ejercicios o cambios de hábitos que propone el libro
- exam_questions: 10 preguntas de reflexión que ayuden a interiorizar el contenido
- chapter_map: estructura del libro con los temas de cada capítulo'''
    },
    'article': {
        'label': 'Artículo / Ensayo / Paper',
        'fields': ['key_concepts','norms','exam_questions'],
        'extra_prompt': '''Extrae:
- key_concepts: los 5-10 argumentos o conceptos centrales del artículo
- norms: fuentes, autores citados, datos estadísticos mencionados ([] si no hay)
- exam_questions: 5 preguntas de análisis crítico del artículo'''
    }
}

def detect_content_type(text, api_key):
    client = OpenAI(api_key=api_key)
    snippet = text[:3000]
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":f"""Clasifica este texto en UNA de estas categorías y responde SOLO con la clave:
- legal (derecho, jurídico, leyes, códigos, jurisprudencia)
- tech (programación, software, sistemas, ingeniería de software)
- data_science (machine learning, IA, estadística, datos, python para análisis)
- personal (desarrollo personal, negocios, emprendimiento, psicología popular, finanzas personales)
- article (artículo académico, ensayo, paper, nota de prensa)

TEXTO:
{snippet}

Responde SOLO con una de las claves: legal, tech, data_science, personal, article"""}],
        temperature=0, max_tokens=10
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
        if t:
            texts.append(t)
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

    profile_section = f"\nPERFIL DEL USUARIO (adapta tu análisis a esto):\n{profile_instructions}\n" if profile_instructions else ''

    prompt = f"""Eres un asistente de estudio experto. Analiza el siguiente contenido de tipo "{ctype['label']}" y responde SOLO con JSON válido.
{profile_section}
Estructura JSON requerida:
{{
  "title": "Título del contenido",
  "author": "Autor(es) o '---'",
  "year": "Año o '---'",
  "branch": "Área específica (ej: Derecho Civil, Machine Learning, Productividad, etc.)",
  "content_type": "{content_type_key}",
  "summary": "Resumen ejecutivo en 4-6 oraciones adaptado al perfil del usuario.",
  {json.dumps(fields_template, ensure_ascii=False)[1:-1]}
}}

{ctype['extra_prompt']}

Responde SOLO el JSON, nada más.

CONTENIDO:
{text}
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0.2, max_tokens=4000
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