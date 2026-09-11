# Guion de demo comercial - Umbral

Duración objetivo: 10 minutos. Objetivo: conseguir un piloto de 14 días, no explicar cada detalle técnico.

## Preparación

1. Ejecutar `python manage.py seed_demo_dashboard --cliente "Carpintería Demo"`.
2. Abrir el dashboard de Carpintería Demo en una pestaña privada.
3. Dejar preparado el filtro `Calificando` y una consulta de estado `Visita agendada`.
4. No mostrar Django Admin, código, tokens ni configuración de Meta.

## Guion

### 0:00 - 1:00 | Abrir con el problema

> Cuando están en obra o en el taller, ¿qué pasa con las consultas que entran sin medidas, fotos o una zona clara? Normalmente alguien tiene que volver a preguntar todo, o directamente la oportunidad se enfría.

> Umbral no reemplaza al vendedor. Ordena la consulta antes de que ustedes pierdan tiempo con ella.

### 1:00 - 3:00 | Mostrar la bandeja

Abrir el dashboard y señalar los cuatro indicadores.

> Acá no ven mensajes sueltos: ven una bandeja de oportunidades. En segundos se distingue qué está incompleto, qué ya está para avanzar y qué necesita una visita.

Abrir `Mariana López`.

> Esta consulta todavía necesita fotos o medidas y un rango de inversión. En vez de leer toda la conversación, ya sabemos exactamente qué falta.

### 3:00 - 5:00 | Mostrar la acción sugerida

Hacer clic en **Copiar respuesta sugerida**.

> El sistema propone la siguiente pregunta en un lenguaje simple. El equipo conserva siempre la decisión; Umbral acelera el trabajo repetitivo de ordenar la información.

### 5:00 - 6:30 | Mostrar una oportunidad lista

Abrir `Estudio Arce` o `Ana Paredes`.

> Acá ya hay zona, proyecto, medidas y plazo. Es una consulta que merece una llamada o un relevamiento, no otra ronda de preguntas básicas.

### 6:30 - 7:30 | Mostrar excepción y visita

Filtrar `Requiere humano`, abrir `Carla Romero`. Luego abrir una visita agendada.

> Si aparece una urgencia o una consulta sensible, no la automatizamos a ciegas: se prioriza para una persona. Y las visitas quedan separadas de las consultas que todavía no tienen datos suficientes.

### 7:30 - 9:00 | Proponer el piloto

> La propuesta no es cambiar todo su WhatsApp ni pedir contraseñas. Hacemos un piloto de 14 días con consultas reales que ustedes nos derivan. Medimos cuántas se ordenan, cuántas llegan completas y cuáles terminan en visita.

> Si al final no les ahorra tiempo ni mejora el seguimiento, no tiene sentido seguir. Si funciona, recién ahí vemos una integración más profunda.

### 9:00 - 10:00 | Cierre

> Para decidir si el piloto les sirve, necesito entender cuántas consultas reciben por semana y dónde se les suelen perder. ¿Lo vemos con dos o tres consultas reales esta semana?

## Respuestas breves a objeciones

| Objeción | Respuesta |
|---|---|
| "Yo respondo todo" | "Perfecto: Umbral no busca reemplazarte, sino evitar que repitas preguntas y que pierdas el contexto entre obra, taller y mensajes." |
| "No quiero dar acceso a WhatsApp" | "No hace falta en el piloto. Empezamos con consultas derivadas manualmente; conservás control total." |
| "No sé si recibo tantas consultas" | "Justamente el piloto nos permite medirlo. Si no hay volumen ni dolor, no te voy a recomendar una integración." |
| "¿Es un chatbot?" | "No. Es una bandeja comercial que ordena lo que entra y te indica qué dato falta o qué oportunidad conviene priorizar." |

## Después de la reunión

Enviar el mismo día:

> Gracias por tu tiempo. Te propongo un piloto de 14 días: nos derivan consultas reales, Umbral las ordena y revisamos juntos qué oportunidades quedan listas para avanzar. No requiere contraseñas ni cambios en sus canales. Si te parece, coordinamos el inicio para [día].
