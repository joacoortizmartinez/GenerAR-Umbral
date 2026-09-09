"""Endpoints de integración para Meta Lead Ads y WhatsApp Cloud API.

La V1 procesa el volumen beta en la misma petición HTTP. Cada efecto externo
queda registrado antes de ejecutarse, se deduplica por ID de Meta y los fallos
permanecen visibles en Django Admin para su resolución manual.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

import phonenumbers
import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.csrf import csrf_exempt
from openai import OpenAI

from .models import Cliente, Interaccion, Lead, WebhookEvent

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = (3.05, 12)
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_HTTP_ATTEMPTS = 3

def landing_page(request: HttpRequest) -> HttpResponse:
    """Página pública mínima de Umbral para el piloto comercial."""
    html = """<!doctype html><html lang='es'><head><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>Umbral | Consultas que se convierten en visitas</title>
    <style>
    body{margin:0;background:#0b1220;color:#eff6ff;font-family:Arial,sans-serif}
    main{max-width:760px;margin:0 auto;padding:120px 28px}
    .brand{color:#67e8f9;font-weight:700;letter-spacing:.13em;font-size:.85rem}
    h1{font-size:clamp(2.6rem,7vw,5rem);line-height:1.02;margin:18px 0}
    p{max-width:650px;color:#cbd5e1;font-size:1.2rem;line-height:1.6}
    .tag{display:inline-block;margin-top:18px;padding:11px 15px;border:1px solid #22d3ee;border-radius:999px;color:#a5f3fc}
    </style></head><body><main><div class='brand'>UMBRAL</div>
    <h1>Más consultas.<br>Mejores visitas técnicas.</h1>
    <p>Umbral ayuda a carpinterías de aluminio y PVC, cerramientos y soluciones en acrílico a ordenar, calificar y convertir sus consultas en oportunidades reales.</p>
    <div class='tag'>Piloto privado para carpinterías</div></main></body></html>"""
    return HttpResponse(html, content_type="text/html; charset=utf-8")


def _manual_intake_page(request: HttpRequest, cliente: Cliente, error: str = "", success: bool = False) -> HttpResponse:
    """Formulario de capacidad limitada para un piloto sin integración de Meta."""
    notice = (
        "<p class='notice success'>Consulta registrada. Umbral la calificó y ya está disponible para revisión.</p>"
        if success else (f"<p class='notice error'>{escape(error)}</p>" if error else "")
    )
    html = f"""<!doctype html><html lang='es'><head><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>Derivar consulta | {escape(cliente.nombre)} · Umbral</title>
    <style>
    body{{margin:0;background:#0b1220;color:#eff6ff;font-family:Arial,sans-serif}}
    main{{max-width:640px;margin:0 auto;padding:54px 22px}} .brand{{color:#67e8f9;font-size:.82rem;font-weight:700;letter-spacing:.13em}}
    h1{{font-size:2rem;margin:12px 0}} p{{color:#cbd5e1;line-height:1.5}} form{{margin-top:28px;padding:24px;background:#111c30;border:1px solid #26364f;border-radius:14px}}
    label{{display:block;font-weight:700;margin:18px 0 7px}} input,textarea{{box-sizing:border-box;width:100%;padding:12px;border:1px solid #475569;border-radius:8px;background:#0b1220;color:#eff6ff;font:inherit}}
    textarea{{min-height:140px;resize:vertical}} .check{{display:flex;gap:9px;align-items:flex-start;font-size:.9rem;font-weight:400;color:#cbd5e1}} .check input{{width:auto;margin-top:3px}}
    button{{margin-top:20px;padding:13px 18px;border:0;border-radius:8px;background:#22d3ee;color:#06202a;font-weight:700;font-size:1rem;cursor:pointer}}
    .notice{{padding:12px 14px;border-radius:8px}} .success{{background:#123b31;color:#bbf7d0}} .error{{background:#4a1d26;color:#fecdd3}}
    small{{color:#94a3b8;display:block;margin-top:18px}}
    </style></head><body><main><div class='brand'>UMBRAL · PILOTO MANUAL</div>
    <h1>Derivar una consulta</h1><p>Registrá una consulta de <strong>{escape(cliente.nombre)}</strong>. Umbral la ordena y la deja lista para revisión.</p>{notice}
    <form method='post'><input type='hidden' name='csrfmiddlewaretoken' value='{get_token(request)}'>
    <label for='nombre'>Nombre del prospecto</label><input id='nombre' name='nombre' maxlength='160' required>
    <label for='telefono'>WhatsApp con código de país</label><input id='telefono' name='telefono' placeholder='+54 9 11 1234 5678' maxlength='32' required>
    <label for='consulta'>Consulta, medidas, zona o notas disponibles</label><textarea id='consulta' name='consulta' maxlength='4000' required></textarea>
    <label class='check'><input type='checkbox' name='consentimiento' value='si' required> Confirmo que esta persona autorizó ser contactada por WhatsApp sobre su consulta.</label>
    <button type='submit'>Registrar y calificar consulta</button><small>En el piloto, Umbral no enviará mensajes automáticamente desde este formulario.</small></form></main></body></html>"""
    return HttpResponse(html, content_type="text/html; charset=utf-8")


def _normalize_manual_phone(value: str) -> str:
    normalized = _normalize_phone(value)
    if normalized:
        return normalized
    try:
        parsed = phonenumbers.parse((value or "").strip(), "AR")
        if phonenumbers.is_possible_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    return ""


def manual_intake(request: HttpRequest, token: str) -> HttpResponse:
    """Registra una consulta manual y ejecuta la misma calificación que WhatsApp."""
    try:
        cliente = Cliente.objects.filter(manual_intake_token=token, activo=True).first()
        if cliente is None:
            raise Cliente.DoesNotExist
    except Cliente.DoesNotExist:
        return HttpResponse("No encontrado", status=404)

    if request.method == "GET":
        return _manual_intake_page(request, cliente)
    if request.method != "POST":
        return HttpResponse(status=405)

    nombre = request.POST.get("nombre", "").strip()
    telefono = _normalize_manual_phone(request.POST.get("telefono", ""))
    consulta = request.POST.get("consulta", "").strip()
    if not nombre or not telefono or not consulta:
        return _manual_intake_page(request, cliente, "Completá nombre, teléfono y consulta.")
    if request.POST.get("consentimiento") != "si":
        return _manual_intake_page(request, cliente, "Confirmá el consentimiento para contacto por WhatsApp.")

    lead = Lead.objects.create(
        cliente=cliente,
        source=Lead.Source.MANUAL,
        nombre=nombre[:160],
        telefono_e164=telefono,
        consentimiento_whatsapp=True,
        payload_origen={"canal": "piloto_manual"},
    )
    Interaccion.objects.create(
        lead=lead,
        direccion=Interaccion.Direccion.ENTRANTE,
        tipo=Interaccion.Tipo.TEXTO,
        texto=consulta[:4000],
        estado_envio=Interaccion.EstadoEnvio.RECIBIDO,
    )
    try:
        _apply_calification(lead, _ask_califier(lead))
    except Exception:
        logger.exception("No se pudo calificar una consulta manual lead=%s", lead.pk)
        lead.estado = Lead.Estado.REQUIERE_HUMANO
        lead.proxima_accion = "revisar_manual"
        lead.motivos_calificacion = ["No se pudo completar la calificación automática."]
        lead.save(update_fields=["estado", "proxima_accion", "motivos_calificacion", "updated_at"])
    return _manual_intake_page(request, cliente, success=True)

LEAD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "mensaje_respuesta": {"type": "string"},
        "zona": {"type": ["string", "null"]},
        "tipo_obra": {
            "type": "string",
            "enum": ["obra_nueva", "reemplazo", "reforma", "cerramiento", "otro", "desconocido"],
        },
        "descripcion_obra": {"type": ["string", "null"]},
        "medidas_aproximadas": {"type": ["string", "null"]},
        "fotos_estado": {
            "type": "string",
            "enum": ["no_solicitadas", "solicitadas", "recibidas", "no_aplican"],
        },
        "rango_presupuesto": {
            "type": "string",
            "enum": ["bajo", "medio", "alto", "desconocido"],
        },
        "plazo": {
            "type": "string",
            "enum": ["0_30_dias", "31_90_dias", "mas_90_dias", "desconocido"],
        },
        "campos_faltantes": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["zona", "tipo_obra", "fotos_o_medidas", "plazo", "presupuesto"],
            },
        },
        "recomendacion": {
            "type": "string",
            "enum": ["calificando", "potencialmente_calificado", "no_calificado", "requiere_humano"],
        },
        "requiere_humano": {"type": "boolean"},
        "resumen_actualizado": {"type": "string"},
    },
    "required": [
        "mensaje_respuesta", "zona", "tipo_obra", "descripcion_obra",
        "medidas_aproximadas", "fotos_estado", "rango_presupuesto", "plazo",
        "campos_faltantes", "recomendacion", "requiere_humano", "resumen_actualizado",
    ],
}


def healthcheck(request: HttpRequest) -> JsonResponse:
    """Endpoint público mínimo para salud del proceso; no revela configuración."""
    return JsonResponse({"status": "ok"})


def _verify_meta_signature(request: HttpRequest) -> bool:
    """Verifica la firma sobre los bytes crudos, antes de interpretar JSON."""
    secret = settings.META_APP_SECRET.encode()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not secret or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret, request.body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def _verify_challenge(request: HttpRequest) -> HttpResponse:
    if (
        request.GET.get("hub.mode") == "subscribe"
        and hmac.compare_digest(
            request.GET.get("hub.verify_token", ""), settings.META_WEBHOOK_VERIFY_TOKEN
        )
    ):
        return HttpResponse(request.GET["hub.challenge"], content_type="text/plain")
    return HttpResponse("Forbidden", status=403)


def _request_with_retry(method: str, url: str, **kwargs: Any) -> requests.Response:
    """Reintenta sólo errores transitorios; nunca repite un 4xx de configuración."""
    kwargs.setdefault("timeout", HTTP_TIMEOUT)
    last_error: Exception | None = None
    for attempt in range(MAX_HTTP_ATTEMPTS):
        try:
            response = requests.request(method, url, **kwargs)
            if response.status_code not in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                return response
            last_error = requests.HTTPError(
                f"HTTP {response.status_code}: {response.text[:500]}", response=response
            )
        except requests.RequestException as exc:
            last_error = exc
        if attempt < MAX_HTTP_ATTEMPTS - 1:
            time.sleep(0.6 * (2**attempt))
    raise last_error or RuntimeError("La petición HTTP falló sin un error específico.")


def _graph_headers() -> dict[str, str]:
    if not settings.META_SYSTEM_USER_TOKEN:
        raise RuntimeError("META_SYSTEM_USER_TOKEN no está configurado.")
    return {"Authorization": f"Bearer {settings.META_SYSTEM_USER_TOKEN}"}


def _graph_url(resource: str, *, whatsapp: bool = False) -> str:
    version = settings.WHATSAPP_GRAPH_API_VERSION if whatsapp else settings.META_GRAPH_API_VERSION
    return f"https://graph.facebook.com/{version}/{resource.lstrip('/')}"


def _normalize_phone(value: str) -> str:
    """Normaliza un teléfono a E.164. Exige que Lead Ads solicite código país."""
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        parsed = phonenumbers.parse(raw, None)
        if phonenumbers.is_possible_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    # WhatsApp envía wa_id sin '+'. Para Lead Ads sin prefijo se rechaza: no adivinar país.
    digits = "".join(char for char in raw if char.isdigit())
    if raw.startswith("+") and len(digits) >= 8:
        return "+" + digits
    return ""


def _field_data_to_dict(field_data: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in field_data:
        values = field.get("values") or []
        if values:
            result[field.get("name", "").strip().lower()] = str(values[0]).strip()
    return result


def _first_field(data: dict[str, str], *names: str) -> str:
    return next((data[name] for name in names if data.get(name)), "")


def _send_whatsapp_template(lead: Lead, interaction: Interaccion | None = None) -> Interaccion:
    """Envía la plantilla de primer contacto; es válida fuera de la ventana de 24 h."""
    interaction = interaction or Interaccion.objects.create(
        lead=lead,
        direccion=Interaccion.Direccion.SALIENTE,
        tipo=Interaccion.Tipo.TEMPLATE,
        texto="Plantilla inicial de WhatsApp",
        estado_envio=Interaccion.EstadoEnvio.PENDIENTE,
    )
    payload = {
        "messaging_product": "whatsapp",
        "to": lead.telefono_e164.removeprefix("+"),
        "type": "template",
        "template": {
            "name": lead.cliente.whatsapp_template_inicial,
            "language": {"code": "es_AR"},
            "components": [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": lead.nombre or ""},
                    {"type": "text", "text": lead.cliente.nombre},
                ],
            }],
        },
    }
    try:
        response = _request_with_retry(
            "POST",
            _graph_url(f"{lead.cliente.whatsapp_phone_number_id}/messages", whatsapp=True),
            headers={**_graph_headers(), "Content-Type": "application/json"},
            json=payload,
        ).json()
        interaction.meta_message_id = (response.get("messages") or [{}])[0].get("id")
        interaction.estado_envio = Interaccion.EstadoEnvio.ENVIADO
        interaction.error_proveedor = ""
        interaction.save(update_fields=["meta_message_id", "estado_envio", "error_proveedor"])
        lead.estado = Lead.Estado.CONTACTADO
        lead.last_message_at = timezone.now()
        lead.save(update_fields=["estado", "last_message_at", "updated_at"])
    except Exception as exc:  # La acción manual de Admin permite reintentar este caso.
        logger.exception("No se pudo enviar plantilla inicial a lead=%s", lead.pk)
        interaction.estado_envio = Interaccion.EstadoEnvio.FALLIDO
        interaction.error_proveedor = str(exc)[:2000]
        interaction.save(update_fields=["estado_envio", "error_proveedor"])
    return interaction


def _send_whatsapp_text(lead: Lead, text: str) -> Interaccion:
    """Sólo se usa como respuesta inmediata a un mensaje entrante del cliente."""
    interaction = Interaccion.objects.create(
        lead=lead,
        direccion=Interaccion.Direccion.SALIENTE,
        tipo=Interaccion.Tipo.TEXTO,
        texto=text,
        estado_envio=Interaccion.EstadoEnvio.PENDIENTE,
    )
    try:
        response = _request_with_retry(
            "POST",
            _graph_url(f"{lead.cliente.whatsapp_phone_number_id}/messages", whatsapp=True),
            headers={**_graph_headers(), "Content-Type": "application/json"},
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": lead.telefono_e164.removeprefix("+"),
                "type": "text",
                "text": {"preview_url": False, "body": text},
            },
        ).json()
        interaction.meta_message_id = (response.get("messages") or [{}])[0].get("id")
        interaction.estado_envio = Interaccion.EstadoEnvio.ENVIADO
        interaction.save(update_fields=["meta_message_id", "estado_envio"])
    except Exception as exc:
        logger.exception("No se pudo responder WhatsApp a lead=%s", lead.pk)
        interaction.estado_envio = Interaccion.EstadoEnvio.FALLIDO
        interaction.error_proveedor = str(exc)[:2000]
        interaction.save(update_fields=["estado_envio", "error_proveedor"])
    return interaction


def _califier_instructions(cliente: Cliente) -> str:
    return f"""Sos el asistente virtual de ventas de {cliente.nombre}, una carpintería de
aberturas de aluminio, PVC y cerramientos ubicada en Argentina.

Tu único objetivo es recopilar información para determinar si la consulta merece
una visita técnica. No cotizás, no inventás precios, no prometés plazos ni das
asesoramiento técnico definitivo.

Información comercial:
- Zonas cubiertas: {', '.join(cliente.zonas_cobertura) or 'no configuradas'}
- Tipos de obra aceptados: {', '.join(cliente.tipos_obra_aceptados) or 'no configurados'}
- Presupuesto mínimo orientativo: {cliente.presupuesto_minimo or 'no informado'} {cliente.moneda}

Reglas:
1. Escribí español rioplatense, cordial y breve; hacé sólo una pregunta por mensaje.
2. Priorizá: zona, tipo de obra, fotos o medidas aproximadas, plazo y presupuesto.
3. Antes de formular una pregunta, revisá toda la ficha y la conversación. Nunca
   preguntes ni incluyas en campos_faltantes un dato que ya esté explícito. Por
   ejemplo, "cambiar ventanas" implica tipo_obra="reemplazo".
4. Para aberturas y cerramientos, fotos o medidas aproximadas siempre son útiles.
   Usá fotos_estado="no_aplican" sólo si el prospecto explica expresamente que no
   hay ninguna superficie, abertura o proyecto que evaluar.
5. requiere_humano sólo puede ser true si el prospecto pide explícitamente hablar
   con una persona, expresa enojo, plantea una urgencia real de menos de 48 horas
   o formula una consulta técnica que no se puede responder sin un especialista.
   No lo uses por falta de datos, por un plazo de 30 días ni por una consulta común.
6. Si piden precio, explicá que depende de medidas, sistema, vidrio y relevamiento;
   solicitá el dato faltante más importante.
7. No pidas DNI, datos bancarios, salud ni información innecesaria.
8. No afirmes que un lead está calificado: esa decisión es del backend.
9. Extraé únicamente información que esté en la conversación o contexto. Nunca inventes.
Devolvé exclusivamente el JSON del esquema indicado."""


def _conversation_context(lead: Lead) -> str:
    turns = lead.interacciones.order_by("-created_at")[:8]
    history = list(reversed(turns))
    lines = [
        f"Ficha actual: zona={lead.zona or 'desconocida'}; tipo_obra={lead.tipo_obra}; "
        f"medidas={lead.medidas_aproximadas or 'desconocidas'}; plazo={lead.plazo}; "
        f"presupuesto={lead.rango_presupuesto}; fotos_recibidas={bool(lead.fotos)}."
    ]
    for turn in history:
        who = "Prospecto" if turn.direccion == Interaccion.Direccion.ENTRANTE else "Asistente"
        if turn.texto:
            lines.append(f"{who}: {turn.texto}")
        elif turn.tipo == Interaccion.Tipo.IMAGEN:
            lines.append(f"{who}: [envió una foto de la obra]")
    return "\n".join(lines)


def _ask_califier(lead: Lead) -> dict[str, Any]:
    client = OpenAI()
    response = client.responses.create(
        model=settings.OPENAI_MODEL,
        store=False,
        instructions=_califier_instructions(lead.cliente),
        input=_conversation_context(lead),
        text={
            "format": {
                "type": "json_schema",
                "name": "calificacion_lead_umbral",
                "strict": True,
                "schema": LEAD_SCHEMA,
            }
        },
    )
    return json.loads(response.output_text)


def _normalise_for_comparison(value: str) -> str:
    return " ".join((value or "").casefold().strip().split())


def _has_human_escalation_trigger(lead: Lead) -> bool:
    """Evita que una clasificación conservadora de IA frene consultas normales."""
    recent_text = " ".join(
        lead.interacciones.filter(direccion=Interaccion.Direccion.ENTRANTE)
        .order_by("-created_at")
        .values_list("texto", flat=True)[:2]
    ).casefold()
    explicit_requests = ("persona", "humano", "asesor", "vendedor", "llamame", "llámenme")
    frustration = ("reclamo", "queja", "estafa", "inútil", "pésimo", "pesimo")
    immediate_urgency = ("urgente hoy", "urgente mañana", "urgente manana", "menos de 48")
    return any(term in recent_text for term in (*explicit_requests, *frustration, *immediate_urgency))


def _next_message_for_lead(lead: Lead, ai_message: str = "") -> str:
    """El flujo comercial es determinístico; la IA sólo interpreta lenguaje libre."""
    if lead.estado == Lead.Estado.REQUIERE_HUMANO:
        return "Gracias. Le aviso a un asesor para que continúe con tu consulta."
    if lead.estado == Lead.Estado.NO_CALIFICADO:
        return "Gracias por contactarnos. Por el momento no realizamos relevamientos en esa zona."
    if lead.estado == Lead.Estado.CALIFICANDO:
        questions = {
            "zona": "¿En qué localidad o barrio se realiza la obra?",
            "tipo_obra": "¿Es una obra nueva, una reforma o un reemplazo de aberturas existentes?",
            "fotos_o_medidas": (
                "¿Podés enviarnos dos o tres fotos del lugar? Si ya tenés medidas aproximadas, "
                "también nos sirven para orientarte."
            ),
            "plazo": "¿Para cuándo te gustaría tener resuelto el proyecto?",
            "presupuesto": (
                "Para confirmar si el proyecto encaja con nuestro servicio, ¿qué rango de inversión "
                "tenés previsto? Es sólo orientativo; el presupuesto final depende del relevamiento."
            ),
        }
        if lead.campos_faltantes:
            return questions[lead.campos_faltantes[0]]
    if lead.estado == Lead.Estado.CALIFICADO:
        return (
            "Perfecto, ya tenemos los datos principales. ¿Querés que coordinemos un relevamiento técnico?"
        )
    return ai_message or "Gracias por la información. Un asesor va a revisar tu consulta."


def _apply_calification(lead: Lead, result: dict[str, Any]) -> None:
    """Actualiza la ficha con IA, pero aplica reglas de negocio determinísticas."""
    unknown_values = {"", "desconocido", "desconocida", "desconocidos", "desconocidas", "no informado", "no informada", "no informados", "no informadas", "no disponible", "n/a", "na", "none", "null"}
    for field in ("zona", "tipo_obra", "descripcion_obra", "medidas_aproximadas", "rango_presupuesto", "plazo"):
        value = result.get(field)
        normalized_value = _normalise_for_comparison(str(value or ""))
        if value and normalized_value not in unknown_values:
            setattr(lead, field, value)

    if result.get("fotos_estado") == "recibidas" and not lead.fotos:
        # La media real se persiste al entrar el webhook; esto sólo evita una afirmación falsa.
        result["fotos_estado"] = "solicitadas"

    # El modelo interpreta lenguaje libre; el backend es la fuente de verdad sobre
    # qué falta. Así evitamos pedir por segunda vez datos que ya están en la ficha.
    known = {
        "zona": bool(lead.zona),
        "tipo_obra": lead.tipo_obra != "desconocido",
        "fotos_o_medidas": bool(lead.fotos or lead.medidas_aproximadas),
        "plazo": lead.plazo != "desconocido",
        "presupuesto": lead.rango_presupuesto != "desconocido",
    }
    missing = [field for field, is_known in known.items() if not is_known]
    lead.campos_faltantes = missing
    lead.resumen_ia = result.get("resumen_actualizado", "")
    lead.motivos_calificacion = []

    covered = {
        _normalise_for_comparison(zone) for zone in lead.cliente.zonas_cobertura
    }
    zone_known = bool(lead.zona)
    in_coverage = _normalise_for_comparison(lead.zona) in covered if zone_known else None

    requires_human = result.get("requiere_humano") and _has_human_escalation_trigger(lead)
    if requires_human:
        lead.estado = Lead.Estado.REQUIERE_HUMANO
        lead.proxima_accion = "avisar_vendedor"
        lead.motivos_calificacion = ["La IA solicitó intervención humana."]
    elif zone_known and covered and not in_coverage:
        lead.estado = Lead.Estado.NO_CALIFICADO
        lead.proxima_accion = "cerrar"
        lead.motivos_calificacion = ["La zona declarada está fuera de cobertura."]
    elif missing or result.get("recomendacion") == "calificando":
        lead.estado = Lead.Estado.CALIFICANDO
        lead.proxima_accion = "preguntar"
    elif all([
        lead.zona,
        lead.tipo_obra != "desconocido",
        lead.plazo != "desconocido",
        lead.rango_presupuesto != "desconocido",
    ]):
        lead.estado = Lead.Estado.CALIFICADO
        lead.proxima_accion = "agendar"
        lead.motivos_calificacion = ["Cumple los datos mínimos; confirmar agenda manualmente."]
    else:
        lead.estado = Lead.Estado.CALIFICANDO
        lead.proxima_accion = "preguntar"
    lead.last_message_at = timezone.now()
    lead.save()


@csrf_exempt
def leadgen_webhook(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return _verify_challenge(request)
    if request.method != "POST":
        return HttpResponse(status=405)
    if not _verify_meta_signature(request):
        return HttpResponse("Invalid signature", status=403)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "leadgen":
                continue
            value = change.get("value") or {}
            meta_lead_id = str(value.get("leadgen_id", ""))
            page_id, form_id = str(value.get("page_id", "")), str(value.get("form_id", ""))
            if not meta_lead_id:
                continue
            event, created = WebhookEvent.objects.get_or_create(
                provider=WebhookEvent.Provider.META_LEAD_ADS,
                external_event_id=meta_lead_id,
                defaults={"payload": value},
            )
            if not created:
                continue
            try:
                cliente = Cliente.objects.get(meta_page_id=page_id, meta_form_id=form_id, activo=True)
                lead_payload = _request_with_retry(
                    "GET",
                    _graph_url(meta_lead_id),
                    headers=_graph_headers(),
                    params={"fields": "field_data,created_time,ad_id,form_id"},
                ).json()
                fields = _field_data_to_dict(lead_payload.get("field_data", []))
                phone = _normalize_phone(_first_field(fields, "phone_number", "telefono", "whatsapp"))
                if not phone:
                    raise ValueError("El formulario no entregó un teléfono E.164 válido.")
                consent = _first_field(fields, "consentimiento_whatsapp", "whatsapp_opt_in").casefold()
                with transaction.atomic():
                    lead, lead_created = Lead.objects.get_or_create(
                        cliente=cliente,
                        meta_lead_id=meta_lead_id,
                        defaults={
                            "source": Lead.Source.META_LEAD_AD,
                            "nombre": _first_field(fields, "full_name", "nombre_completo", "name"),
                            "telefono_e164": phone,
                            "email": _first_field(fields, "email"),
                            "consentimiento_whatsapp": consent in {"si", "sí", "yes", "true", "1"},
                            "payload_origen": {"webhook": value, "lead": lead_payload},
                        },
                    )
                    if not lead_created:
                        event.status = WebhookEvent.Status.PROCESSED
                        event.processed_at = timezone.now()
                        event.save(update_fields=["status", "processed_at"])
                        continue
                    event.status = WebhookEvent.Status.PROCESSED
                    event.processed_at = timezone.now()
                    event.save(update_fields=["status", "processed_at"])
                if not lead.consentimiento_whatsapp:
                    lead.estado = Lead.Estado.REQUIERE_HUMANO
                    lead.motivos_calificacion = ["No se recibió consentimiento de WhatsApp."]
                    lead.save(update_fields=["estado", "motivos_calificacion", "updated_at"])
                else:
                    _send_whatsapp_template(lead)
            except Exception as exc:
                logger.exception("Error procesando Meta Lead Ad id=%s", meta_lead_id)
                event.status = WebhookEvent.Status.FAILED
                event.error = str(exc)[:2000]
                event.save(update_fields=["status", "error"])
    return JsonResponse({"status": "ok"})


def _process_statuses(statuses: list[dict[str, Any]]) -> None:
    status_map = {
        "sent": Interaccion.EstadoEnvio.ENVIADO,
        "delivered": Interaccion.EstadoEnvio.ENTREGADO,
        "read": Interaccion.EstadoEnvio.LEIDO,
        "failed": Interaccion.EstadoEnvio.FALLIDO,
    }
    for item in statuses:
        message_id, status = item.get("id"), status_map.get(item.get("status"))
        if message_id and status:
            Interaccion.objects.filter(meta_message_id=message_id).update(estado_envio=status)


@csrf_exempt
def whatsapp_webhook(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return _verify_challenge(request)
    if request.method != "POST":
        return HttpResponse(status=405)
    if not _verify_meta_signature(request):
        return HttpResponse("Invalid signature", status=403)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            _process_statuses(value.get("statuses") or [])
            metadata = value.get("metadata") or {}
            phone_number_id = str(metadata.get("phone_number_id", ""))
            messages = value.get("messages") or []
            if not messages:
                continue
            try:
                cliente = Cliente.objects.get(whatsapp_phone_number_id=phone_number_id, activo=True)
            except Cliente.DoesNotExist:
                logger.warning("Mensaje de WhatsApp para número no configurado: %s", phone_number_id)
                continue
            for message in messages:
                message_id = message.get("id")
                sender = _normalize_phone("+" + str(message.get("from", "")))
                if not message_id or not sender:
                    continue
                event, created = WebhookEvent.objects.get_or_create(
                    provider=WebhookEvent.Provider.WHATSAPP,
                    external_event_id=f"message:{message_id}",
                    defaults={"payload": message},
                )
                if not created:
                    continue
                try:
                    lead, _ = Lead.objects.get_or_create(
                        cliente=cliente,
                        telefono_e164=sender,
                        defaults={"source": Lead.Source.WHATSAPP, "estado": Lead.Estado.CALIFICANDO},
                    )
                    message_type = message.get("type", "text")
                    text = (message.get("text") or {}).get("body", "")
                    media: dict[str, Any] = {}
                    interaction_type = Interaccion.Tipo.TEXTO
                    if message_type == "image":
                        interaction_type = Interaccion.Tipo.IMAGEN
                        media = message.get("image") or {}
                        text = "[Foto recibida]"
                        lead.fotos = [*lead.fotos, media]
                        lead.save(update_fields=["fotos", "updated_at"])
                    elif message_type != "text":
                        text = f"[Mensaje no soportado: {message_type}]"

                    incoming, incoming_created = Interaccion.objects.get_or_create(
                        meta_message_id=message_id,
                        defaults={
                            "lead": lead,
                            "direccion": Interaccion.Direccion.ENTRANTE,
                            "tipo": interaction_type,
                            "texto": text,
                            "media": media,
                            "estado_envio": Interaccion.EstadoEnvio.RECIBIDO,
                        },
                    )
                    if not incoming_created:
                        continue
                    result = _ask_califier(lead)
                    incoming.respuesta_ia = result
                    incoming.save(update_fields=["respuesta_ia"])
                    _apply_calification(lead, result)
                    _send_whatsapp_text(lead, _next_message_for_lead(lead, result.get("mensaje_respuesta", "")))
                    event.status = WebhookEvent.Status.PROCESSED
                    event.processed_at = timezone.now()
                    event.save(update_fields=["status", "processed_at"])
                except Exception as exc:
                    logger.exception("Error procesando WhatsApp message=%s", message_id)
                    event.status = WebhookEvent.Status.FAILED
                    event.error = str(exc)[:2000]
                    event.save(update_fields=["status", "error"])
    return JsonResponse({"status": "ok"})
