import json, base64, re
from flask import request, jsonify, session
from database import get_db
from auth import login_required

def extract_academic_data(content_b64, content_type, api_key, is_image=False):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    if is_image:
        prompt_text = """Analiza esta imagen de una malla curricular o pensum universitario.
Extrae TODOS los datos que puedas ver y responde SOLO con JSON válido:
{
  "type": "malla",
  "career": "Nombre de la carrera",
  "university": "Universidad si aparece",
  "total_semesters": 10,
  "subjects": [
    {
      "name": "Nombre de la materia",
      "semester": 1,
      "credits": 3,
      "code": "código si aparece o null"
    }
  ]
}"""
        messages = [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{content_b64}"}},
                {"type": "text", "text": prompt_text}
            ]
        }]
        model = "gpt-4o"
    else:
        prompt_text = f"""Analiza este texto de una malla curricular o horario universitario.
Responde SOLO con JSON válido, sin texto adicional:

Si es una MALLA CURRICULAR:
{{
  "type": "malla",
  "career": "Nombre de la carrera",
  "university": "Universidad",
  "total_semesters": 10,
  "subjects": [
    {{"name": "Nombre", "semester": 1, "credits": 3, "code": "código o null"}}
  ]
}}

Si es un HORARIO SEMANAL:
{{
  "type": "horario",
  "semester": "2024-2",
  "subjects": [
    {{
      "name": "Nombre de la materia",
      "days": ["Lunes", "Miércoles"],
      "time": "7:00-9:00",
      "room": "aula o null",
      "professor": "nombre o null"
    }}
  ]
}}

TEXTO:
{content_b64}"""
        messages = [{"role": "user", "content": prompt_text}]
        model = "gpt-4o-mini"

    response = client.chat.completions.create(
        model=model, messages=messages, temperature=0.1, max_tokens=2000)
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    try:
        return json.loads(raw)
    except:
        return {"type": "unknown", "raw": raw, "subjects": []}

def register_academic_routes(app):

    @app.route('/api/academic/upload', methods=['POST'])
    @login_required
    def upload_academic():
        user_id = session['user_id']
        db = get_db()
        import os
        env_key = os.environ.get('OPENAI_API_KEY', '').strip()
        if env_key:
            api_key = env_key
        else:
            user = db.execute('SELECT api_key_enc FROM users WHERE id=?', (user_id,)).fetchone()
            api_key = (user['api_key_enc'] if user else '') or ''
        if not api_key:
            return jsonify({'error': 'No hay una API key de OpenAI configurada'}), 400

        doc_type = request.form.get('doc_type', 'malla')

        if 'file' not in request.files:
            return jsonify({'error': 'No se envió archivo'}), 400

        file = request.files['file']
        fname = file.filename.lower()
        is_image = fname.endswith(('.jpg','.jpeg','.png','.webp','.heic'))
        is_pdf = fname.endswith('.pdf')

        if is_image:
            raw_bytes = file.read()
            b64 = base64.b64encode(raw_bytes).decode()
            parsed = extract_academic_data(b64, doc_type, api_key, is_image=True)
            content_stored = b64[:200] + '...'
        elif is_pdf:
            import pdfplumber, io
            raw_bytes = file.read()
            text = ''
            with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t: text += t + '\n'
                    if len(text) > 10000: break
            parsed = extract_academic_data(text[:10000], doc_type, api_key, is_image=False)
            content_stored = text[:500]
        else:
            return jsonify({'error': 'Solo se aceptan imágenes o PDFs'}), 400

        db.execute('''
            INSERT INTO academic_data (user_id, type, content, parsed)
            VALUES (?,?,?,?)
        ''', (user_id, doc_type, content_stored, json.dumps(parsed)))
        db.commit()

        return jsonify({'ok': True, 'parsed': parsed})

    @app.route('/api/academic/data', methods=['GET'])
    @login_required
    def get_academic():
        user_id = session['user_id']
        db = get_db()
        rows = db.execute(
            'SELECT id, type, parsed, created_at FROM academic_data WHERE user_id=? ORDER BY created_at DESC',
            (user_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try: d['parsed'] = json.loads(d['parsed'])
            except: pass
            result.append(d)
        return jsonify(result)

    @app.route('/api/academic/data/<int:doc_id>', methods=['DELETE'])
    @login_required
    def delete_academic(doc_id):
        user_id = session['user_id']
        db = get_db()
        db.execute('DELETE FROM academic_data WHERE id=? AND user_id=?', (doc_id, user_id))
        db.commit()
        return jsonify({'ok': True})

    @app.route('/api/academic/subjects', methods=['GET'])
    @login_required
    def get_subjects():
        user_id = session['user_id']
        db = get_db()
        rows = db.execute(
            'SELECT parsed FROM academic_data WHERE user_id=? ORDER BY created_at DESC',
            (user_id,)
        ).fetchall()
        all_subjects = []
        for r in rows:
            try:
                parsed = json.loads(r['parsed'])
                subs = parsed.get('subjects', [])
                for s in subs:
                    name = s.get('name','')
                    if name and name not in [x['name'] for x in all_subjects]:
                        all_subjects.append({'name': name, 'semester': s.get('semester'), 'credits': s.get('credits')})
            except: pass
        return jsonify(all_subjects)

def get_academic_context(user_id):
    db = get_db()
    rows = db.execute(
        'SELECT type, parsed FROM academic_data WHERE user_id=? ORDER BY created_at DESC LIMIT 5',
        (user_id,)
    ).fetchall()
    if not rows:
        return ''
    parts = ['CONTEXTO ACADÉMICO DEL USUARIO:']
    for r in rows:
        try:
            parsed = json.loads(r['parsed'])
            t = parsed.get('type','')
            if t == 'malla':
                career = parsed.get('career','')
                subs = parsed.get('subjects', [])
                parts.append(f"Carrera: {career}. Materias: {', '.join(s['name'] for s in subs[:20])}.")
            elif t == 'horario':
                subs = parsed.get('subjects', [])
                parts.append(f"Horario actual: {', '.join(s['name'] for s in subs)}.")
        except: pass
    return '\n'.join(parts)