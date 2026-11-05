"""Correo saliente por SMTP, con plantilla de la marca.

Sin SMTP_SERVIDOR no se envía nada: se escribe en la consola de la API y la función devuelve False,
para que quien llama muestre la liga en pantalla. En desarrollo se usa Mailpit (docker-compose):
los correos se ven en http://localhost:8025 y no salen a internet.
"""
import logging
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from html import escape
from pathlib import Path

from core.config import configuracion

log = logging.getLogger("uvicorn.error")

_LOGO = Path(__file__).resolve().parent.parent / "recursos" / "logo-correo.png"
NARANJA = "#DE951B"
NEGRO = "#222221"


def plantilla(titulo: str, parrafos: list[str], boton: tuple[str, str] | None = None, nota: str | None = None,
              cid_logo: str | None = None, cuerpo_html: str | None = None, ancho: int = 560) -> tuple[str, str]:
    """Devuelve (html, texto). Los párrafos son texto plano; aquí se escapan.
    `cuerpo_html` (ya escapado por quien llama) se agrega después de los párrafos, para correos con más formato."""
    cabecera = (
        f'<img src="cid:{cid_logo}" alt="Súper Naturista" width="200" style="display:block;border:0;height:auto">'
        if cid_logo else f'<span style="color:{NARANJA};font-size:20px;font-weight:800">Súper Naturista</span>'
    )
    cuerpo = "".join(f'<p style="margin:0 0 14px;line-height:1.55">{escape(p)}</p>' for p in parrafos)
    if boton:
        texto_boton, liga = boton
        cuerpo += (
            f'<p style="margin:24px 0"><a href="{escape(liga)}" style="background:{NARANJA};color:{NEGRO};'
            f'text-decoration:none;font-weight:800;padding:12px 22px;border-radius:12px;display:inline-block">'
            f'{escape(texto_boton)}</a></p>'
            f'<p style="margin:0 0 14px;font-size:12px;color:#77776f;line-height:1.5">Si el botón no funciona, copia esta liga en tu navegador:<br>'
            f'<span style="word-break:break-all">{escape(liga)}</span></p>'
        )
    if cuerpo_html:
        cuerpo += cuerpo_html
    if nota:
        cuerpo += f'<p style="margin:16px 0 0;font-size:12px;color:#77776f;line-height:1.5">{escape(nota)}</p>'
    html = f"""<!doctype html><html lang="es"><body style="margin:0;background:#f3f3f0;font-family:Nunito,Segoe UI,Arial,sans-serif;color:{NEGRO}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f3f0;padding:24px 12px"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:{ancho}px;background:#ffffff;border-radius:18px;overflow:hidden">
<tr><td style="background:{NEGRO};padding:20px 28px">{cabecera}
<div style="color:#ffffff99;font-size:12px;font-weight:700;margin-top:6px">Transformación digital</div></td></tr>
<tr><td style="height:4px;background:{NARANJA}"></td></tr>
<tr><td style="padding:28px">
<h1 style="margin:0 0 16px;font-size:20px;font-weight:800">{escape(titulo)}</h1>{cuerpo}
</td></tr>
<tr><td style="padding:16px 28px;background:#f8f8f6;font-size:11px;color:#99998f">
Correo automático de SMN - Transformación digital. No respondas a este mensaje.</td></tr>
</table></td></tr></table></body></html>"""
    texto = "\n\n".join([titulo, *parrafos] + ([f"{boton[0]}: {boton[1]}"] if boton else []) + ([nota] if nota else []))
    return html, texto


def enviar(para: str, asunto: str, titulo: str, parrafos: list[str], boton: tuple[str, str] | None = None,
           nota: str | None = None, cuerpo_html: str | None = None, texto_extra: str | None = None,
           ancho: int = 560) -> bool:
    """Envía un correo. Devuelve True si el servidor SMTP lo aceptó.
    `cuerpo_html` y `texto_extra` son la parte con formato y su versión en texto plano."""
    cfg = configuracion()
    if not cfg.smtp_servidor:
        log.info("Correo no enviado (sin SMTP_SERVIDOR) a %s: %s", para, asunto)
        return False

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = cfg.smtp_remitente
    msg["To"] = para
    cid = make_msgid(domain="smn.local")[1:-1] if _LOGO.exists() else None
    html, texto = plantilla(titulo, parrafos, boton, nota, cid, cuerpo_html, ancho)
    if texto_extra:
        texto += "\n\n" + texto_extra
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")
    if cid:
        msg.get_payload()[1].add_related(_LOGO.read_bytes(), "image", "png", cid=f"<{cid}>")

    try:
        with smtplib.SMTP(cfg.smtp_servidor, cfg.smtp_puerto, timeout=10) as smtp:
            if cfg.smtp_tls:
                smtp.starttls()
            if cfg.smtp_usuario:
                smtp.login(cfg.smtp_usuario, cfg.smtp_contrasena)
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as e:
        log.warning("No se pudo enviar el correo a %s (%s): %s", para, asunto, e)
        return False
