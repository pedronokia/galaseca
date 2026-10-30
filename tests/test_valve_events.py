"""Testes do catalogo de eventos da Valve."""
from __future__ import annotations

from datetime import date

from galaseca import valve_events


_REF = date(2026, 6, 8)


def test_events_for_category_capsulas_finds_cologne_2026():
    events = valve_events.events_for_category(
        "Cápsulas", since_days=365, reference_date=_REF,
    )
    assert len(events) == 1
    assert events[0]["id"] == "capsule_abolition_2026_05"
    assert events[0]["impact"] == "positive_all_legacy"


def test_events_for_category_caixas_finds_dec_2025():
    events = valve_events.events_for_category(
        "Caixas", since_days=365, reference_date=_REF,
    )
    ids = [e["id"] for e in events]
    assert "rare_drops_removed_2025_12" in ids


def test_events_for_category_facas_finds_oct_2025():
    events = valve_events.events_for_category(
        "Facas", since_days=365, reference_date=_REF,
    )
    ids = [e["id"] for e in events]
    assert "trade_up_knife_2025_10" in ids


def test_events_for_category_luvas_finds_oct_2025():
    events = valve_events.events_for_category(
        "Luvas", since_days=365, reference_date=_REF,
    )
    ids = [e["id"] for e in events]
    assert "trade_up_knife_2025_10" in ids


def test_events_for_category_unknown_returns_empty():
    events = valve_events.events_for_category(
        "Inexistente", reference_date=_REF,
    )
    assert events == []


def test_events_for_category_filters_by_since_days_short():
    # Cologne 2026 (22/05) eh ~17 dias antes do _REF (08/06).
    # since_days=10 nao deve pegar.
    events = valve_events.events_for_category(
        "Cápsulas", since_days=10, reference_date=_REF,
    )
    assert events == []


def test_events_for_category_filters_by_since_days_long():
    events = valve_events.events_for_category(
        "Cápsulas", since_days=30, reference_date=_REF,
    )
    assert len(events) == 1


def test_events_for_category_ignores_future_events():
    # Antes de qualquer evento -> retorna vazio
    early = date(2025, 1, 1)
    assert valve_events.events_for_category(
        "Cápsulas", reference_date=early,
    ) == []


def test_events_sorted_most_recent_first():
    # Adicionar categoria fake hipotetica nao faz parte do teste; mas
    # validar a ordem com Caixas que possui (potencialmente) varios.
    events = valve_events.events_for_category(
        "Caixas", since_days=10000, reference_date=_REF,
    )
    if len(events) >= 2:
        for a, b in zip(events, events[1:]):
            assert a["date"] >= b["date"]


def test_latest_regime_change_capsulas():
    ev = valve_events.latest_regime_change("Cápsulas", reference_date=_REF)
    assert ev is not None
    assert ev["id"] == "capsule_abolition_2026_05"


def test_latest_regime_change_caixas():
    ev = valve_events.latest_regime_change("Caixas", reference_date=_REF)
    assert ev is not None
    assert ev["date"] == date(2025, 12, 17)


def test_latest_regime_change_unknown_returns_none():
    assert valve_events.latest_regime_change(
        "Inexistente", reference_date=_REF,
    ) is None


def test_latest_regime_change_excludes_future_events():
    # Em 2025-01-01, Cologne 2026 ainda nao aconteceu
    assert valve_events.latest_regime_change(
        "Cápsulas", reference_date=date(2025, 1, 1),
    ) is None


def test_events_have_required_fields():
    required = {"id", "date", "type", "categories", "impact",
                "magnitude", "title", "summary"}
    for ev in valve_events.EVENTS:
        missing = required - set(ev.keys())
        assert not missing, f"Evento {ev.get('id')} sem campos: {missing}"


def test_event_ids_are_unique():
    ids = [e["id"] for e in valve_events.EVENTS]
    assert len(ids) == len(set(ids))
