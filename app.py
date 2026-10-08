"""
Chatbot de WhatsApp para clínica de adelgazamiento (tratamientos no invasivos)
Los datos de la clínica están en config.py. Las claves se configuran como variables de entorno.
"""
import os
import requests
from flask import Flask, request

app = Flask(__name__)

# ----------------------------- CREDENCIALES (variables de entorno) -----------------------------
TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_ID = os.getenv("PHONE_NUMBER_ID", "")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")
ADVISOR = os.getenv("ADVISOR_NUMBER", "")

from config import CLINICA, HORARIO, DIRECCION, MAPS, TRATAMIENTOS, AVISO  # noqa: E402

vistos = set()  # ids de mensajes ya procesados (Meta a veces reenvía)

sesiones = {}  # {telefono: {"estado": str, "datos": dict}}


# ----------------------------- ENVÍO DE MENSAJES -----------------------------
def _post(payload):
    url = f"https://graph.facebook.com/v21.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        if r.status_code >= 400:
            print("Error WhatsApp:", r.text)
    except requests.RequestException as e:
        print("Error de red:", e)


def enviar_texto(to, texto):
    _post({"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": texto}})


def enviar_botones(to, texto, botones):
    """botones: lista de (id, titulo) — máximo 3, título hasta 20 caracteres."""
    _post({
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": texto},
            "action": {"buttons": [
                {"type": "reply", "reply": {"id": i, "title": t}} for i, t in botones
            ]},
        },
    })


def enviar_lista(to, texto, boton, filas):
    """filas: lista de (id, titulo, descripcion) — máximo 10, título hasta 24 caracteres."""
    _post({
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": texto},
            "action": {"button": boton, "sections": [{
                "title": "Opciones",
                "rows": [{"id": i, "title": t, "description": d} for i, t, d in filas],
            }]},
        },
    })


# ----------------------------- MENSAJES DEL FLUJO -----------------------------
def menu_principal(to):
    sesiones[to] = {"estado": "menu", "datos": sesiones.get(to, {}).get("datos", {})}
    enviar_lista(
        to,
        f"✨ ¡Hola! Soy el asistente virtual de *{CLINICA}*.\n"
        "Te ayudo con información sobre nuestros tratamientos corporales *no invasivos* "
        "(sin cirugía, sin agujas). ¿Qué te gustaría hacer?",
        "Ver opciones",
        [
            ("m_tratamientos", "Tratamientos", "Conoce cómo funciona cada uno"),
            ("m_precios", "Precios", "Costos y promociones"),
            ("m_agendar", "Agendar evaluación", "Cita de valoración gratuita"),
            ("m_ubicacion", "Ubicación y horarios", "Cómo llegar"),
            ("m_faq", "Preguntas frecuentes", "Dudas comunes"),
            ("m_asesor", "Hablar con asesora", "Atención personalizada"),
        ],
    )


def menu_tratamientos(to):
    sesiones[to]["estado"] = "tratamientos"
    enviar_lista(
        to, "Estos son nuestros tratamientos. Elige uno para ver el detalle 👇", "Tratamientos",
        [(k, v["nombre"], "") for k, v in TRATAMIENTOS.items()],
    )


def detalle_tratamiento(to, clave):
    t = TRATAMIENTOS[clave]
    sesiones[to]["datos"]["interes"] = t["nombre"]
    enviar_texto(to, f"*{t['nombre']}*\n\n{t['desc']}\n\n💰 {t['precio']}\n\n{AVISO}")
    enviar_botones(to, "¿Qué deseas hacer ahora?", [
        ("m_agendar", "Agendar evaluación"),
        ("m_tratamientos", "Ver otros"),
        ("m_menu", "Menú principal"),
    ])


def mostrar_precios(to):
    lineas = [f"• {v['nombre']}: {v['precio']}" for v in TRATAMIENTOS.values()]
    enviar_texto(
        to,
        "💰 *Precios referenciales*\n\n" + "\n".join(lineas) +
        "\n\n🎁 Consulta por nuestros *paquetes de 6 y 10 sesiones* con descuento.\n\n" + AVISO,
    )
    enviar_botones(to, "¿Te gustaría una evaluación gratuita?", [
        ("m_agendar", "Agendar evaluación"),
        ("m_asesor", "Hablar con asesora"),
        ("m_menu", "Menú principal"),
    ])


