"""Priority Engine: cada factor aislado (umbral 90% en scoring/ segun spec)."""
from atlas.scoring.engine import Facts, compute_score, load_weights

W = load_weights()


def test_sin_deadline_factor_bajo():
    score, bd = compute_score(Facts(), W)
    assert bd["deadline_factor"] == round(25 * 0.15, 2)


def test_deadline_inminente_domina():
    score, bd = compute_score(Facts(horas_hasta_deadline=0), W)
    assert bd["deadline_factor"] == 25.0


def test_deadline_24h():
    _, bd = compute_score(Facts(horas_hasta_deadline=24), W)
    assert bd["deadline_factor"] == 12.5  # 25 * 1/(1+1)


def test_eisenhower_cuadrantes():
    def eis(u, i):
        return compute_score(Facts(urgente=u, importante=i), W)[1]["eisenhower_factor"]

    assert eis(True, True) == 12.0
    assert eis(False, True) == round(12 * 0.7, 2)
    assert eis(True, False) == 6.0
    assert eis(False, False) == round(12 * 0.1, 2)


def test_frog_solo_tareas_grandes_pospuestas():
    _, bd = compute_score(Facts(estimated_minutes=30, veces_pospuesta=4), W)
    assert bd["frog_factor"] == 0.0  # corta, no aplica
    _, bd = compute_score(Facts(estimated_minutes=90, veces_pospuesta=2), W)
    assert bd["frog_factor"] == 4.0  # 8 * min(1, 2/4)


def test_age_sube_lento_y_topa():
    _, bd = compute_score(Facts(dias_abierta=7), W)
    assert bd["age_factor"] == 3.0  # 6 * 7/14
    _, bd = compute_score(Facts(dias_abierta=60), W)
    assert bd["age_factor"] == 6.0


def test_penalidad_sobrecarga():
    _, bd = compute_score(Facts(carga_del_dia=0.9, estimated_minutes=120), W)
    assert bd["effort_penalty_if_overloaded"] == -10.0
    _, bd = compute_score(Facts(carga_del_dia=0.5, estimated_minutes=120), W)
    assert bd["effort_penalty_if_overloaded"] == 0.0


def test_score_acotado_0_100():
    maxi = Facts(horas_hasta_deadline=0, impacto=1, requester_factor=1, urgente=True,
                 importante=True, estrategico=True, veces_pospuesta=8, estimated_minutes=120,
                 dias_abierta=30, tareas_mismo_contexto_hoy=3)
    score, _ = compute_score(maxi, W)
    assert 0 <= score <= 100
    assert score == 100.0


def test_breakdown_explicable():
    score, bd = compute_score(Facts(horas_hasta_deadline=12, impacto=0.8), W)
    assert abs(score - round(sum(bd.values()), 1)) < 0.1
    assert set(bd) == set(W["weights"])
