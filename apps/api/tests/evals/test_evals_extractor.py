"""Evals del Extractor: 10 correos realistas (anonimizados), unos que son
tarea y otros que no. Corre solo con ANTHROPIC_API_KEY (gasta tokens reales).
Criterio del bloque: precision >= 0.8."""
import asyncio
import os

import pytest

from atlas.agents import runtime
from atlas.agents.schemas import ExtractorOut
from atlas.core import config

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"), reason="sin ANTHROPIC_API_KEY, eval saltado"
)

# (asunto, cuerpo, es_tarea)
CASOS = [
    ("Propuesta comercial", "Hola Tomás, ¿me mandas la propuesta actualizada el viernes? Saludos", True),
    ("Re: contrato", "Perfecto, muchas gracias por el envío. Quedamos atentos.", False),
    ("Reunión de kickoff", "¿Puedes preparar la presentación para el kickoff del lunes?", True),
    ("Newsletter semanal", "Las 10 noticias tech de la semana. Suscríbete para más.", False),
    ("Factura pendiente", "Te recuerdo que la factura 447 vence mañana, ¿puedes gestionar el pago?", True),
    ("FYI", "Te comparto el reporte final por si lo quieres mirar algún día, sin apuro.", False),
    ("Candidato finalista", "Necesitamos tu feedback de la entrevista de ayer antes del jueves.", True),
    ("Confirmación automática", "Tu reserva quedó confirmada para el 15 de julio a las 9am.", False),
    ("Presupuesto Q3", "¿Revisas los números del presupuesto y me dices si aprobamos?", True),
    ("Re: gracias", "¡Gracias a ti! Fue un gusto conversar.", False),
]


def test_precision_extractor():
    async def run():
        aciertos = 0
        for asunto, cuerpo, es_tarea in CASOS:
            out = await runtime.call_agent(
                "extractor",
                {"mensaje": {"subject": asunto, "bodyPreview": cuerpo,
                             "from": {"emailAddress": {"address": "contacto@empresa.com"}}},
                 "fecha_hoy": "2026-07-09", "contexto_usuario": {"areas": ["Ventas"]}},
                ExtractorOut,
                config.MODEL_FAST,
            )
            detecto = bool(out and any(c.confianza >= 0.6 for c in out.candidatas))
            if detecto == es_tarea:
                aciertos += 1
        precision = aciertos / len(CASOS)
        print(f"\nPrecision extractor: {precision:.0%} ({aciertos}/{len(CASOS)})")
        assert precision >= 0.8, f"Precision {precision:.0%} bajo el umbral"

    asyncio.run(run())
