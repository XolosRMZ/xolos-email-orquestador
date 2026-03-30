import imaplib
import email
from email.header import decode_header
import os
import datetime
import ssl
import re
from render_email import procesar_correo

# ==========================================
# CONFIGURACIÓN (Vía Variables de Entorno)
# ==========================================
IMAP_SERVER = os.environ.get("XOLOS_IMAP_SERVER", "mail.xolosramirez.com")
IMAP_USER = os.environ.get("XOLOS_IMAP_USER", "fernando@xolosramirez.com")
IMAP_PASS = os.environ.get("XOLOS_IMAP_PASS", "")

# ==========================================
# UTILIDADES DE PARSEO (EXTRACTORES)
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
    """
    Extrae el nombre, email y el mensaje real del cuerpo de un correo de Formspree.
    """
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
# BUCLE PRINCIPAL
# ==========================================
def leer_inbox():
    print(f"Conectando a {IMAP_SERVER}...")
    if not IMAP_PASS:
        print("ERROR: La variable de entorno XOLOS_IMAP_PASS no está configurada.")
        return

    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        mail = imaplib.IMAP4_SSL(IMAP_SERVER, ssl_context=ssl_context)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select("inbox")

        # Cambiamos a UNSEEN para procesar solo los no leídos
        status, data = mail.search(None, "UNSEEN")
        
        if status != "OK":
            print("Error al buscar correos.")
            return

        ids_mensajes = data[0].split()
        if not ids_mensajes:
            print("-> No hay correos nuevos.")
            return
            
        print(f"-> {len(ids_mensajes)} correos no leídos encontrados.\n")

        if not os.path.exists("outputs"):
            os.makedirs("outputs")

        for i, num in enumerate(ids_mensajes):
            status, fetch_data = mail.fetch(num, "(RFC822)")
            for response_part in fetch_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    asunto = decodificar_asunto(msg["Subject"])
                    remitente_raw = msg.get("From", "")
                    cuerpo_crudo = extraer_cuerpo(msg)
                    
                    # --- INTERCEPTOR DE FORMSPREE ---
                    if "formspree" in remitente_raw.lower() or "formspree" in asunto.lower():
                        print(f"[{i+1}] ¡Formspree Detectado! Limpiando Lead...")
                        print("    ----- CUERPO CRUDO FORMSPREE (Snippet) -----")
                        print(cuerpo_crudo[:800]) # Depuración del cuerpo
                        print("    --------------------------------------------")
                        
                        nombre_remitente, email_real, cuerpo_real = parsear_formspree(cuerpo_crudo)
                    else:
                        print(f"[{i+1}] Correo Directo Detectado.")
                        nombre_remitente = extraer_nombre(remitente_raw)
                        email_real = ""
                        cuerpo_real = cuerpo_crudo
                    
                    print(f"    De (Real): {nombre_remitente}")
                    if email_real:
                        print(f"    Email (Real): {email_real}")
                    print(f"    Asunto: {asunto}")
                    
                    # --- ORQUESTADOR ---
                    html_respuesta = procesar_correo(asunto, cuerpo_real, nombre_remitente)
                    
                    # --- GUARDAR RESULTADO ---
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"outputs/draft_{timestamp}_msg{i+1}.html"
                    
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(html_respuesta)
                    print(f"    [✔] Guardado en: {filename}\n")
                    
        mail.logout()
        print("Proceso finalizado con éxito.")
        
    except Exception as e:
        print(f"Error conectando por IMAP: {e}")

if __name__ == "__main__":
    leer_inbox()
