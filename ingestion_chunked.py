"""
ingestion_chunked.py — Motor de análisis para libros grandes (400+ páginas)

Arquitectura de procesamiento en background:
  PDF de 400 páginas
        ↓
  Dividir en chunks de ~15 páginas
        ↓
  Analizar cada chunk: normas, casos, conceptos (llamadas paralelas)
        ↓
  Acumular en knowledge_base completo
        ↓
  Síntesis final conectando TODO el contenido sin omitir nada
"""

import json, re, time
import pdfplumber
from openai import OpenAI

# ── CONFIG ────────────────────────────────────────────────────────────────────
PAGES_PER_CHUNK = 15       # páginas por fragmento
CHARS_PER_CHUNK = 18_000   # ~15 páginas densas en caracteres
MAX_WORKERS = 3            # llamadas GPT paralelas máximo
CHUNK_MAX_TOKENS = 2500    # tokens por análisis de chunk
SYNTHESIS_MAX_TOKENS = 8000  # tokens para síntesis final (guía ejecutiva, no JSON exhaustivo)


# ── EXTRACCIÓN POR CHUNKS ─────────────────────────────────────────────────────

def extract_pdf_chunks(filepath: str) -> tuple[list[dict], int]:
    """
    Extrae el PDF completo dividiéndolo en chunks de ~15 páginas.
    Retorna lista de chunks y total de páginas.
    """

    import os
    import gc

    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"📚 PDF: {size_mb:.2f} MB")

    chunks = []
    total_pages = 0

    with pdfplumber.open(filepath) as pdf:

        total_pages = len(pdf.pages)
        print(f"📖 Total páginas: {total_pages}")
        buffer = ""
        chunk_start = 1

        for i, page in enumerate(pdf.pages):
            page_num = i + 1
            print(f"📄 Extrayendo página {page_num}/{total_pages}")
            text = page.extract_text() or ""
            print(f"Caracteres: {len(text)}")

            
            buffer += text + "\n"

            del text
            gc.collect()

    
            is_last = page_num == total_pages
            is_full = (
                len(buffer) >= CHARS_PER_CHUNK
                or (page_num - chunk_start + 1) >= PAGES_PER_CHUNK
            )

            if is_full or is_last:
                if buffer.strip():
                    chunks.append({
                        "index": len(chunks),
                        "pages": f"{chunk_start}–{page_num}",
                        "page_start": chunk_start,
                        "page_end": page_num,
                        "text": buffer[:CHARS_PER_CHUNK]
                    })

                buffer = ""
                chunk_start = page_num + 1

    return chunks, total_pages


# ── ANÁLISIS DE UN CHUNK ──────────────────────────────────────────────────────

