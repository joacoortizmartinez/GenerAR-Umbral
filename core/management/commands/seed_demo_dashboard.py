from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import Cliente, Interaccion, Lead


DEMO_LEADS = [
    {
        "nombre": "Mariana López", "telefono": "+5491123456701", "estado": Lead.Estado.CALIFICANDO,
        "zona": "Pilar", "tipo": "reemplazo", "obra": "Cambio de cinco ventanas de aluminio en vivienda existente.",
        "medidas": "Pendientes", "plazo": "0_30_dias", "presupuesto": "desconocido",
        "faltantes": ["fotos_o_medidas", "presupuesto"], "accion": "preguntar",
        "resumen": "Quiere reemplazar cinco ventanas en Pilar durante este mes. Faltan fotos o medidas y presupuesto orientativo.",
    },
    {
        "nombre": "Estudio Arce", "telefono": "+5491123456702", "estado": Lead.Estado.CALIFICADO,
        "zona": "Tigre", "tipo": "obra_nueva", "obra": "Aberturas de PVC para casa nueva de dos plantas.",
        "medidas": "Planos y medidas preliminares enviados", "plazo": "31_90_dias", "presupuesto": "alto",
        "faltantes": [], "accion": "agendar",
        "resumen": "Obra nueva en Tigre con planos disponibles. Proyecto de buena escala y plazo de ejecución dentro de 90 días.",
    },
    {
        "nombre": "Javier Medina", "telefono": "+5491123456703", "estado": Lead.Estado.VISITA_AGENDADA,
        "zona": "San Isidro", "tipo": "cerramiento", "obra": "Cerramiento de galería con techo de vidrio.",
        "medidas": "Galería de 6 x 3 m", "plazo": "0_30_dias", "presupuesto": "medio",
        "faltantes": [], "accion": "confirmar_visita",
        "resumen": "Cerramiento de galería en San Isidro. Medidas informadas y visita técnica coordinada para confirmar sistema y vidrio.",
    },
    {
        "nombre": "Carla Romero", "telefono": "+5491123456704", "estado": Lead.Estado.REQUIERE_HUMANO,
        "zona": "Vicente López", "tipo": "reforma", "obra": "Consulta técnica por filtración en puerta balcón existente.",
        "medidas": "No informadas", "plazo": "0_30_dias", "presupuesto": "desconocido",
        "faltantes": ["fotos_o_medidas"], "accion": "avisar_vendedor",
        "resumen": "Consulta urgente por filtración. Solicitó hablar con un asesor para evaluar una reparación.",
    },
    {
        "nombre": "Lucas Fernández", "telefono": "+5491123456705", "estado": Lead.Estado.NO_CALIFICADO,
        "zona": "La Plata", "tipo": "reemplazo", "obra": "Cambio de una ventana de cocina.",
        "medidas": "120 x 100 cm", "plazo": "mas_90_dias", "presupuesto": "bajo",
        "faltantes": [], "accion": "cerrar",
        "resumen": "Consulta fuera de la zona de cobertura definida para este piloto.",
    },
    {
        "nombre": "Arquitectura Norte", "telefono": "+5491123456706", "estado": Lead.Estado.CALIFICANDO,
        "zona": "Nordelta", "tipo": "obra_nueva", "obra": "Aberturas de aluminio para ampliación de vivienda.",
        "medidas": "Aproximadamente 18 m2 de aberturas", "plazo": "31_90_dias", "presupuesto": "desconocido",
        "faltantes": ["presupuesto"], "accion": "preguntar",
        "resumen": "Ampliación en Nordelta con medidas aproximadas. Falta definir rango de inversión para avanzar.",
    },
    {
        "nombre": "Sofía Cabrera", "telefono": "+5491123456707", "estado": Lead.Estado.VISITA_ASISTIDA,
        "zona": "Martínez", "tipo": "reemplazo", "obra": "Reemplazo de ventanal corredizo por PVC con DVH.",
        "medidas": "2,40 x 2,10 m", "plazo": "0_30_dias", "presupuesto": "medio",
        "faltantes": [], "accion": "enviar_presupuesto",
        "resumen": "Relevamiento realizado. Se confirmaron medidas y sistema de PVC con DVH; corresponde enviar presupuesto.",
    },
    {
        "nombre": "Martín Cordero", "telefono": "+5491123456708", "estado": Lead.Estado.NUEVO,
        "zona": "San Fernando", "tipo": "desconocido", "obra": "Pidió información por ventanas.",
        "medidas": "Pendientes", "plazo": "desconocido", "presupuesto": "desconocido",
        "faltantes": ["tipo_obra", "fotos_o_medidas", "plazo", "presupuesto"], "accion": "preguntar",
        "resumen": "Consulta nueva. Aún falta entender el proyecto, las medidas, el plazo y la inversión prevista.",
    },
    {
        "nombre": "Ana Paredes", "telefono": "+5491123456709", "estado": Lead.Estado.CALIFICADO,
        "zona": "Escobar", "tipo": "cerramiento", "obra": "Frente plegable para quincho.",
        "medidas": "Frente de 4,80 x 2,60 m con fotos", "plazo": "31_90_dias", "presupuesto": "medio",
        "faltantes": [], "accion": "agendar",
        "resumen": "Cerramiento plegable para quincho en Escobar. Cuenta con fotos y medidas suficientes para coordinar relevamiento.",
    },
    {
        "nombre": "Rodrigo Ibarra", "telefono": "+5491123456710", "estado": Lead.Estado.CONTACTADO,
        "zona": "Belén de Escobar", "tipo": "reforma", "obra": "Cambio de puerta de entrada y paño fijo.",
        "medidas": "Pendientes", "plazo": "0_30_dias", "presupuesto": "desconocido",
        "faltantes": ["fotos_o_medidas", "presupuesto"], "accion": "preguntar",
        "resumen": "Interesado en renovar puerta de entrada. Ya confirmó zona y plazo, pero debe enviar fotos o medidas.",
    },
    {
        "nombre": "Laura Acosta", "telefono": "+5491123456711", "estado": Lead.Estado.CALIFICANDO,
        "zona": "Pilar", "tipo": "otro", "obra": "Mampara a medida para baño principal.",
        "medidas": "1,60 x 2,00 m", "plazo": "0_30_dias", "presupuesto": "desconocido",
        "faltantes": ["presupuesto"], "accion": "preguntar",
        "resumen": "Solicita mampara a medida en Pilar. Informó medidas y plazo; falta rango de inversión para priorizarla.",
    },
    {
        "nombre": "Constructora Brava", "telefono": "+5491123456712", "estado": Lead.Estado.VISITA_AGENDADA,
        "zona": "Benavídez", "tipo": "obra_nueva", "obra": "Aberturas de aluminio para local comercial.",
        "medidas": "Frente de 8 m y tres ventanas", "plazo": "31_90_dias", "presupuesto": "alto",
        "faltantes": [], "accion": "confirmar_visita",
        "resumen": "Obra comercial en Benavídez. Datos completos y visita técnica coordinada para definir perfilería y DVH.",
    },
]


