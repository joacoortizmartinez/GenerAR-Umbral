"""Dashboard privado V1 de Umbral."""

from datetime import timedelta

from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.utils.html import escape

from .models import Cliente, Lead

STATUS_STYLE = {
    Lead.Estado.NUEVO: "gray", Lead.Estado.CONTACTADO: "blue",
    Lead.Estado.CALIFICANDO: "blue", Lead.Estado.CALIFICADO: "green",
    Lead.Estado.REQUIERE_HUMANO: "orange", Lead.Estado.VISITA_AGENDADA: "purple",
    Lead.Estado.VISITA_ASISTIDA: "teal", Lead.Estado.NO_CALIFICADO: "red",
    Lead.Estado.PERDIDO: "red",
}


def _reply(lead: Lead) -> str:
    if lead.estado == Lead.Estado.REQUIERE_HUMANO:
        return "Gracias. Le aviso a un asesor para que continúe con tu consulta."
    if lead.estado == Lead.Estado.NO_CALIFICADO:
        return "Gracias por contactarnos. Por el momento no realizamos relevamientos en esa zona."
    if lead.estado == Lead.Estado.CALIFICANDO:
        questions = {
            "zona": "¿En qué localidad o barrio se realiza la obra?",
            "tipo_obra": "¿Es una obra nueva, una reforma o un reemplazo de aberturas existentes?",
            "fotos_o_medidas": "¿Podés enviarnos dos o tres fotos del lugar? Si ya tenés medidas aproximadas, también nos sirven para orientarte.",
            "plazo": "¿Para cuándo te gustaría tener resuelto el proyecto?",
            "presupuesto": "Para confirmar si el proyecto encaja con nuestro servicio, ¿qué rango de inversión tenés previsto? Es sólo orientativo; el presupuesto final depende del relevamiento.",
        }
        if lead.campos_faltantes:
            return questions.get(lead.campos_faltantes[0], "Gracias por la información. Un asesor va a revisar tu consulta.")
    if lead.estado == Lead.Estado.CALIFICADO:
        return "Perfecto, ya tenemos los datos principales. ¿Querés que coordinemos un relevamiento técnico?"
    return "Gracias por la información. Un asesor va a revisar tu consulta."


def _initials(name: str) -> str:
    words = (name or "Consulta").split()
    return "".join(word[0].upper() for word in words[:2] if word) or "C"


def _lead_row(lead: Lead) -> str:
    missing = "".join(
        f"<span class='missing'>{escape(value.replace('_', ' '))}</span>"
        for value in lead.campos_faltantes or []
    )
    return f"""<details class='lead-row'>
      <summary>
        <div class='identity'><span class='avatar'>{escape(_initials(lead.nombre))}</span><div><b>{escape(lead.nombre or 'Consulta sin nombre')}</b><small>{escape(lead.telefono_e164)} · {escape(lead.zona or 'Zona pendiente')}</small></div></div>
        <p class='lead-summary'>{escape(lead.resumen_ia or 'Todavía no hay resumen automático para esta consulta.')}</p>
        <span class='status {STATUS_STYLE.get(lead.estado, 'blue')}'>{escape(lead.get_estado_display())}</span>
        <span class='chevron'>⌄</span>
      </summary>
      <div class='lead-detail'>
        <div class='detail-grid'>
          <div><span>Tipo de obra</span><b>{escape((lead.tipo_obra or 'desconocido').replace('_', ' ').capitalize())}</b></div>
          <div><span>Plazo</span><b>{escape((lead.plazo or 'Sin plazo').replace('_', ' '))}</b></div>
          <div><span>Medidas</span><b>{escape(lead.medidas_aproximadas or 'No informadas')}</b></div>
          <div><span>Presupuesto</span><b>{escape(lead.rango_presupuesto or 'Desconocido')}</b></div>
        </div>
        <div class='notes'><b>Detalle de obra</b><p>{escape(lead.descripcion_obra or 'No se ingresó una descripción adicional.')}</p></div>
        {f"<div class='missing-row'><b>Datos pendientes</b>{missing}</div>" if missing else "<div class='complete'>✓ Datos principales completos para avanzar</div>"}
        <div class='suggestion'><div><span>PRÓXIMA ACCIÓN</span><b>{escape(lead.proxima_accion.replace('_', ' ').capitalize())}</b></div><button type='button' class='copy' data-copy='{escape(_reply(lead))}'>Copiar respuesta sugerida</button></div>
      </div>
    </details>"""


