# ⚖️ Marisi Reader

Biblioteca jurídica inteligente para estudiantes de derecho.
Sube PDFs de libros → obtén análisis completo con IA → guarda en catálogo → chatea con el libro.

---

## 🚀 Deploy en Railway (5 minutos)

### 1. Subir a GitHub
```bash
git init
git add .
git commit -m "Marisi Reader v1"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/marisi-reader.git
git push -u origin main
```

### 2. Deploy en Railway
1. Ve a **railway.app** → New Project → Deploy from GitHub repo
2. Selecciona el repo `marisi-reader`
3. Railway detecta el `Procfile` automáticamente
4. En Settings → Variables, agrega: `PORT = 5000` (Railway lo pone solo)
5. Listo — Railway te da una URL pública tipo `marisi-reader.up.railway.app`

### 3. Primera vez
- El servidor inicializa la DB automáticamente
- Marisi abre la URL en Safari en su iPhone
- Safari pregunta si quiere agregar a pantalla de inicio → ¡queda como app!

---

## 📱 Instalar como app en iPhone/iPad

1. Abrir la URL en **Safari** (no Chrome)
2. Tocar el ícono de compartir (□↑)
3. Seleccionar **"Añadir a pantalla de inicio"**
4. Confirmar → aparece el ícono en el home

---

## 🔑 API Key de OpenAI

- Obtener en: **platform.openai.com/api-keys**
- Marisi la ingresa en la pantalla de inicio de la app
- Se guarda solo en su dispositivo (localStorage)
- **Costo estimado**: analizar un libro de 300 págs ≈ $0.05–0.15 USD

---

## 📁 Estructura del proyecto

```
marisi-reader/
├── app.py          # Backend Flask + rutas API
├── analyzer.py     # Extracción PDF + análisis con GPT-4o-mini
├── chat.py         # Chat contextual con el libro
├── run.py          # Entry point
├── requirements.txt
├── Procfile        # Para Railway
├── templates/
│   └── index.html  # Frontend PWA
└── static/
    ├── css/app.css
    ├── js/app.js
    ├── manifest.json  # PWA config
    ├── sw.js          # Service Worker
    └── icons/
```

---

## ⚡ Correr localmente (para desarrollo)

```bash
pip install -r requirements.txt
python run.py
# Abre http://localhost:5000
```
