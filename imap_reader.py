import imaplib
import email
from email.header import decode_header
import os
import datetime
import ssl
from render_email import procesar_correo

# ==========================================
# CONFIGURACIÓN
# ==========================================
IMAP_SERVER = os.environ.get("XOLOS_IMAP_SERVER", "mail.xolosramirez.com")
IMAP_USER = os.environ.get("XOLOS_IMAP_USER", "fernando@xolosramirez.com")
IMAP_PASS = os.environ.get("XOLOS_IMAP_PASS", "")

# ==========================================
# UTILIDADES DE PARSEO
# ==========================================
def decodificar_asunto(header_value):
    if not header_value:
        return "Sin Asunto"

    partes = decode_header(header_value)
    asunto_final = []

    for valor, charset in partes:
        if isinstance(valor, bytes):
            asunto_final.append(valor.decode(charset or "utf-8", errors="ignore"))
        else:
            asunto_final.append(str(valor))

    return "".join(asunto_final)

def extraer_cuerpo(msg):
    cuerpo = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "")

            if content_type == "text/plain" and "attachment" not in content_disposition.lower():
                payload = part.get_payload(decode=True)
                if payload:
                    cuerpo = payload.decode("utf-8", errors="ignore")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            cuerpo = payload.decode("utf-8", errors="ignore")

    return cuerpo

def extraer_nombre(remitente_raw):
    if remitente_raw and "<" in remitente_raw:
        nombre = remitente_raw.split("<")[0].strip().replace('"', "")
        if nombre:
            return nombre
    return "Amigo(a)"

# ==========================================
# BUCLE PRINCIPAL
# ==========================================
def leer_inbox():
    print(f"Conectando a {IMAP_SERVER}...")

    if not IMAP_PASS:
        print("Error: falta XOLOS_IMAP_PASS en variables de entorno.")
        return

    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        mail = imaplib.IMAP4_SSL(IMAP_SERVER, 993, ssl_context=ssl_context)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select("INBOX")

        status, data = mail.search(None, "UNSEEN")

        if status != "OK":
            print("Error al buscar correos.")
            mail.logout()
            return

        ids_mensajes = data[0].split()

        if not ids_mensajes:
            print("-> No hay correos nuevos.")
            mail.logout()
            return

        print(f"-> {len(ids_mensajes)} correos no leídos encontrados.\n")

        os.makedirs("outputs", exist_ok=True)

        for i, num in enumerate(ids_mensajes, start=1):
            status, fetch_data = mail.fetch(num, "(RFC822)")
            if status != "OK":
                print(f"Error al leer mensaje {num}.")
                continue

            for response_part in fetch_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])

                    asunto = decodificar_asunto(msg.get("Subject"))
                    remitente_raw = msg.get("From", "")
                    nombre_remitente = extraer_nombre(remitente_raw)
                    cuerpo = extraer_cuerpo(msg)

                    print(f"[{i}] Asunto: {asunto}")
                    print(f"    De: {nombre_remitente} ({remitente_raw})")

                    html_respuesta = procesar_correo(asunto, cuerpo, nombre_remitente)

                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"outputs/draft_{timestamp}_msg{i}.html"

                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(html_respuesta)

                    print(f"    [✔] Guardado en: {filename}\n")

        mail.logout()
        print("Proceso finalizado con éxito.")

    except Exception as e:
        print(f"Error conectando por IMAP: {e}")

if __name__ == "__main__":
    leer_inbox()