class Command(BaseCommand):
    help = "Crea o actualiza 12 leads ficticios, etiquetados como demo, para mostrar el dashboard."

    def add_arguments(self, parser):
        parser.add_argument("--cliente", default="Carpintería Demo", help="Nombre exacto del cliente demo.")
        parser.add_argument("--limpiar", action="store_true", help="Elimina sólo los leads creados por este comando.")

    def handle(self, *args, **options):
        cliente = Cliente.objects.filter(nombre=options["cliente"]).first()
        if cliente is None:
            raise CommandError(f'No existe un cliente llamado "{options["cliente"]}".')

        seeded = Lead.objects.filter(cliente=cliente, payload_origen__demo_seed="umbral_dashboard")
        if options["limpiar"]:
            count = seeded.count()
            seeded.delete()
            self.stdout.write(self.style.SUCCESS(f"Se eliminaron {count} leads de demostración."))
            return

        now = timezone.now()
        created = updated = 0
        for index, item in enumerate(DEMO_LEADS):
            lead, was_created = Lead.objects.update_or_create(
                cliente=cliente,
                telefono_e164=item["telefono"],
                defaults={
                    "source": Lead.Source.MANUAL,
                    "nombre": item["nombre"],
                    "consentimiento_whatsapp": True,
                    "payload_origen": {"demo_seed": "umbral_dashboard"},
                    "estado": item["estado"],
                    "zona": item["zona"],
                    "tipo_obra": item["tipo"],
                    "descripcion_obra": item["obra"],
                    "medidas_aproximadas": item["medidas"],
                    "rango_presupuesto": item["presupuesto"],
                    "plazo": item["plazo"],
                    "campos_faltantes": item["faltantes"],
                    "resumen_ia": item["resumen"],
                    "proxima_accion": item["accion"],
                    "last_message_at": now - timedelta(hours=index * 3),
                    "visita_agendada_para": now + timedelta(days=index + 1) if item["estado"] == Lead.Estado.VISITA_AGENDADA else None,
                    "visita_asistida_at": now - timedelta(days=1) if item["estado"] == Lead.Estado.VISITA_ASISTIDA else None,
                },
            )
            created += int(was_created)
            updated += int(not was_created)
            Interaccion.objects.get_or_create(
                lead=lead,
                direccion=Interaccion.Direccion.ENTRANTE,
                tipo=Interaccion.Tipo.SISTEMA,
                texto="Lead ficticio creado para demostración comercial de Umbral.",
                defaults={"canal": "demo", "estado_envio": Interaccion.EstadoEnvio.RECIBIDO},
            )
        self.stdout.write(self.style.SUCCESS(f"Demo lista: {created} leads creados y {updated} actualizados."))