def _page(cliente: Cliente, leads: list[Lead], metrics: dict[str, int], active_filter: str) -> HttpResponse:
    filter_items = "".join(
        f"<a class='filter {'active' if value == active_filter else ''}' href='?estado={escape(value)}'>{escape(label)}</a>"
        for value, label in [("", "Todas"), *Lead.Estado.choices]
    )
    rows = "".join(_lead_row(lead) for lead in leads)
    if not rows:
        rows = "<div class='empty'><b>Todavía no hay consultas.</b><br>Cuando se cargue una consulta durante el piloto aparecerá acá con su resumen y la acción recomendada.</div>"
    html = f"""<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><meta name='robots' content='noindex,nofollow'>
    <title>Panel | {escape(cliente.nombre)} · Umbral</title>
    <style>
    :root{{--ink:#16263d;--navy:#0d1b2e;--teal:#0b9c9c;--cyan:#47d4d4;--muted:#718096;--line:#e7edf3;--bg:#f6f8fb;--panel:#fff;--good:#097a54;--orange:#a85b05}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Arial,sans-serif}}.shell{{max-width:1240px;margin:auto;padding:0 24px 42px}}header{{background:var(--navy);color:#fff}}.header-inner{{max-width:1240px;margin:auto;padding:20px 24px 25px}}.topline{{display:flex;align-items:center;justify-content:space-between}}.brand{{color:var(--cyan);font-size:.74rem;font-weight:800;letter-spacing:.16em}}.pilot{{font-size:.82rem;color:#aebfd2;background:#17304e;padding:6px 9px;border-radius:99px}}h1{{font-size:clamp(1.7rem,3vw,2.35rem);letter-spacing:-.04em;margin:22px 0 6px}}.subtitle{{color:#b9c8d7;margin:0;line-height:1.45}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:-17px}}.metric{{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:15px 17px;box-shadow:0 6px 16px rgba(18,38,61,.05)}}.metric b{{font-size:1.65rem;letter-spacing:-.05em;display:block}}.metric span{{display:block;margin-top:4px;color:var(--muted);font-size:.82rem}}.workspace{{display:grid;grid-template-columns:208px 1fr;gap:20px;margin-top:33px}}aside{{height:max-content;background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:12px}}.side-label{{color:#8a9aad;font-size:.72rem;font-weight:800;letter-spacing:.08em;padding:4px 8px 9px}}.filter{{display:block;text-decoration:none;color:#50647b;padding:9px 8px;border-radius:7px;font-size:.86rem;font-weight:700;margin:2px 0}}.filter:hover{{background:#f1f6f8}}.filter.active{{background:#e9fbfa;color:#087e7e}}.content-header{{display:flex;align-items:end;justify-content:space-between;margin:0 0 12px}}h2{{font-size:1.27rem;margin:0 0 4px}}.content-header p{{color:var(--muted);font-size:.88rem;margin:0}}.count{{font-size:.8rem;color:var(--muted)}}.lead-list{{background:var(--panel);border:1px solid var(--line);border-radius:11px;overflow:hidden}}.lead-row{{border-bottom:1px solid var(--line)}}.lead-row:last-child{{border-bottom:0}}summary{{display:grid;grid-template-columns:minmax(175px,.9fr) minmax(240px,1.8fr) 115px 16px;gap:16px;align-items:center;padding:17px 18px;cursor:pointer;list-style:none}}summary::-webkit-details-marker{{display:none}}summary:hover{{background:#fbfdff}}.identity{{display:flex;gap:10px;align-items:center;min-width:0}}.avatar{{display:grid;place-items:center;width:34px;height:34px;border-radius:50%;flex:0 0 34px;background:#e4f6f5;color:#087f7c;font-weight:800;font-size:.78rem}}.identity b{{display:block;font-size:.93rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.identity small{{display:block;color:var(--muted);font-size:.76rem;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.lead-summary{{margin:0;color:#5b6f85;font-size:.85rem;line-height:1.38;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.status{{justify-self:start;font-size:.72rem;font-weight:800;padding:6px 8px;border-radius:99px;white-space:nowrap}}.gray{{background:#edf1f5;color:#4c6075}}.blue{{background:#e7f4fb;color:#16759a}}.green{{background:#e0f7ec;color:#087251}}.orange{{background:#fff2db;color:#a85b05}}.purple{{background:#eee9ff;color:#5845a8}}.teal{{background:#ddf5f1;color:#08766f}}.red{{background:#fbe8eb;color:#aa3948}}.chevron{{color:#8a9aac;font-size:1.2rem;text-align:center}}details[open] .chevron{{transform:rotate(180deg)}}.lead-detail{{background:#fbfcfe;border-top:1px solid var(--line);padding:17px 18px 18px;margin:0 10px 10px;border-radius:0 0 9px 9px}}.detail-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.detail-grid div,.notes{{border:1px solid var(--line);background:#fff;border-radius:8px;padding:10px}}.detail-grid span,.suggestion span{{display:block;color:#8291a3;font-size:.68rem;font-weight:800;letter-spacing:.05em;text-transform:uppercase;margin-bottom:5px}}.detail-grid b{{font-size:.82rem;line-height:1.35}}.notes{{margin-top:10px}}.notes b{{font-size:.8rem}}.notes p{{margin:5px 0 0;color:#5b6f85;font-size:.84rem;line-height:1.4}}.missing-row{{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-top:11px;font-size:.8rem;color:var(--orange)}}.missing{{background:#fff1db;border-radius:5px;padding:4px 6px}}.complete{{margin-top:11px;color:var(--good);font-size:.82rem;font-weight:700}}.suggestion{{display:flex;justify-content:space-between;align-items:center;gap:16px;border-top:1px solid var(--line);margin-top:14px;padding-top:14px}}.suggestion b{{font-size:.86rem}}.copy{{border:0;border-radius:7px;background:var(--teal);color:#fff;padding:9px 11px;font-weight:800;cursor:pointer;font-size:.8rem}}.copy:hover{{background:#087f7f}}.copy.copied{{background:#087251}}.empty{{margin:18px;border:1px dashed #c5d1dc;border-radius:9px;padding:34px;text-align:center;color:var(--muted);line-height:1.6}}.legal{{max-width:1240px;margin:0 auto;padding:0 24px 28px;color:#8291a3;font-size:.77rem}}@media(max-width:780px){{.shell,.header-inner,.legal{{padding-left:15px;padding-right:15px}}.workspace{{grid-template-columns:1fr;gap:13px;margin-top:24px}}aside{{display:flex;gap:7px;overflow:auto;padding:8px}}.side-label{{display:none}}.filter{{white-space:nowrap;margin:0}}.metrics{{grid-template-columns:repeat(2,1fr);gap:8px}}summary{{grid-template-columns:1fr auto;gap:10px;padding:15px}}.lead-summary{{grid-column:1/-1;grid-row:2}}.chevron{{grid-column:2;grid-row:1}}.detail-grid{{grid-template-columns:1fr 1fr}}.suggestion{{align-items:flex-start;flex-direction:column}}}}</style></head>
    <body><header><div class='header-inner'><div class='topline'><span class='brand'>UMBRAL · PANEL DE CONSULTAS</span><span class='pilot'>Piloto privado</span></div><h1>{escape(cliente.nombre)}</h1><p class='subtitle'>Consultas ordenadas para decidir rápido qué responder, presupuestar o visitar.</p></div></header>
    <main class='shell'><section class='metrics'><div class='metric'><b>{metrics['received']}</b><span>Consultas - últimos 30 días</span></div><div class='metric'><b>{metrics['in_progress']}</b><span>En seguimiento</span></div><div class='metric'><b>{metrics['ready']}</b><span>Listas para avanzar</span></div><div class='metric'><b>{metrics['visits']}</b><span>Visitas técnicas</span></div></section>
    <section class='workspace'><aside><div class='side-label'>FILTRAR CONSULTAS</div>{filter_items}</aside><div><div class='content-header'><div><h2>Bandeja de consultas</h2><p>Abrí una consulta para ver su ficha y respuesta sugerida.</p></div><span class='count'>{len(leads)} visibles</span></div><section class='lead-list'>{rows}</section></div></section></main>
    <div class='legal'>Umbral organiza las consultas; la decisión comercial y técnica siempre permanece en tu equipo.</div>
    <script>function copyFallback(text){{var area=document.createElement('textarea');area.value=text;area.setAttribute('readonly','');area.style.position='fixed';area.style.opacity='0';document.body.appendChild(area);area.select();var ok=document.execCommand('copy');document.body.removeChild(area);return ok}}document.querySelectorAll('.copy').forEach(function(button){{button.addEventListener('click',function(){{var text=button.dataset.copy;var done=function(){{button.textContent='Respuesta copiada';button.classList.add('copied');setTimeout(function(){{button.textContent='Copiar respuesta sugerida';button.classList.remove('copied')}},1800)}};if(navigator.clipboard&&window.isSecureContext){{navigator.clipboard.writeText(text).then(done).catch(function(){{if(copyFallback(text))done()}})}}else if(copyFallback(text)){{done()}}}})}})</script></body></html>"""
    return HttpResponse(html, content_type="text/html; charset=utf-8")