def _analyze_chunk(chunk: dict, chunk_index: int, total_chunks: int,
                   content_type: str, client: OpenAI) -> dict:
    """
    Analiza un fragmento del libro extrayendo hechos jurídicos / conceptuales.
    Optimizado para contenido legal pero adaptable.
    """

    type_instructions = {
        'legal': """Extrae del fragmento:
- norms: TODAS las normas citadas (ley, decreto, artículo, código) con su contenido exacto
- cases: todos los fallos y sentencias con tribunal, año y ratio decidendi
- key_concepts: conceptos jurídicos con definición doctrinal rigurosa y fuente
- chapter_topics: temas o secciones identificadas en este fragmento
- doctrinal_notes: posiciones doctrinales, debates o notas del autor""",

        'tech': """Extrae del fragmento:
- concepts: conceptos técnicos con definición y ejemplo de uso
- tools: herramientas o librerías mencionadas con su propósito
- chapter_topics: temas o secciones en este fragmento
- code_patterns: patrones o estructuras de código relevantes
- warnings: advertencias o errores comunes que menciona el autor""",

        'data_science': """Extrae del fragmento:
- algorithms: algoritmos con intuición y caso de uso
- math_concepts: conceptos matemáticos o estadísticos con intuición
- chapter_topics: temas en este fragmento
- tools: librerías mencionadas con su propósito
- pitfalls: errores comunes o supuestos que el autor advierte""",

        'philosophy': """Extrae del fragmento:
- arguments: argumentos filosóficos con su lógica interna
- key_figures: filósofos o autores citados y su posición
- chapter_topics: temas o secciones en este fragmento
- key_terms: términos técnicos con la definición EXACTA del autor
- tensions: tensiones o contradicciones que aparecen""",

        'personal': """Extrae del fragmento:
- claims: afirmaciones centrales del autor con su evidencia
- exercises: ejercicios o acciones concretas propuestas
- chapter_topics: temas en este fragmento
- examples: ejemplos o casos que usa el autor
- warnings: advertencias o excepciones que menciona""",
    }

    instructions = type_instructions.get(content_type, type_instructions['personal'])

    prompt = f"""Eres un analista experto extrayendo información de un fragmento de libro académico.
Fragmento {chunk_index + 1} de {total_chunks} — Páginas {chunk['pages']}

IMPORTANTE:
- Extrae TODO lo relevante de este fragmento, sin omitir nada
- Sé específico y riguroso — esto se acumulará con otros fragmentos
- No inventes información que no esté en el texto

{instructions}

FRAGMENTO DEL LIBRO (páginas {chunk['pages']}):
{chunk['text']}

Responde SOLO con JSON válido:
{{
  "chunk_index": {chunk_index},
  "pages": "{chunk['pages']}",
  "chapter_topics": ["tema o sección identificada en este fragmento"],
  "key_concepts": [
    {{"term": "término", "definition": "definición del autor", "page_hint": "contexto aproximado"}}
  ],
  "norms": [
    {{"norm": "identificación exacta", "content": "qué establece", "context": "cómo la usa el autor"}}
  ],
  "cases": [
    {{"case": "nombre del caso/sentencia", "court": "tribunal", "year": "año", "ratio": "qué establece"}}
  ],
  "supporting_elements": [
    {{"type": "herramienta|algoritmo|ejemplo|ejercicio|argumento", "name": "nombre", "detail": "detalle"}}
  ],
  "important_quotes": [
    "frase textual importante del fragmento"
  ],
  "doctrinal_notes": [
    "posición doctrinal, debate o nota relevante del autor"
  ]
}}"""

    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=CHUNK_MAX_TOKENS,
            response_format={"type": "json_object"}
        )
        raw = r.choices[0].message.content.strip()
        return json.loads(raw)
    except Exception as e:
        print(f"⚠ Chunk {chunk_index} falló: {e}")
        return {
            "chunk_index": chunk_index,
            "pages": chunk['pages'],
            "chapter_topics": [],
            "key_concepts": [],
            "norms": [],
            "cases": [],
            "supporting_elements": [],
            "important_quotes": [],
            "doctrinal_notes": []
        }


# ── ACUMULACIÓN DE KNOWLEDGE BASE ─────────────────────────────────────────────

def _accumulate_knowledge(chunk_results: list[dict]) -> dict:
    """
    Acumula todos los resultados de los chunks en una knowledge base unificada.
    Deduplica por nombre/norma para evitar repeticiones.
    """
    kb = {
        "chapter_topics": [],
        "key_concepts": [],
        "norms": [],
        "cases": [],
        "supporting_elements": [],
        "important_quotes": [],
        "doctrinal_notes": [],
        "chunks_processed": len(chunk_results)
    }

    seen_concepts = set()
    seen_norms = set()
    seen_cases = set()

    for chunk in chunk_results:
        # Tópicos de capítulos
        for topic in chunk.get("chapter_topics", []):
            if topic and topic not in kb["chapter_topics"]:
                kb["chapter_topics"].append(topic)

        # Conceptos clave — deduplica por término
        for c in chunk.get("key_concepts", []):
            key = c.get("term", "").lower().strip()
            if key and key not in seen_concepts:
                seen_concepts.add(key)
                kb["key_concepts"].append(c)

        # Normas — deduplica por identificación
        for n in chunk.get("norms", []):
            key = n.get("norm", "").lower().strip()
            if key and key not in seen_norms:
                seen_norms.add(key)
                kb["norms"].append(n)

        # Casos — deduplica por nombre
        for case in chunk.get("cases", []):
            key = case.get("case", "").lower().strip()
            if key and key not in seen_cases:
                seen_cases.add(key)
                kb["cases"].append(case)

        # Elementos de soporte (sin deduplicar — pueden repetirse con diferente contexto)
        kb["supporting_elements"].extend(chunk.get("supporting_elements", []))

        # Citas importantes (máx 3 por chunk para no inflar)
        quotes = chunk.get("important_quotes", [])[:3]
        kb["important_quotes"].extend(quotes)

        # Notas doctrinales
        kb["doctrinal_notes"].extend(chunk.get("doctrinal_notes", []))

    return kb


# ── SÍNTESIS FINAL ────────────────────────────────────────────────────────────

