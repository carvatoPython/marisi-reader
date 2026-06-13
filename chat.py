import json
from openai import OpenAI

def chat_with_context(book_data, user_message, history, api_key, profile_instructions='', academic_context=''):
    client = OpenAI(api_key=api_key)

    for f in ['key_concepts','norms','jurisprudence','exam_questions','chapter_map','tools_frameworks','action_items']:
        if isinstance(book_data.get(f), str):
            try: book_data[f] = json.loads(book_data[f])
            except: book_data[f] = []

    content_type = book_data.get('content_type', 'legal')
    type_hints = {
        'legal': 'Eres un asistente de estudio jurídico. Usa terminología legal precisa.',
        'tech': 'Eres un asistente de estudio técnico. Usa ejemplos de código cuando sea útil.',
        'data_science': 'Eres un asistente de data science. Puedes mostrar pseudocódigo o fórmulas cuando ayude.',
        'personal': 'Eres un asistente de aprendizaje personal. Conecta el contenido con situaciones prácticas.',
        'article': 'Eres un asistente de análisis crítico. Fomenta el pensamiento reflexivo.'
    }
    type_hint = type_hints.get(content_type, type_hints['legal'])

    sections = []
    if book_data.get('key_concepts'): sections.append(f"CONCEPTOS CLAVE:\n{json.dumps(book_data['key_concepts'], ensure_ascii=False)}")
    if book_data.get('norms'): sections.append(f"NORMAS/FUENTES:\n{json.dumps(book_data['norms'], ensure_ascii=False)}")
    if book_data.get('jurisprudence'): sections.append(f"JURISPRUDENCIA:\n{json.dumps(book_data['jurisprudence'], ensure_ascii=False)}")
    if book_data.get('tools_frameworks'): sections.append(f"HERRAMIENTAS:\n{json.dumps(book_data['tools_frameworks'], ensure_ascii=False)}")
    if book_data.get('action_items'): sections.append(f"ACCIONES PRÁCTICAS:\n{json.dumps(book_data['action_items'], ensure_ascii=False)}")
    if book_data.get('exam_questions'): sections.append(f"PREGUNTAS DE ESTUDIO:\n{json.dumps(book_data['exam_questions'], ensure_ascii=False)}")
    if book_data.get('chapter_map'): sections.append(f"ESTRUCTURA:\n{json.dumps(book_data['chapter_map'], ensure_ascii=False)}")

    system_prompt = f"""{type_hint}

CONTENIDO QUE ESTÁS ANALIZANDO:
Título: {book_data.get('title','Sin título')}
Autor: {book_data.get('author','Desconocido')}
Área: {book_data.get('branch','General')}
Resumen: {book_data.get('summary','')}

{chr(10).join(sections)}

{f"PERFIL DEL USUARIO:{chr(10)}{profile_instructions}" if profile_instructions else ''}
{f"CONTEXTO ACADÉMICO:{chr(10)}{academic_context}" if academic_context else ''}

Responde en español. Si te piden repasar, haz preguntas de una en una.
Usa emojis ocasionalmente (📖 ⚖️ 💡 ✅ 🔧 📊).
"""
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history[-8:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="gpt-4o-mini", messages=messages, temperature=0.5, max_tokens=800)
    return response.choices[0].message.content.strip()
