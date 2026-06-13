import os, json, re
from openai import OpenAI
import pdfplumber

MAX_CHARS = 80000

def extract_text_from_pdf(filepath):
    text = ""; page_count = 0
    with pdfplumber.open(filepath) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            extracted = page.extract_text()
            if extracted: text += extracted + "\n"
            if len(text) >= MAX_CHARS: break
    return text[:MAX_CHARS], page_count

def analyze_book(filepath, api_key):
    client = OpenAI(api_key=api_key)
    text, pages = extract_text_from_pdf(filepath)
    if len(text.strip()) < 100:
        raise ValueError("No se pudo extraer texto del PDF. Puede ser un PDF escaneado sin OCR.")

    prompt = f"""Eres un asistente jurídico especializado en derecho colombiano y latinoamericano.
Analiza el siguiente texto de un libro de derecho y responde ÚNICAMENTE con un objeto JSON válido, sin texto adicional, sin bloques de código markdown.

Estructura JSON requerida:
{{
  "title": "Título completo del libro",
  "author": "Nombre del autor",
  "year": "Año de publicación o '---'",
  "branch": "Rama del derecho (Derecho Civil, Penal, Constitucional, Laboral, Administrativo, Internacional, Comercial, Teoría General del Derecho, etc.)",
  "summary": "Resumen ejecutivo en 4-6 oraciones: qué estudia, tesis central, público objetivo, utilidad práctica.",
  "key_concepts": [
    {{"term": "Nombre del concepto", "definition": "Definición según el libro", "context": "Contexto e importancia"}}
  ],
  "norms": [
    {{"norm": "Nombre exacto de la ley/decreto/artículo", "content": "Qué dice o regula", "relevance": "Por qué es relevante"}}
  ],
  "jurisprudence": [
    {{"case": "Nombre o número del fallo", "court": "Corte o tribunal", "contribution": "Aporte al tema jurídico"}}
  ],
  "exam_questions": [
    {{"question": "Pregunta tipo parcial universitario", "hint": "Enfoque sugerido para responderla"}}
  ],
  "chapter_map": [
    {{"chapter": "Nombre/número del capítulo", "topics": ["tema 1", "tema 2"]}}
  ]
}}

Reglas: key_concepts mínimo 8, máximo 20. norms y jurisprudence: todos los que aparezcan. exam_questions: exactamente 10. Si no hay jurisprudencia, devuelve []. Solo el JSON, nada más.

TEXTO DEL LIBRO:
{text}
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0.2, max_tokens=4000)
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r'^```(?:json)?\s*','',raw); raw = re.sub(r'\s*```$','',raw)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"La IA no devolvió JSON válido: {str(e)}")
    result['pages'] = pages
    return result