def _synthesize_full(
    title_hint: str,
    content_type: str,
    pages: int,
    knowledge_base: dict,
    profile_instructions: str,
    client: OpenAI
) -> dict:
    """
    Síntesis final usando el knowledge base completo acumulado de todos los chunks.
    Produce el análisis final rico para la DB.
    """

    CONTENT_TYPE_LABELS = {
        'legal': 'Jurídico / Derecho',
        'tech': 'Tecnología / Programación',
        'data_science': 'Data Science / IA / ML',
        'philosophy': 'Filosofía / Pensamiento',
        'personal': 'Desarrollo personal / Negocios',
        'article': 'Artículo / Ensayo / Paper',
    }
    ctype_label = CONTENT_TYPE_LABELS.get(content_type, 'Académico')

    # Comprimir knowledge base para el prompt — la KB completa ya vive en
    # knowledge_base / se persistirá en book_knowledge en la Fase 2 jerárquica.
    # Aquí solo seleccionamos una muestra representativa y manejable para
    # que el modelo pueda generar una guía ejecutiva de calidad, no un
    # volcado imposible de 300+ ítems en un solo JSON.
    kb_for_prompt = {
        "chapter_topics": knowledge_base["chapter_topics"][:60],
        "key_concepts": knowledge_base["key_concepts"][:40],
        "norms": knowledge_base["norms"][:40],
        "cases": knowledge_base["cases"][:30],
        "doctrinal_notes": knowledge_base["doctrinal_notes"][:30],
        "important_quotes": knowledge_base["important_quotes"][:20],
        "chunks_processed": knowledge_base["chunks_processed"],
        "total_concepts_in_kb": len(knowledge_base["key_concepts"]),
        "total_norms_in_kb": len(knowledge_base["norms"]),
        "total_cases_in_kb": len(knowledge_base["cases"]),
    }

    kb_json = json.dumps(kb_for_prompt, ensure_ascii=False)

    reader_block = ""
    if profile_instructions:
        reader_block = f"""
╔══════════════════════════════════════════════════════╗
  PERFIL DE LA LECTORA — esto cambia el análisis
╚══════════════════════════════════════════════════════╝
{profile_instructions}

Conecta el contenido del libro con sus necesidades específicas:
- ¿Qué va a encontrar especialmente útil para sus exámenes?
- ¿Qué normas o conceptos son más relevantes para su área de estudio?
- ¿Qué preguntas de examen se alinean con lo que está estudiando?
═══════════════════════════════════════════════════════
"""

    synthesis_instructions = {
        'legal': """
MODO GUÍA EJECUTIVA — key_concepts (selecciona los 15-20 MÁS IMPORTANTES para estudiar):
  No es necesario incluir todos los conceptos del knowledge base — esa base completa
  ya queda almacenada y disponible para consulta. Tu tarea aquí es priorizar:
  los conceptos que más probablemente aparezcan en examen o sean fundamento de otros.
  Para cada uno: definición doctrinal rigurosa, fuente normativa, aplicación práctica.

norms: Selecciona las 15-20 normas más relevantes y centrales del libro.
  Prioriza las que se citan repetidamente o sustentan los argumentos principales.

jurisprudence: Selecciona los 10-15 casos más importantes o más citados.
  Para cada uno: tribunal, año, ratio decidendi, importancia.

chapter_map: Construye el mapa de capítulos/secciones principales del libro
  (puedes resumir varios chapter_topics afines en una sola entrada de capítulo).

MODO MENTOR — summary:
  - El problema jurídico real que aborda el libro completo
  - Los 3-5 temas más importantes para exámenes
  - Lo que los estudiantes suelen pasar por alto
  - El debate doctrinal más importante que genera

exam_questions (10): Análisis de casos hipotéticos, problemas jurídicos reales,
  no memorización. Basadas en el contenido REAL del libro completo.

CRÍTICO: Esta es una guía ejecutiva de estudio, no un volcado exhaustivo.
Selecciona con criterio lo más importante — la base de conocimiento completa
del libro ya está preservada por separado y sigue disponible para consultas
puntuales (por ejemplo en el chat). Calidad y relevancia, no cantidad.
""",
        'tech': """
MODO GUÍA EJECUTIVA — key_concepts (selecciona los 15 más importantes):
  Prioriza los conceptos fundamentales sobre los que se construyen los demás.
  Con ejemplos reales de uso.

tools_frameworks: Selecciona las herramientas más relevantes con trade-offs reales.

chapter_map: Mapa de las secciones principales del libro.

exam_questions (10): Problemas reales de producción, no teoría.

CRÍTICO: Guía ejecutiva, no volcado exhaustivo. La base de conocimiento completa
sigue disponible por separado.
""",
        'personal': """
MODO GUÍA EJECUTIVA — key_concepts (selecciona los 10 más importantes):
  Prioriza las afirmaciones centrales que sostienen el argumento del libro.

action_items: Selecciona los ejercicios más prácticos y aplicables con contexto.

chapter_map: Mapa de las secciones principales.

exam_questions (10): Preguntas de aplicación práctica.

CRÍTICO: Guía ejecutiva, no volcado exhaustivo.
""",
    }
    synth_inst = synthesis_instructions.get(content_type, synthesis_instructions.get('personal', ''))

    prompt = f"""Eres un intérprete intelectual de élite. Tienes una MUESTRA REPRESENTATIVA
del knowledge base de un libro de {pages} páginas, extraído en {knowledge_base['chunks_processed']}
fragmentos analizados secuencialmente (el libro tiene en total {kb_for_prompt['total_concepts_in_kb']}
conceptos, {kb_for_prompt['total_norms_in_kb']} normas y {kb_for_prompt['total_cases_in_kb']} casos
identificados — aquí ves los más representativos).

MUESTRA DEL KNOWLEDGE BASE:
{kb_json}

TÍTULO APROXIMADO: {title_hint}
TIPO: {ctype_label}

{reader_block}

Tu trabajo: generar una GUÍA EJECUTIVA DE ESTUDIO de alta calidad a partir de esta muestra.
Selecciona con criterio lo más importante y relevante. La base de conocimiento completa del
libro ya fue preservada y sigue disponible aparte (para consultas puntuales en el chat) —
tu tarea NO es reproducirla entera aquí, sino sintetizar lo esencial en una guía clara,
profunda y útil para estudiar.

{synth_inst}

Responde SOLO con JSON válido:
{{
  "title": "título exacto del libro",
  "author": "autor o '---'",
  "year": "año o '---'",
  "branch": "área específica del derecho/conocimiento",
  "content_type": "{content_type}",

  "summary": "Síntesis profunda: problema real que aborda, importancia práctica, lo que los estudiantes suelen ignorar, debates que genera. Mínimo 200 palabras.",

  "key_concepts": [
    {{"term": "término exacto", "definition": "definición doctrinal/técnica rigurosa", "context": "conexión con otros conceptos del libro"}}
  ],

  "norms": [
    {{"norm": "identificación exacta", "content": "qué establece", "relevance": "por qué importa en este libro"}}
  ],

  "jurisprudence": [
    {{"case": "nombre del caso", "court": "tribunal", "year": "año", "contribution": "qué aporta al argumento del libro"}}
  ],

  "chapter_map": [
    {{"chapter": "nombre del capítulo/sección", "topics": ["temas que trata"]}}
  ],

  "tools_frameworks": [
    {{"name": "nombre", "purpose": "para qué sirve", "when_to_use": "cuándo aplicarlo"}}
  ],

  "action_items": [
    {{"action": "acción concreta", "context": "cuándo aplicarla", "benefit": "resultado esperado"}}
  ],

  "exam_questions": [
    {{"question": "pregunta de examen realista", "hint": "enfoque para responderla"}}
  ],

  "why_this_book_matters": [
    {{"profile": "tipo de estudiante/momento", "insight": "qué encuentra específicamente valioso"}}
  ],

  "debate_suggestion": {{
    "natural_opponent": "posición o autor que contradice",
    "natural_ally": "posición o autor que complementa",
    "central_tension": "la tensión principal en una oración",
    "why": "por qué este debate es importante"
  }},

  "concept_map": [
    {{"from": "concepto A", "to": "concepto B", "relation": "cómo se conectan"}}
  ],

  "what_community_says": {{
    "most_cited_moment": "el tema o norma más citada por estudiantes",
    "common_misconception": "el error más común al estudiar este libro",
    "community_debate": "debate académico principal sobre el contenido"
  }}
}}"""

    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=SYNTHESIS_MAX_TOKENS,
        response_format={"type": "json_object"}
    )

    print(f"📊 Síntesis: {r.usage.prompt_tokens} tokens prompt, {r.usage.completion_tokens} tokens completion")
    raw = r.choices[0].message.content.strip()
    result = json.loads(raw)

    # Garantizar campos
    result["pages"] = pages
    for f in ["key_concepts", "norms", "jurisprudence", "tools_frameworks",
              "action_items", "exam_questions", "chapter_map",
              "why_this_book_matters", "concept_map"]:
        if f not in result:
            result[f] = []
    if "debate_suggestion" not in result:
        result["debate_suggestion"] = {}
    if "what_community_says" not in result:
        result["what_community_says"] = {}

    return result


