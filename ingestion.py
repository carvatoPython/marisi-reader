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
    },
    'tech': {
        'label': 'Tecnología / Programación',
        'fields': ['key_concepts','tools_frameworks','exam_questions','chapter_map'],
    },
    'data_science': {
        'label': 'Data Science / IA / ML',
        'fields': ['key_concepts','tools_frameworks','exam_questions','chapter_map'],
    },
    'philosophy': {
        'label': 'Filosofía / Pensamiento',
        'fields': ['key_concepts','norms','exam_questions','chapter_map'],
    },
    'personal': {
        'label': 'Desarrollo personal / Negocios',
        'fields': ['key_concepts','action_items','exam_questions','chapter_map'],
    },
    'article': {
        'label': 'Artículo / Ensayo / Paper',
        'fields': ['key_concepts','norms','exam_questions'],
    }
}

# Prompts de análisis profundo por tipo
TYPE_ANALYSIS_PROMPTS = {
    'philosophy': """
INSTRUCCIONES PARA FILOSOFÍA — Lee con cuidado:

summary (mínimo 200 palabras, NO es resumen):
  Responde: ¿Cuál es la pregunta HUMANA que le quita el sueño al autor (no la académica)?
  ¿Por qué millones de personas han leído este libro? ¿Qué momento de vida los lleva a él?
  ¿Qué encontraron que no esperaban? ¿Dónde choca el libro con lo que la gente cree?
  Si hay perfil del lector: ¿por qué ESTE libro a ESTA persona en ESTE momento?
  Usa el contexto de foros y lectores reales si está disponible. Habla en segunda persona cuando tengas el perfil.

key_concepts (mínimo 12):
  Para cada concepto: qué entiende el AUTOR (no Wikipedia), qué problema resuelve DENTRO del libro,
  y cómo se conecta con otros conceptos. Muestra la cadena de ideas, no conceptos aislados.
  Incluye las controversias o malentendidos más comunes si los hay.

norms: Todos los autores/obras/corrientes con los que dialoga — y la posición del autor frente a cada uno.

exam_questions (10): Preguntas que obligan a TOMAR POSICIÓN, no a describir.
  "¿Camus tiene razón en que...?" no "¿Qué dice Camus sobre...?"

why_this_book_matters (4 perfiles):
  Por momentos de vida, no por demografía. Específico y humano.
  Usa lo que dicen los lectores reales de Goodreads/Reddit si está disponible.

concept_map: La cadena de ideas del libro. De la premisa inicial a la conclusión.

debate_suggestion:
  natural_opponent, natural_ally, central_tension, why.
  reader_position: dónde se ubica este lector específico en ese debate.
""",
    'legal': """
INSTRUCCIONES PARA DERECHO — Lee con cuidado:

summary (mínimo 180 palabras, NO es resumen):
  ¿Cuál es el problema jurídico real que aborda? ¿Qué controversia doctrinal genera?
  ¿Por qué importa para quien lo estudia o practica?
  ¿Qué diferencia a este libro de los demás sobre el mismo tema?
  Si hay perfil del lector: conecta con su área de estudio/práctica específica.
  Usa debates académicos y de foros jurídicos si están disponibles.

key_concepts (mínimo 12):
  Definición doctrinal rigurosa (no de diccionario), fuente normativa o jurisprudencial,
  y cómo se aplica en la práctica real. Incluye los debates que genera cada concepto.
  Muestra cómo los conceptos se encadenan: de la premisa al argumento central.

norms: TODAS las normas con identificación exacta, contenido y debates que generan.
jurisprudence: Todos los fallos con su ratio decidendi y su impacto doctrinal.

exam_questions (10): Preguntas de análisis jurídico que requieran aplicar conceptos a casos,
  no solo describir normas.

why_this_book_matters (4 perfiles):
  Por momento de carrera o práctica. Ej: "Si estás preparando un litigio sobre X..."

concept_map: Cómo los conceptos jurídicos se encadenan en el argumento del autor.

debate_suggestion:
  natural_opponent: posición doctrinal contraria con autor y argumento específico.
  natural_ally: escuela o autor que comparte la posición.
  central_tension: el debate jurídico real.
""",
    'tech': """
INSTRUCCIONES PARA TECNOLOGÍA — Lee con cuidado:

summary (mínimo 150 palabras, NO es resumen):
  ¿Qué problema real resuelve este conocimiento? ¿Por qué importa aprenderlo ahora?
  ¿Qué debate existe en la comunidad sobre el enfoque del libro?
  ¿Qué dicen los desarrolladores experimentados sobre este libro en Stack Overflow, Reddit, Hacker News?
  Si hay perfil del lector: ¿cómo conecta con lo que está construyendo?

key_concepts (mínimo 10):
  Qué es, para qué sirve, ejemplo concreto de uso real, cuándo NO usarlo, alternativas.
  Muestra cómo los conceptos se encadenan: de lo más básico a lo más avanzado.

tools_frameworks: Con casos de uso reales, limitaciones honestas y cuándo preferir alternativas.
  Incluye lo que dice la comunidad (Reddit, Stack Overflow) sobre cada herramienta.

exam_questions (10): Ejercicios prácticos reales. Problemas que un dev encontraría en producción.

why_this_book_matters (4 perfiles): Por momento de carrera. "Si estás aprendiendo X...", "Si trabajas en Y..."

concept_map: Del concepto más básico al más avanzado, mostrando dependencias.

debate_suggestion:
  natural_opponent: enfoque o tecnología alternativa que contraargumenta.
  central_tension: el debate técnico real de la comunidad.
""",
    'data_science': """
INSTRUCCIONES PARA DATA SCIENCE — Lee con cuidado:

summary (mínimo 150 palabras, NO es resumen):
  ¿Qué problema de datos o ML resuelve? ¿Cuándo necesitas exactamente este conocimiento?
  ¿Qué dice la comunidad (Kaggle, r/MachineLearning, Towards Data Science) sobre este libro?
  ¿Qué críticas honestas le hacen? ¿Qué lo hace mejor o peor que alternativas?

key_concepts (mínimo 10):
  Definición técnica + intuición matemática (sin fórmulas complejas) + caso de uso real +
  cuándo falla o tiene limitaciones. Muestra la progresión lógica de conceptos.

tools_frameworks: Con trade-offs reales. Qué dice la comunidad sobre cada librería/técnica.
exam_questions (10): Problemas reales de modelado que requieran tomar decisiones.
why_this_book_matters (4 perfiles): Por proyecto o nivel de experiencia.
concept_map: Del dato crudo al modelo al deployment.
debate_suggestion: El debate metodológico real en la comunidad.
""",
    'personal': """
INSTRUCCIONES PARA DESARROLLO PERSONAL/NEGOCIOS — Lee con cuidado:

summary (mínimo 150 palabras, NO es resumen):
  ¿Cuál es la promesa REAL del libro (no la del título)?
  ¿Qué idea del libro incomoda más? ¿Cuál resuena de inmediato?
  ¿Qué dicen los lectores de Goodreads/Reddit — por qué lo aman o lo odian?
  ¿Quién debería leerlo y quién probablemente no le saque valor?
  Si hay perfil del lector: conecta con su situación específica.

key_concepts (mínimo 8):
  Qué sostiene el autor REALMENTE (puede contradecir el sentido común).
  Muestra la cadena de ideas: cómo un principio lleva al siguiente.
  Incluye las críticas más honestas que se le hacen a cada idea.

action_items: Concretos y específicos con contexto real de cuándo aplicarlos.
exam_questions (10): Preguntas que cuestionen creencias propias, no que recuerden el libro.
why_this_book_matters (4 perfiles): Por momento de vida. Humano y específico.
concept_map: Cómo los principios del libro se encadenan.
debate_suggestion: El debate real sobre si las ideas del libro funcionan o no.
""",
    'article': """
INSTRUCCIONES PARA ARTÍCULO/ENSAYO:

summary (mínimo 100 palabras):
  ¿Cuál es el argumento real (no el tema)? ¿Qué presupone que el lector va a aceptar?
  ¿Qué evidencia usa y qué tan sólida es?
  ¿Qué respuestas o críticas ha generado en la comunidad académica?

key_concepts (5-10): Con la lógica interna de cada argumento y su punto más débil.
norms: Fuentes usadas y cómo el autor las interpreta (¿fielmente o selectivamente?).
exam_questions (5): De análisis crítico que evalúen los argumentos.
why_this_book_matters (3 perfiles): Contextos en que este artículo importa.
debate_suggestion: La controversia real que genera.
"""
}