def mostrar_ubicacion(to):
    enviar_texto(to, f"📍 *Dirección:* {DIRECCION}\n🕘 *Horario:* {HORARIO}\n🗺️ {MAPS}")
    enviar_botones(to, "¿Algo más?", [("m_agendar", "Agendar evaluación"), ("m_menu", "Menú principal")])


def mostrar_faq(to):
    sesiones[to]["estado"] = "faq"
    enviar_lista(to, "Elige tu duda 👇", "Preguntas", [
        ("f_dolor", "¿Duele?", "Sensaciones durante el tratamiento"),
        ("f_resultados", "¿Cuándo veo resultados?", "Tiempos aproximados"),
        ("f_sesiones", "¿Cuántas sesiones?", "Según cada caso"),
        ("f_contra", "¿Quiénes no pueden?", "Contraindicaciones"),
    ])


FAQ = {
    "f_dolor": "Los tratamientos no invasivos son, en general, bien tolerados. Puedes sentir calor, "
               "frío o una vibración suave según el equipo. No requieren anestesia ni recuperación.",
    "f_resultados": "Depende de la persona y del tratamiento. Muchas pacientes notan cambios "
                    "progresivos a partir de las primeras sesiones; en la evaluación te damos una "
                    "estimación realista.",
    "f_sesiones": "El número de sesiones se define en la evaluación según tu objetivo, la zona a "
                  "tratar y tu composición corporal.",
    "f_contra": "Algunos tratamientos no se recomiendan en embarazo, lactancia, marcapasos, "
                "ciertas condiciones médicas o con implantes metálicos en la zona. Por eso la "
                "evaluación previa es obligatoria. Si tienes una condición médica, consulta antes "
                "con tu médico.",
}


# ----------------------------- AGENDAR CITA -----------------------------
def iniciar_agenda(to):
    sesiones[to]["estado"] = "agenda_nombre"
    enviar_texto(to, "¡Perfecto! 📅 Te agendo una *evaluación gratuita*.\n\n¿Cuál es tu *nombre completo*?")


def flujo_agenda(to, texto):
    s = sesiones[to]
    d = s["datos"]
    if s["estado"] == "agenda_nombre":
        d["nombre"] = texto.strip()
        s["estado"] = "agenda_interes"
        enviar_lista(to, f"Gracias, {d['nombre'].split()[0]} 😊 ¿Qué te interesa tratar?", "Elegir", [
            *[(k, v["nombre"], "") for k, v in TRATAMIENTOS.items()],
            ("t_noseguro", "Aún no lo sé", "Quiero orientación"),
        ])
    elif s["estado"] == "agenda_fecha":
        d["fecha"] = texto.strip()
        s["estado"] = "agenda_confirma"
        enviar_botones(
            to,
            f"Confirma tus datos:\n\n👤 {d['nombre']}\n💆 {d.get('interes', 'Por definir')}\n"
            f"🗓️ {d['fecha']}\n\n¿Es correcto?",
            [("c_si", "Sí, confirmar"), ("c_no", "Corregir")],
        )


def confirmar_cita(to):
    d = sesiones[to]["datos"]
    enviar_texto(
        to,
        "✅ ¡Solicitud enviada! Una asesora te confirmará la hora exacta por este mismo chat "
        "en breve. Recuerda venir con ropa cómoda. ¡Te esperamos! 💛",
    )
    if ADVISOR:
      enviar_texto(
        ADVISOR,
        f"🔔 *NUEVA SOLICITUD DE EVALUACIÓN*\n👤 {d.get('nombre')}\n📱 +{to}\n"
        f"💆 {d.get('interes', 'Por definir')}\n🗓️ {d.get('fecha')}",
    )
    sesiones[to]["estado"] = "menu"


def derivar_asesor(to):
    enviar_texto(to, "Con gusto 🙌 Una asesora te escribirá en breve. Horario: " + HORARIO)
    if ADVISOR:
        enviar_texto(ADVISOR, f"🙋 El cliente +{to} pidió hablar con una asesora.")
    sesiones[to]["estado"] = "humano"  # el bot deja de responder hasta que escriban 'menu'