# ── DETECCIÓN DE TÍTULO Y TIPO ────────────────────────────────────────────────

def _detect_metadata(first_chunk_text: str, api_key: str) -> dict:
    """Detecta título, autor, año y tipo de contenido desde el primer chunk."""
    client = OpenAI(api_key=api_key)
    snippet = first_chunk_text[:3000]

    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"""Del siguiente texto extrae el título, autor, año y tipo de contenido.

Tipos posibles: legal / tech / data_science / philosophy / personal / article

TEXTO:
{snippet}

Responde SOLO con JSON:
{{"title": "título exacto o '---'", "author": "autor o '---'", "year": "año o '---'", "content_type": "tipo"}}"""}],
        temperature=0,
        max_tokens=100,
        response_format={"type": "json_object"}
    )
    try:
        return json.loads(r.choices[0].message.content)
    except Exception:
        return {"title": "---", "author": "---", "year": "---", "content_type": "legal"}


# ── PROCESO PRINCIPAL CON PROGRESO ────────────────────────────────────────────

def process_pdf_chunked(
    filepath: str,
    api_key: str,
    profile_instructions: str = "",
    progress_callback=None
) -> dict:
    """
    Procesa un PDF completo de cualquier extensión usando chunks.

    progress_callback(step: str, current: int, total: int, message: str)
    → llamado en cada etapa para actualizar el estado del job en DB.

    Retorna el mismo formato que process_source() original.
    """
    client = OpenAI(api_key=api_key)

    def _progress(step, current, total, message):
        if progress_callback:
            try:
                progress_callback(step, current, total, message)
            except Exception as e:
                print(f"⚠ Progress callback error: {e}")
        print(f"[{step}] {current}/{total} — {message}")

    # ── Paso 0: Extracción de chunks ────────────────────────────────────────
    _progress("extract", 0, 1, "Extrayendo páginas del PDF...")
    chunks, total_pages = extract_pdf_chunks(filepath)
    total_chunks = len(chunks)
    _progress("extract", 1, 1, f"PDF dividido en {total_chunks} fragmentos ({total_pages} páginas)")

    if not chunks:
        raise ValueError("No se pudo extraer texto del PDF")

    # ── Paso 1: Detectar metadatos desde el primer chunk ────────────────────
    _progress("metadata", 0, 1, "Detectando tipo de contenido...")
    metadata = _detect_metadata(chunks[0]["text"], api_key)
    content_type = metadata.get("content_type", "legal")
    title_hint = metadata.get("title", "---")
    _progress("metadata", 1, 1, f"Tipo detectado: {content_type} — {title_hint}")

    # ── Paso 2: Analizar chunks secuencialmente ─────────────────────────────
    chunk_results = []
    for i, chunk in enumerate(chunks):
        _progress("analyze", i, total_chunks,
                  f"Analizando páginas {chunk['pages']}...")
        result = _analyze_chunk(chunk, i, total_chunks, content_type, client)
        chunk_results.append(result)
        # Pausa pequeña para no saturar la API
        if i < total_chunks - 1:
            time.sleep(0.5)

    _progress("analyze", total_chunks, total_chunks,
              f"Todos los fragmentos analizados")

    # ── Paso 3: Acumular knowledge base ─────────────────────────────────────
    _progress("accumulate", 0, 1, "Construyendo base de conocimiento...")
    knowledge_base = _accumulate_knowledge(chunk_results)
    stats = (f"{len(knowledge_base['key_concepts'])} conceptos, "
             f"{len(knowledge_base['norms'])} normas, "
             f"{len(knowledge_base['cases'])} casos")
    _progress("accumulate", 1, 1, f"Knowledge base: {stats}")

    # ── Paso 4: Síntesis final ──────────────────────────────────────────────
    _progress("synthesize", 0, 1, "Generando análisis final completo...")
    result = _synthesize_full(
        title_hint=title_hint,
        content_type=content_type,
        pages=total_pages,
        knowledge_base=knowledge_base,
        profile_instructions=profile_instructions,
        client=client
    )
    _progress("synthesize", 1, 1, f"✅ Análisis completo: {result.get('title', '---')}")

    result["source_type"] = "pdf"
    return result