def detect_content_type(text, api_key):
    client = OpenAI(api_key=api_key)
    snippet = text[:3000]
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":f"""Clasifica este texto en UNA categoría:
- legal (derecho, jurídico, leyes, códigos, jurisprudencia)
- tech (programación, software, sistemas, ingeniería de software)
- data_science (machine learning, IA, estadística, datos)
- philosophy (filosofía, ensayo filosófico, ética, existencialismo, fenomenología, metafísica)
- personal (desarrollo personal, negocios, emprendimiento, psicología popular, finanzas)
- article (artículo académico, paper, ensayo corto, nota de análisis)

TEXTO:
{snippet}

Responde SOLO con la clave."""}],
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
            {"type":"text","text":"Transcribe TODO el texto de la imagen completa y ordenadamente. Solo el texto."}
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
        for tag in soup(['script','style','nav','footer','header','aside']):
            tag.decompose()
        text = soup.get_text(separator='\n', strip=True)
        lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 30]
        return '\n'.join(lines)[:MAX_CHARS], 1
    except Exception as e:
        raise ValueError(f"No se pudo acceder a la URL: {str(e)}")

def extract_from_epub(filepath):
    try:
        import ebooklib  # type: ignore[import]
        from ebooklib import epub  # type: ignore[import]
    except ImportError:
        raise ValueError("EbookLib no está instalado.")
    book_epub = epub.read_epub(filepath)
    texts = []
    for item in book_epub.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), 'html.parser')
        t = soup.get_text(separator='\n', strip=True)
        if t: texts.append(t)
    full_text = '\n'.join(texts)[:MAX_CHARS]
    return full_text, max(1, len(full_text.split()) // 250)

def extract_from_docx(filepath):
    try:
        from docx import Document  # type: ignore[import]
    except ImportError:
        raise ValueError("python-docx no está instalado.")
    doc = Document(filepath)
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    full_text = '\n'.join(paragraphs)[:MAX_CHARS]
    return full_text, max(1, len(full_text.split()) // 250)


def _quick_detect_title_author(text: str, api_key: str) -> tuple[str, str]:
    """Detecta título y autor del texto antes de hacer el análisis completo."""
    client = OpenAI(api_key=api_key)
    snippet = text[:2000]
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":f"""Del siguiente texto, extrae SOLO el título y autor.
Responde SOLO con JSON: {{"title": "...", "author": "..."}}
Si no puedes detectarlos con certeza, usa "---".

