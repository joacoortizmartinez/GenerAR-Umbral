from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.contrib import admin, messages
from django.core.management import call_command
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import Cliente, Interaccion, Lead, SolicitudPiloto, WebhookEvent
from .views import _send_whatsapp_template


class ColaOperativaFilter(admin.SimpleListFilter):
    title = "cola operativa"
    parameter_name = "cola"

    def lookups(self, request, model_admin):
        return (("humano", "Requiere humano"), ("agendada", "Visita agendada"), ("fallido", "Plantilla fallida"))

    def queryset(self, request, queryset):
        if self.value() == "humano":
            return queryset.filter(estado=Lead.Estado.REQUIERE_HUMANO)
        if self.value() == "agendada":
            return queryset.filter(estado=Lead.Estado.VISITA_AGENDADA)
        if self.value() == "fallido":
            return queryset.filter(interacciones__estado_envio=Interaccion.EstadoEnvio.FALLIDO).distinct()
        return queryset

@admin.register(SolicitudPiloto)
class SolicitudPilotoAdmin(admin.ModelAdmin):
    list_display = ("negocio", "nombre", "telefono_e164", "ciudad", "rubro", "volumen_consultas", "estado", "created_at")
    list_filter = ("estado", "rubro", "volumen_consultas")
    search_fields = ("negocio", "nombre", "telefono_e164", "ciudad", "email")
    readonly_fields = ("id", "created_at", "updated_at")
    list_editable = ("estado",)

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("nombre", "telefono_e164", "cliente", "estado", "zona", "tipo_obra", "plazo", "created_at")
    list_filter = ("estado", "cliente", "source", ColaOperativaFilter)
    search_fields = ("nombre", "telefono_e164", "zona", "resumen_ia")
    readonly_fields = ("id", "created_at", "updated_at", "last_message_at", "visita_asistida_at")
    actions = ("reenviar_plantilla", "marcar_visita_asistida")

    @admin.action(description="Reenviar plantilla de WhatsApp a leads seleccionados")
    def reenviar_plantilla(self, request, queryset):
        sent = 0
        for lead in queryset.filter(consentimiento_whatsapp=True):
            interaction = _send_whatsapp_template(lead)
            sent += interaction.estado_envio == Interaccion.EstadoEnvio.ENVIADO
        self.message_user(request, f"Plantillas enviadas: {sent}.", messages.SUCCESS if sent else messages.WARNING)

    @admin.action(description="Marcar visitas seleccionadas como asistidas")
    def marcar_visita_asistida(self, request, queryset):
        count = queryset.update(estado=Lead.Estado.VISITA_ASISTIDA, visita_asistida_at=timezone.now())
        self.message_user(request, f"{count} visita(s) marcada(s) como asistidas.", messages.SUCCESS)


def _weekly_summary(cliente: Cliente) -> str:
    since = timezone.now() - timedelta(days=7)
    leads = cliente.leads.filter(created_at__gte=since)
    total = leads.count()
    calificados = leads.filter(estado__in=[Lead.Estado.CALIFICADO, Lead.Estado.VISITA_AGENDADA, Lead.Estado.VISITA_ASISTIDA]).count()
    agendadas = leads.filter(estado=Lead.Estado.VISITA_AGENDADA).count()
    asistidas = leads.filter(estado=Lead.Estado.VISITA_ASISTIDA).count()
    humanos = leads.filter(estado=Lead.Estado.REQUIERE_HUMANO).count()
    conversion = round((calificados / total * 100), 1) if total else 0
    return f"""# Reporte semanal — {cliente.nombre}

Período: últimos 7 días, hasta {timezone.localtime():%d/%m/%Y %H:%M}

| Métrica | Resultado |
|---|---:|
| Consultas nuevas | {total} |
| Calificadas o mejor | {calificados} |
| Tasa de calificación | {conversion}% |
| Visitas agendadas | {agendadas} |
| Visitas asistidas | {asistidas} |
| Casos que requieren atención humana | {humanos} |

## Próxima acción

Revisar los casos pendientes de atención humana y confirmar las visitas agendadas.
"""


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    @admin.display(description="Enlace de derivación manual")
    def manual_intake_url(self, obj: Cliente):
        url = reverse("manual-intake", args=[obj.manual_intake_token])
        return format_html('<a href="{}" target="_blank" rel="noopener">Abrir formulario privado</a>', url)
    @admin.display(description="Dashboard del cliente")
    def client_dashboard_url(self, obj: Cliente):
        url = reverse("client-dashboard", args=[obj.manual_intake_token])
        return format_html('<a href="{}" target="_blank" rel="noopener">Abrir dashboard privado</a>', url)

    list_display = ("nombre", "contacto_nombre", "activo", "meta_page_id", "whatsapp_phone_number_id")
    readonly_fields = ("manual_intake_token", "manual_intake_url", "client_dashboard_url")
    list_filter = ("activo",)
    search_fields = ("nombre", "contacto_nombre", "contacto_whatsapp")
    actions = ("generar_resumen_semanal", "cargar_demo_dashboard")

    @admin.action(description="Cargar 12 consultas ficticias en Carpintería Demo")
    def cargar_demo_dashboard(self, request, queryset):
        demo_clients = queryset.filter(nombre="Carpintería Demo")
        if not demo_clients.exists():
            self.message_user(request, "Por seguridad, esta acción sólo funciona seleccionando Carpintería Demo.", messages.ERROR)
            return
        for cliente in demo_clients:
            call_command("seed_demo_dashboard", "--cliente", cliente.nombre, stdout=StringIO())
        self.message_user(request, "Demo cargada: ya podés abrir el dashboard privado.", messages.SUCCESS)

    @admin.action(description="Descargar reporte semanal Markdown")
    def generar_resumen_semanal(self, request, queryset):
        content = "\n\n---\n\n".join(_weekly_summary(cliente) for cliente in queryset)
        response = HttpResponse(content, content_type="text/markdown; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="umbral-reporte-semanal.md"'
        return response


@admin.register(Interaccion)
class InteraccionAdmin(admin.ModelAdmin):
    list_display = ("lead", "direccion", "tipo", "estado_envio", "created_at")
    list_filter = ("direccion", "tipo", "estado_envio", "lead__cliente")
    search_fields = ("lead__nombre", "lead__telefono_e164", "texto", "meta_message_id")
    readonly_fields = ("created_at",)


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("provider", "external_event_id", "status", "received_at", "processed_at")
    list_filter = ("provider", "status")
    search_fields = ("external_event_id", "error")
    readonly_fields = ("provider", "external_event_id", "payload", "status", "error", "received_at", "processed_at")
