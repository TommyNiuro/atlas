"""Priority Engine: formula determinista de la seccion 8 del requerimiento.
Funcion pura, pesos en config/scoring.yaml, cero LLM, cero tokens."""
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[5]  # .../apps/api/src/atlas/scoring -> raiz
DEFAULT_WEIGHTS_PATH = REPO_ROOT / "config" / "scoring.yaml"


def load_weights(path: Path = DEFAULT_WEIGHTS_PATH) -> dict:
    return yaml.safe_load(path.read_text())


@dataclass
class Facts:
    """Hechos duros + señales del Priorizador, ya resueltos a numeros."""

    horas_hasta_deadline: float | None = None
    impacto: float = 0.0  # señal del agente 3, 0-1
    requester_factor: float = 0.4  # cliente_con_deal 1.0 | jefe 0.9 | colega 0.6 | auto 0.4
    urgente: bool = False
    importante: bool = False
    estrategico: bool = False  # proyecto marcado estrategico (pareto)
    veces_pospuesta: int = 0
    estimated_minutes: int | None = None
    dias_abierta: float = 0.0
    tareas_mismo_contexto_hoy: int = 0  # tareas abiertas del mismo proyecto/cliente
    carga_del_dia: float = 0.0  # 0-1


def _factores(f: Facts) -> dict[str, float]:
    if f.horas_hasta_deadline is None:
        deadline = 0.15
    else:
        deadline = 1 / (1 + max(f.horas_hasta_deadline, 0) / 24)

    if f.urgente and f.importante:
        eisenhower = 1.0
    elif f.importante:
        eisenhower = 0.7
    elif f.urgente:
        eisenhower = 0.5
    else:
        eisenhower = 0.1

    frog = 0.0
    if f.estimated_minutes and f.estimated_minutes > 60:
        frog = min(1.0, f.veces_pospuesta / 4)

    overloaded = 1.0 if (f.carga_del_dia > 0.85 and (f.estimated_minutes or 0) > 90) else 0.0

    return {
        "deadline_factor": deadline,
        "impact_factor": f.impacto,
        "requester_factor": f.requester_factor,
        "eisenhower_factor": eisenhower,
        "pareto_factor": 1.0 if f.estrategico else 0.0,
        "frog_factor": frog,
        "age_factor": min(1.0, f.dias_abierta / 14),
        "context_bonus": 1.0 if f.tareas_mismo_contexto_hoy >= 2 else 0.0,
        "effort_penalty_if_overloaded": overloaded,
    }


def compute_score(facts: Facts, weights: dict | None = None) -> tuple[float, dict]:
    """Devuelve (score 0-100, desglose factor por factor). Explicable: cada
    factor aparece con su aporte, nunca un numero magico."""
    w = (weights or load_weights())["weights"]
    factores = _factores(facts)
    breakdown = {k: round(w[k] * v, 2) for k, v in factores.items()}
    score = max(0.0, min(100.0, sum(breakdown.values())))
    return round(score, 1), breakdown