TEXTO:
{snippet}"""}],
            temperature=0, max_tokens=80
        )
        raw = res.choices[0].message.content.strip()
        raw = raw.lstrip('```json').lstrip('```').rstrip('```').strip()
        data = json.loads(raw)
        return data.get('title','---'), data.get('author','---')
    except Exception:
        return '---', '---'


def analyze_content(text, pages, content_type_key, api_key, profile_instructions='', enrichment_block=''):
    client = OpenAI(api_key=api_key)
    ctype = CONTENT_TYPES[content_type_key]
    type_prompt = TYPE_ANALYSIS_PROMPTS.get(content_type_key, TYPE_ANALYSIS_PROMPTS['personal'])

    reader_block = ''
    if profile_instructions:
        reader_block = f"""
╔══════════════════════════════════════════════════════════╗
  PERFIL DEL LECTOR — Úsalo para personalizar TODO
╚══════════════════════════════════════════════════════════╝
{profile_instructions}
Escribe pensando en ESTA persona. Usa "tú" cuando sea natural.
Conecta el libro con su vida, sus tensiones y sus objetivos.
═══════════════════════════════════════════════════════════
"""

    prompt = f"""Eres un intérprete intelectual de élite. Tu trabajo NO es hacer resúmenes.
Tu trabajo es mostrar qué hay realmente en un libro, por qué importa, y cómo ha transformado a personas reales.

