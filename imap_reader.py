import imaplib
import email
from email.header import decode_header
from email.message import EmailMessage
import os
import datetime
import ssl
import re
import time
import socket
from render_email import procesar_correo

# 1. TIMEOUT GLOBAL PARA EVITAR CUELGUES
socket.setdefaulttimeout(15)

# ==========================================
# CONFIGURACIÓN 
# ==========================================
IMAP_SERVER = os.environ.get("XOLOS_IMAP_SERVER", "mail.xolosramirez.com")
IMAP_USER = os.environ.get("XOLOS_IMAP_USER", "fernando@xolosramirez.com")
IMAP_PASS = os.environ.get("XOLOS_IMAP_PASS", "")

DRAFTS_FOLDER = "Drafts"

# ==========================================
# UTILIDADES DE PARSEO
# ==========================================
def decodificar_asunto(header_value):
    if not header_value: return "Sin Asunto"
    decoded_bytes, charset = decode_header(header_value)[0]
    if charset:
        return decoded_bytes.decode(charset)
    elif isinstance(decoded_bytes, bytes):
        return decoded_bytes.decode('utf-8', errors='ignore')
    return str(decoded_bytes)

def extraer_cuerpo(msg):
    cuerpo = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                cuerpo = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                break
    else:
        cuerpo = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
    return cuerpo

def extraer_nombre(remitente_raw):
    if remitente_raw and '<' in remitente_raw:
        nombre = remitente_raw.split('<')[0].strip().replace('"', '')
        if nombre: 
            return nombre
    return "Amigo(a)"

def parsear_formspree(cuerpo_crudo):
    nombre_real = "Amigo(a)"
    email_real = ""
    mensaje_real = cuerpo_crudo

    match_nombre = re.search(r'(?im)^(?:nombre|name)\s*:\s*(.+)$', cuerpo_crudo)
    if match_nombre:
        nombre_real = match_nombre.group(1).strip()

    match_email = re.search(r'(?im)^(?:correo|email|e-mail)\s*:\s*(.+)$', cuerpo_crudo)
    if match_email:
        email_real = match_email.group(1).strip()

    match_mensaje = re.search(r'(?is)(?:^|\n)(?:mensaje|message)\s*:\s*(.+)', cuerpo_crudo)
    if match_mensaje:
        mensaje_real = match_mensaje.group(1).strip()

    return nombre_real, email_real, mensaje_real

# ==========================================
# INSTRUMENTACIÓN IMAP
# ==========================================
def listar_carpetas(mail):
    status, folders = mail.list()
    if status == "OK":
        print("\n    --- Carpetas disponibles en IMAP ---")
        for folder in folders:
            print("    " + folder.decode("utf-8", errors="ignore"))
        print("    ------------------------------------\n")
    else:
        print("    No se pudieron listar las carpetas IMAP.")

# ==========================================
# BUCLE PRINCIPAL
# ==========================================
def leer_inbox():
    print(f"Conectando a {IMAP_SERVER}...")

    if not IMAP_PASS:
        print("ERROR: La variable de entorno XOLOS_IMAP_PASS no está configurada.")
        return

    try:
        print("[1/7] Creando contexto SSL...")
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        print("[2/7] Abriendo conexión IMAP SSL (Timeout: 15s)...")
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, 993, ssl_context=ssl_context)

        print("[3/7] Haciendo login...")
        login_status, login_data = mail.login(IMAP_USER, IMAP_PASS)
        print(f"    Login: {login_status} | {login_data}")

        print("[4/7] Listando carpetas...")
        listar_carpetas(mail)

        print("[5/7] Seleccionando INBOX...")
        select_status, select_data = mail.select("INBOX")
        print(f"    Select: {select_status} | {select_data}")

        print("[6/7] Buscando UNSEEN...")
        status, data = mail.search(None, "UNSEEN")
        print(f"    Search: {status} | {data}")

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
        
        print("[7/7] Procesando mensajes y subiendo Borradores...")

        for i, num_bytes in enumerate(ids_mensajes):
            # Convertir el ID del mensaje (bytes) a string para usarlo en mail.store()
            num = num_bytes.decode('utf-8') 
            
            status, fetch_data = mail.fetch(num, "(RFC822)")
            for response_part in fetch_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    asunto_original = decodificar_asunto(msg["Subject"])
                    remitente_raw = msg.get("From", "")
                    cuerpo_crudo = extraer_cuerpo(msg)
                    correo_respuesta = remitente_raw
                    
                    if "formspree" in remitente_raw.lower() or "formspree" in asunto_original.lower():
                        print(f"[{i+1}] ¡Formspree Detectado! Limpiando Lead...")
                        nombre_remitente, email_real, cuerpo_real = parsear_formspree(cuerpo_crudo)
                        if email_real:
                            correo_respuesta = email_real 
                    else:
                        print(f"[{i+1}] Correo Directo Detectado.")
                        nombre_remitente = extraer_nombre(remitente_raw)
                        cuerpo_real = cuerpo_crudo
                        match_correo = re.search(r'<([^>]+)>', remitente_raw)
                        if match_correo:
                            correo_respuesta = match_correo.group(1)
                    
                    print(f"    De (Real): {nombre_remitente}")
                    print(f"    Asunto: {asunto_original}")
                    
                    html_respuesta = procesar_correo(asunto_original, cuerpo_real, nombre_remitente)
                    
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"outputs/draft_{timestamp}_msg{i+1}.html"
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(html_respuesta)
                    print(f"    [✔] Respaldo guardado en: {filename}")

                    borrador = EmailMessage()
                    borrador["Subject"] = f"Re: {asunto_original}"
                    borrador["From"] = IMAP_USER
                    borrador["To"] = correo_respuesta
                    
                    borrador.set_content("Por favor visualiza este correo en un cliente que soporte HTML.")
                    borrador.add_alternative(html_respuesta, subtype='html')

                    status_append, data_append = mail.append(
                        DRAFTS_FOLDER,
                        '\\Draft',
                        imaplib.Time2Internaldate(time.time()),
                        borrador.as_bytes()
                    )
                    
                    if status_append == "OK":
                        print(f"    [🚀] ¡Borrador inyectado en Mailcow exitosamente!")
                        # Marcar el correo original como leído
                        mail.store(num, '+FLAGS', '\\Seen')
                        print(f"    [✔] Correo original marcado como leído.\n")
                    else:
                        print(f"    [X] Error al inyectar borrador: {status_append} | {data_append}\n")
                    
        mail.logout()
        print("Proceso finalizado con éxito.")
        
    except socket.timeout:
        print("\n[!] ERROR: Timeout de socket al intentar conectar por IMAP. El servidor no respondió en 15 segundos.")
    except Exception as e:
        print(f"\n[!] ERROR conectando por IMAP: {type(e).__name__}: {e}")

if __name__ == "__main__":
    leer_inbox()
