"""
comms.py — Módulo de comunicación de MERY
Maneja Gmail (OAuth2) y WhatsApp Business API.

Comandos de voz que MERY detecta automáticamente:
  "envía un correo a..."        → gmail_enviar()
  "léeme mis correos"           → gmail_leer()
  "responde el correo de..."    → gmail_responder()
  "manda un WhatsApp a..."      → whatsapp_enviar()
  "léeme mis WhatsApp"          → whatsapp_leer()
"""

import os
import base64
import json
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

# ─── Credenciales (van en .env) ───────────────────────────────────────────────
WA_TOKEN      = os.getenv("WHATSAPP_TOKEN")       # Token de Meta Business
WA_PHONE_ID   = os.getenv("WHATSAPP_PHONE_ID")    # ID del número de negocio
WA_MY_NUMBER  = os.getenv("WHATSAPP_MY_NUMBER")   # Tu número (con código país, sin +)


# ══════════════════════════════════════════════════════════════════════════════
# GMAIL
# ══════════════════════════════════════════════════════════════════════════════

def _gmail_service():
    """Retorna el servicio autenticado de Gmail.
    En Railway: lee desde variables de entorno GMAIL_TOKEN_JSON.
    En local: lee desde archivos json.
    """
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

        # ── Railway: variables de entorno ─────────────────────────────────
        token_json = os.getenv("GMAIL_TOKEN_JSON")
        if token_json:
            creds = Credentials.from_authorized_user_info(
                json.loads(token_json), SCOPES
            )
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            return build("gmail", "v1", credentials=creds), None

        # ── Local: archivos en disco ──────────────────────────────────────
        TOKEN_PATH = os.path.join(os.path.dirname(__file__), "gmail_token.json")
        CREDS_PATH = os.path.join(os.path.dirname(__file__), "gmail_credentials.json")

        creds = None
        if os.path.exists(TOKEN_PATH):
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(CREDS_PATH):
                    return None, "❌ Falta GMAIL_TOKEN_JSON en variables de entorno."
                from google_auth_oauthlib.flow import InstalledAppFlow
                flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())

        return build("gmail", "v1", credentials=creds), None

    except ImportError:
        return None, "❌ Instala: pip install google-api-python-client google-auth-oauthlib"


def gmail_enviar(destinatario: str, asunto: str, cuerpo: str) -> str:
    """Envía un correo desde tu cuenta de Gmail."""
    service, error = _gmail_service()
    if error:
        return error

    try:
        msg = MIMEMultipart()
        msg["To"]      = destinatario
        msg["Subject"] = asunto
        msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()

        return f"Correo enviado a {destinatario}."

    except Exception as e:
        return f"Error enviando correo: {e}"


def gmail_leer(max_mensajes: int = 5) -> list[dict]:
    """
    Lee los últimos correos no leídos.
    Retorna lista de dicts: {de, asunto, fragmento, id}
    """
    service, error = _gmail_service()
    if error:
        return [{"error": error}]

    try:
        result = service.users().messages().list(
            userId="me", labelIds=["UNREAD"], maxResults=max_mensajes
        ).execute()

        mensajes = []
        for m in result.get("messages", []):
            msg = service.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject"]
            ).execute()

            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            mensajes.append({
                "id":       m["id"],
                "de":       headers.get("From", "Desconocido"),
                "asunto":   headers.get("Subject", "(sin asunto)"),
                "fragmento": msg.get("snippet", "")[:120]
            })

        return mensajes

    except Exception as e:
        return [{"error": str(e)}]


def gmail_responder(mensaje_id: str, cuerpo: str) -> str:
    """Responde a un correo específico por su ID."""
    service, error = _gmail_service()
    if error:
        return error

    try:
        original = service.users().messages().get(
            userId="me", id=mensaje_id, format="metadata",
            metadataHeaders=["From", "Subject", "Message-ID", "References"]
        ).execute()

        headers = {h["name"]: h["value"] for h in original["payload"]["headers"]}

        msg = MIMEMultipart()
        msg["To"]         = headers.get("From", "")
        msg["Subject"]    = "Re: " + headers.get("Subject", "")
        msg["In-Reply-To"] = headers.get("Message-ID", "")
        msg["References"] = headers.get("References", "") + " " + headers.get("Message-ID", "")
        msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(
            userId="me",
            body={"raw": raw, "threadId": original["threadId"]}
        ).execute()

        return f"Respuesta enviada a {headers.get('From', 'destinatario')}."

    except Exception as e:
        return f"Error al responder: {e}"


