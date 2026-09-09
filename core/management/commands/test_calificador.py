"""Prueba local del calificador Umbral sin Meta ni WhatsApp."""

from django.core.management.base import BaseCommand, CommandError

from core.models import Cliente, Interaccion, Lead
from core.views import _apply_calification, _ask_califier, _next_message_for_lead


class Command(BaseCommand):
    help = "Prueba GPT-4o-mini y Structured Outputs sin enviar mensajes externos."

    def add_arguments(self, parser):
        parser.add_argument("--cliente", default="Carpintería Demo")
        parser.add_argument(
            "--mensaje",
            default="Hola, estoy en Pilar. Quiero cambiar cinco ventanas en una casa y hacerlo este mes.",
        )
        parser.add_argument("--telefono", default="+5491100000000")
        parser.add_argument("--conservar", action="store_true", help="Conserva el lead de prueba en Admin.")

    def handle(self, *args, **options):
        try:
            cliente = Cliente.objects.get(nombre=options["cliente"], activo=True)
        except Cliente.DoesNotExist as exc:
            raise CommandError(f"No existe un cliente activo llamado: {options['cliente']}") from exc

        lead = Lead.objects.create(
            cliente=cliente,
            source=Lead.Source.MANUAL,
            nombre="Prueba local IA",
            telefono_e164=options["telefono"],
            estado=Lead.Estado.CALIFICANDO,
        )
        Interaccion.objects.create(
            lead=lead,
            direccion=Interaccion.Direccion.ENTRANTE,
            tipo=Interaccion.Tipo.TEXTO,
            texto=options["mensaje"],
            estado_envio=Interaccion.EstadoEnvio.RECIBIDO,
        )

        try:
            result = _ask_califier(lead)
            _apply_calification(lead, result)
            self.stdout.write(self.style.SUCCESS("OpenAI respondió correctamente."))
            self.stdout.write("\nJSON estructurado:\n")
            self.stdout.write(str(result))
            self.stdout.write(
                f"\nEstado final: {lead.estado} | Próxima acción: {lead.proxima_accion}"
            )
            self.stdout.write(f"Mensaje que enviaría Umbral: {_next_message_for_lead(lead, result['mensaje_respuesta'])}")
        finally:
            if not options["conservar"]:
                lead.delete()
                self.stdout.write("\nLead de prueba eliminado: no se modificaron datos operativos.")