def client_dashboard(request: HttpRequest, token: str) -> HttpResponse:
    cliente = Cliente.objects.filter(manual_intake_token=token, activo=True).first()
    if cliente is None:
        return HttpResponse("No encontrado", status=404)

    leads = Lead.objects.filter(cliente=cliente).order_by("-last_message_at", "-created_at")
    active_filter = request.GET.get("estado", "")
    if active_filter in {value for value, _label in Lead.Estado.choices}:
        leads = leads.filter(estado=active_filter)
    elif active_filter:
        active_filter = ""

    recent = Lead.objects.filter(cliente=cliente, created_at__gte=timezone.now() - timedelta(days=30))
    metrics = {
        "received": recent.count(),
        "in_progress": recent.filter(estado__in=[Lead.Estado.NUEVO, Lead.Estado.CONTACTADO, Lead.Estado.CALIFICANDO, Lead.Estado.REQUIERE_HUMANO]).count(),
        "ready": recent.filter(estado__in=[Lead.Estado.CALIFICADO, Lead.Estado.VISITA_AGENDADA]).count(),
        "visits": recent.filter(estado__in=[Lead.Estado.VISITA_AGENDADA, Lead.Estado.VISITA_ASISTIDA]).count(),
    }
    return _page(cliente, list(leads[:60]), metrics, active_filter)