def gmail_resumen_ia(client_openai, model: str) -> str:
    """
    Lee los correos no leídos y genera un resumen inteligente con IA.
    """
    correos = gmail_leer(max_mensajes=8)

    if not correos or "error" in correos[0]:
        return correos[0].get("error", "No se pudieron leer los correos.")

    if not correos:
        return "No tienes correos no leídos."

    texto = "\n".join(
        f"- De: {c['de']} | Asunto: {c['asunto']} | {c['fragmento']}"
        for c in correos
    )

    try:
        response = client_openai.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Eres MERY. Resume estos correos en 3 líneas, priorizando lo urgente. Español, directo."},
                {"role": "user", "content": texto}
            ],
            max_tokens=120
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error IA: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# WHATSAPP BUSINESS API
# ══════════════════════════════════════════════════════════════════════════════

WA_BASE_URL = "https://graph.facebook.com/v19.0"


def whatsapp_enviar(numero: str, mensaje: str) -> str:
    """
    Envía un mensaje de WhatsApp.
    numero: con código de país, sin +. Ej: 573001234567
    """
    if not WA_TOKEN or not WA_PHONE_ID:
        return "❌ Configura WHATSAPP_TOKEN y WHATSAPP_PHONE_ID en .env"

    url = f"{WA_BASE_URL}/{WA_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": mensaje}
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        r.raise_for_status()
        return f"WhatsApp enviado a {numero}."
    except requests.HTTPError as e:
        return f"Error WhatsApp: {e.response.text}"
    except Exception as e:
        return f"Error WhatsApp: {e}"


def whatsapp_leer_webhook(data: dict) -> list[dict]:
    """
    Procesa el payload de un webhook de WhatsApp Business.
    Retorna lista de mensajes recibidos.
    """
    mensajes = []
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    mensajes.append({
                        "de":      msg.get("from"),
                        "tipo":    msg.get("type"),
                        "texto":   msg.get("text", {}).get("body", ""),
                        "id":      msg.get("id"),
                        "momento": msg.get("timestamp")
                    })
    except Exception:
        pass
    return mensajes


# ══════════════════════════════════════════════════════════════════════════════
# INTÉRPRETE DE INTENCIÓN (conecta con brain.py)
# ══════════════════════════════════════════════════════════════════════════════

def interpretar_intencion_comms(texto: str) -> dict | None:
    """
    Detecta si la pregunta del usuario implica una acción de comunicación.
    Retorna dict con la acción a realizar, o None si no aplica.

    Ejemplos:
      "envía un correo a juan@email.com sobre la reunión de mañana"
      → {"accion": "gmail_enviar", "destinatario": "juan@email.com", ...}

      "léeme mis correos"
      → {"accion": "gmail_leer"}

      "manda un WhatsApp a 573001234567 que llegaré tarde"
      → {"accion": "whatsapp_enviar", "numero": "573001234567", ...}
    """
    texto_lower = texto.lower()
    palabras = set(texto_lower.split())

    # Gmail — enviar (cualquier combinación de acción + correo)
    accion_envio  = {"envía", "envia", "enviar", "manda", "mandar", "entrega", "entregar", "escribe", "escribir"}
    objeto_correo = {"correo", "email", "mail", "mensaje"}

    if accion_envio & palabras and objeto_correo & palabras:
        return {"accion": "gmail_enviar", "raw": texto}

    # Gmail — leer
    accion_leer = {"léeme", "leeme", "lee", "leer", "revisa", "revisar", "muestra", "mostrar", "tengo", "hay"}
    if accion_leer & palabras and objeto_correo & palabras:
        return {"accion": "gmail_leer"}

    # Gmail — responder
    if {"responde", "responder", "contesta", "contestar"} & palabras and objeto_correo & palabras:
        return {"accion": "gmail_responder", "raw": texto}

    # WhatsApp — enviar
    if {"whatsapp", "wsp", "ws"} & palabras:
        return {"accion": "whatsapp_enviar", "raw": texto}

    return None