LA DIFERENCIA ENTRE RESUMIR E INTERPRETAR:
✗ RESUMIR: "Camus sostiene que la vida es absurda y propone vivir con conciencia del absurdo."
✓ INTERPRETAR: "Camus escribe para personas que ya saben que la vida puede no tener sentido
  y aun así no pueden dejar de buscarle uno. El libro no responde esa pregunta — enseña a vivir sin responderla.
  Y por eso lo han leído millones: no porque solucione el problema, sino porque lo nombra."

{reader_block}

{enrichment_block}

Tipo de contenido: {ctype['label']}

{type_prompt}

Responde SOLO con JSON válido (sin markdown):
{{
  "title": "Título exacto",
  "author": "Autor(es) o '---'",
  "year": "Año o '---'",
  "branch": "Área específica y precisa",
  "content_type": "{content_type_key}",
  "summary": "Interpretación profunda y personalizada — NO resumen",
  "why_this_book_matters": [
    {{"profile": "tipo de lector por momento de vida", "insight": "qué encuentra ahí que no esperaba"}}
  ],
  "concept_map": [
    {{"from": "concepto A", "to": "concepto B", "relation": "cómo se conectan"}}
  ],
  "debate_suggestion": {{
    "natural_opponent": "nombre del pensador/autor/enfoque contrario",
    "natural_ally": "nombre del pensador/autor/enfoque afín",
    "central_tension": "la tensión en una oración",
    "why": "por qué ese debate específico es revelador",
    "reader_position": "dónde se ubicaría probablemente este lector"
  }},
  "key_concepts": [{{"term":"...","definition":"...","context":"..."}}],
  "norms": [{{"norm":"...","content":"...","relevance":"..."}}],
  "jurisprudence": [{{"case":"...","court":"...","contribution":"..."}}],
  "tools_frameworks": [{{"name":"...","purpose":"...","when_to_use":"..."}}],
  "action_items": [{{"action":"...","context":"...","benefit":"..."}}],
  "exam_questions": [{{"question":"...","hint":"..."}}],
  "chapter_map": [{{"chapter":"...","topics":["..."]}}]
}}

CONTENIDO DEL LIBRO:
{text}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0.4,
        max_tokens=5000
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r'^```(?:json)?\s*','',raw)
    raw = re.sub(r'\s*```$','',raw)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Error en respuesta JSON: {str(e)}")

    result['pages'] = pages
    for f in ['key_concepts','norms','jurisprudence','tools_frameworks','action_items',
              'exam_questions','chapter_map','why_this_book_matters','concept_map']:
        if f not in result:
            result[f] = []
    if 'debate_suggestion' not in result:
        result['debate_suggestion'] = {}
    return result


def process_source(source_type, filepath_or_url, api_key, profile_instructions=''):
    # 1. Extraer texto
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

    # 2. Detectar tipo de contenido
    content_type_key = detect_content_type(text, api_key)

    # 3. Detectar título y autor para buscar en la web
    title, author = _quick_detect_title_author(text, api_key)

    # 4. Enriquecer con búsqueda web en 4 capas
    enrichment_block = ''
    if title != '---':
        try:
            from enrichment import enrich_book_context, build_enrichment_block
            enrichment = enrich_book_context(title, author, content_type_key, api_key)
            enrichment_block = build_enrichment_block(enrichment, title, author)
        except Exception as e:
            print(f"⚠ Enrichment falló (no crítico): {e}")
            enrichment_block = ''

    # 5. Analizar con IA usando texto + enriquecimiento + perfil del lector
    result = analyze_content(text, pages, content_type_key, api_key, profile_instructions, enrichment_block)
    result['source_type'] = source_type
    return result