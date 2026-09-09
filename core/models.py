import uuid

from django.db import models


class Cliente(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=160)
    activo = models.BooleanField(default=True)
    contacto_nombre = models.CharField(max_length=120)
    contacto_whatsapp = models.CharField(max_length=32)
    meta_page_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    meta_form_id = models.CharField(max_length=64, blank=True)
    whatsapp_phone_number_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    manual_intake_token = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    whatsapp_template_inicial = models.CharField(max_length=128, default="umbral_bienvenida")
    zonas_cobertura = models.JSONField(default=list)
    tipos_obra_aceptados = models.JSONField(default=list)
    presupuesto_minimo = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    moneda = models.CharField(max_length=3, default="ARS")
    calendar_id = models.CharField(max_length=255, blank=True)
    duracion_visita_minutos = models.PositiveIntegerField(default=60)
    horarios_visita = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"

    def __str__(self) -> str:
        return self.nombre


class Lead(models.Model):
    class Source(models.TextChoices):
        META_LEAD_AD = "meta_lead_ad", "Meta Lead Ad"
        WHATSAPP = "whatsapp", "WhatsApp"
        MANUAL = "manual", "Manual"

    class Estado(models.TextChoices):
        NUEVO = "nuevo", "Nuevo"
        CONTACTADO = "contactado", "Contactado"
        CALIFICANDO = "calificando", "Calificando"
        CALIFICADO = "calificado", "Calificado"
        NO_CALIFICADO = "no_calificado", "No calificado"
        REQUIERE_HUMANO = "requiere_humano", "Requiere humano"
        VISITA_AGENDADA = "visita_agendada", "Visita agendada"
        VISITA_ASISTIDA = "visita_asistida", "Visita asistida"
        PERDIDO = "perdido", "Perdido"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="leads")
    source = models.CharField(max_length=32, choices=Source.choices)
    meta_lead_id = models.CharField(max_length=64, null=True, blank=True)
    nombre = models.CharField(max_length=160, blank=True)
    telefono_e164 = models.CharField(max_length=32)
    email = models.EmailField(blank=True)
    consentimiento_whatsapp = models.BooleanField(default=False)
    payload_origen = models.JSONField(default=dict)
    estado = models.CharField(max_length=32, choices=Estado.choices, default=Estado.NUEVO)
    zona = models.CharField(max_length=120, blank=True)
    tipo_obra = models.CharField(max_length=32, default="desconocido")
    descripcion_obra = models.TextField(blank=True)
    medidas_aproximadas = models.TextField(blank=True)
    fotos = models.JSONField(default=list, blank=True)
    rango_presupuesto = models.CharField(max_length=24, default="desconocido")
    plazo = models.CharField(max_length=24, default="desconocido")
    campos_faltantes = models.JSONField(default=list, blank=True)
    motivos_calificacion = models.JSONField(default=list, blank=True)
    resumen_ia = models.TextField(blank=True)
    proxima_accion = models.CharField(max_length=32, default="preguntar")
    visita_agendada_para = models.DateTimeField(null=True, blank=True)
    visita_asistida_at = models.DateTimeField(null=True, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cliente", "meta_lead_id"],
                name="unique_meta_lead_per_cliente",
            )
        ]
        indexes = [models.Index(fields=["cliente", "estado"]), models.Index(fields=["telefono_e164"])]

    def __str__(self) -> str:
        return f"{self.nombre or self.telefono_e164} · {self.cliente}"


class Interaccion(models.Model):
    class Direccion(models.TextChoices):
        ENTRANTE = "entrante", "Entrante"
        SALIENTE = "saliente", "Saliente"

    class Tipo(models.TextChoices):
        TEXTO = "texto", "Texto"
        IMAGEN = "imagen", "Imagen"
        TEMPLATE = "template", "Template"
        SISTEMA = "sistema", "Sistema"

    class EstadoEnvio(models.TextChoices):
        RECIBIDO = "recibido", "Recibido"
        PENDIENTE = "pendiente", "Pendiente"
        ENVIADO = "enviado", "Enviado"
        ENTREGADO = "entregado", "Entregado"
        LEIDO = "leido", "Leído"
        FALLIDO = "fallido", "Fallido"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="interacciones")
    direccion = models.CharField(max_length=16, choices=Direccion.choices)
    canal = models.CharField(max_length=16, default="whatsapp")
    tipo = models.CharField(max_length=16, choices=Tipo.choices)
    texto = models.TextField(blank=True)
    media = models.JSONField(default=dict, blank=True)
    meta_message_id = models.CharField(max_length=128, null=True, blank=True, unique=True)
    estado_envio = models.CharField(max_length=16, choices=EstadoEnvio.choices, default=EstadoEnvio.PENDIENTE)
    respuesta_ia = models.JSONField(default=dict, blank=True)
    error_proveedor = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class WebhookEvent(models.Model):
    class Provider(models.TextChoices):
        META_LEAD_ADS = "meta_lead_ads", "Meta Lead Ads"
        WHATSAPP = "whatsapp", "WhatsApp"

    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=32, choices=Provider.choices)
    external_event_id = models.CharField(max_length=160)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED)
    error = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "external_event_id"], name="unique_provider_event")]