# ----------------------------- LÓGICA PRINCIPAL -----------------------------
def manejar(to, texto, boton_id):
    s = sesiones.setdefault(to, {"estado": "inicio", "datos": {}})
    t = (texto or "").lower().strip()

    # Atajos globales
    if t in ("menu", "menú", "hola", "buenas", "inicio", "0") or s["estado"] == "inicio":
        return menu_principal(to)

    # Si está con un humano, no interrumpir
    if s["estado"] == "humano":
        return

    # Botones / listas
    if boton_id:
        if boton_id == "m_menu":
            return menu_principal(to)
        if boton_id == "m_tratamientos":
            return menu_tratamientos(to)
        if boton_id == "m_precios":
            return mostrar_precios(to)
        if boton_id == "m_agendar":
            return iniciar_agenda(to)
        if boton_id == "m_ubicacion":
            return mostrar_ubicacion(to)
        if boton_id == "m_faq":
            return mostrar_faq(to)
        if boton_id == "m_asesor":
            return derivar_asesor(to)
        if boton_id in TRATAMIENTOS and s["estado"] == "tratamientos":
            return detalle_tratamiento(to, boton_id)
        if boton_id in FAQ:
            enviar_texto(to, FAQ[boton_id] + "\n\n" + AVISO)
            return enviar_botones(to, "¿Te ayudo con algo más?", [
                ("m_agendar", "Agendar evaluación"), ("m_faq", "Más preguntas"), ("m_menu", "Menú principal"),
            ])
        if s["estado"] == "agenda_interes" and (boton_id in TRATAMIENTOS or boton_id == "t_noseguro"):
            s["datos"]["interes"] = TRATAMIENTOS[boton_id]["nombre"] if boton_id in TRATAMIENTOS else "Por definir"
            s["estado"] = "agenda_fecha"
            return enviar_texto(to, "¿Qué *día y horario* te viene mejor? (ej: martes por la tarde)\n" + HORARIO)
        if boton_id == "c_si":
            return confirmar_cita(to)
        if boton_id == "c_no":
            return iniciar_agenda(to)

    # Texto libre dentro del flujo de agenda
    if s["estado"].startswith("agenda_"):
        return flujo_agenda(to, texto)

    # Palabras clave en texto libre
    if any(p in t for p in ("precio", "costo", "cuánto", "cuanto", "valor")):
        return mostrar_precios(to)
    if any(p in t for p in ("cita", "agendar", "reservar", "evaluación", "evaluacion")):
        return iniciar_agenda(to)
    if any(p in t for p in ("dirección", "direccion", "ubicación", "ubicacion", "horario", "dónde", "donde")):
        return mostrar_ubicacion(to)
    if any(p in t for p in ("asesor", "persona", "humano", "llamar")):
        return derivar_asesor(to)

    enviar_texto(to, "No logré entender tu mensaje 🤔 Te muestro el menú:")
    menu_principal(to)


# ----------------------------- WEBHOOK -----------------------------
@app.route("/")
def salud():
    return "Chatbot activo", 200


@app.route("/webhook", methods=["GET"])
def verificar():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge", ""), 200
    return "Token inválido", 403


@app.route("/webhook", methods=["POST"])
def recibir():
    data = request.get_json(silent=True) or {}
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                for msg in change.get("value", {}).get("messages", []):
                    if msg.get("id") in vistos:
                        continue
                    vistos.add(msg.get("id"))
                    if len(vistos) > 5000:
                        vistos.clear()
                    to = msg["from"]
                    texto, boton_id = None, None
                    if msg["type"] == "text":
                        texto = msg["text"]["body"]
                    elif msg["type"] == "interactive":
                        inter = msg["interactive"]
                        r = inter.get("button_reply") or inter.get("list_reply")
                        boton_id, texto = r["id"], r["title"]
                    else:
                        texto = ""  # imágenes, audios, etc.
                    manejar(to, texto, boton_id)
    except Exception as e:
        print("Error procesando mensaje:", e)
    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
