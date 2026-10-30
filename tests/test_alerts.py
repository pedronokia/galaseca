"""Testes do engine de alertas."""
from __future__ import annotations

from galaseca import alerts


def test_evaluate_price_below_target():
    item = {"name": "Test", "target": 100.0}
    fired = alerts.evaluate_item(item, current_price=95.0)
    assert len(fired) == 1
    assert fired[0]["rule"] == "price_below"
    assert "atingiu alvo" in fired[0]["label"]


def test_evaluate_price_below_not_reached():
    item = {"name": "Test", "target": 100.0}
    fired = alerts.evaluate_item(item, current_price=120.0)
    assert fired == []


def test_evaluate_price_below_from_rules():
    """price_below em rules (RulesDialog) dispara igual ao target legado."""
    item = {"name": "Test", "rules": {"price_below": 100.0}}
    fired = alerts.evaluate_item(item, current_price=95.0)
    assert len(fired) == 1
    assert fired[0]["rule"] == "price_below"


def test_evaluate_price_drop_pct():
    item = {
        "name": "Test",
        "baseline_price": 100.0,
        "rules": {"price_drop_pct": 15},
    }
    fired = alerts.evaluate_item(item, current_price=80.0)  # -20%
    assert len(fired) == 1
    assert fired[0]["rule"] == "price_drop_pct"


def test_evaluate_price_drop_pct_not_enough():
    item = {
        "name": "Test",
        "baseline_price": 100.0,
        "rules": {"price_drop_pct": 15},
    }
    fired = alerts.evaluate_item(item, current_price=90.0)  # -10%
    assert fired == []


def test_evaluate_volume_spike():
    item = {"name": "Test", "rules": {"volume_spike": 2.0}}
    vh = [{"value": 100}] * 5 + [{"value": 400}]  # 4x
    fired = alerts.evaluate_item(item, current_price=None, volume_history=vh)
    assert any(a["rule"] == "volume_spike" for a in fired)


def test_evaluate_volume_spike_normal():
    item = {"name": "Test", "rules": {"volume_spike": 2.0}}
    vh = [{"value": 100}] * 5 + [{"value": 105}]
    fired = alerts.evaluate_item(item, current_price=None, volume_history=vh)
    assert fired == []


def test_evaluate_supply_drop():
    item = {"name": "Test", "rules": {"supply_drop": 2.0}}
    sh = [{"value": 200}] * 5 + [{"value": 50}]  # 0.25x
    fired = alerts.evaluate_item(item, current_price=None, supply_history=sh)
    assert any(a["rule"] == "supply_drop" for a in fired)


def test_evaluate_multiple_rules():
    item = {
        "name": "Test",
        "target": 100.0,
        "baseline_price": 200.0,
        "rules": {"price_drop_pct": 20, "volume_spike": 2.0},
    }
    vh = [{"value": 100}] * 5 + [{"value": 400}]
    fired = alerts.evaluate_item(item, current_price=80.0, volume_history=vh)
    rules = {a["rule"] for a in fired}
    assert "price_below" in rules
    assert "price_drop_pct" in rules
    assert "volume_spike" in rules


def test_diff_new_alerts_first_call():
    item = {"name": "Test"}
    fired = [
        {"rule": "price_below", "label": "x", "value": 0, "severity": "info"},
    ]
    new = alerts.diff_new_alerts(item, fired)
    assert len(new) == 1
    assert item["triggered_rules"] == ["price_below"]


def test_diff_new_alerts_suppresses_repeat():
    item = {"name": "Test", "triggered_rules": ["price_below"]}
    fired = [
        {"rule": "price_below", "label": "x", "value": 0, "severity": "info"},
    ]
    new = alerts.diff_new_alerts(item, fired)
    assert new == []


def test_diff_new_alerts_auto_rearm():
    """Se a regra deixa de disparar, sai do triggered_rules (pode rearmar)."""
    item = {"name": "Test", "triggered_rules": ["price_below"]}
    new = alerts.diff_new_alerts(item, [])
    assert new == []
    assert item["triggered_rules"] == []


def test_record_and_load_alerts_log(tmp_path):
    p = tmp_path / "log.json"
    alerts.record_alert("AK-47 | Redline", {
        "rule": "price_below", "label": "atingiu alvo",
        "value": 95.0, "severity": "opportunity",
    }, path=p)
    log = alerts.load_alerts_log(path=p)
    assert len(log) == 1
    assert log[0]["name"] == "AK-47 | Redline"
    assert log[0]["rule"] == "price_below"


def test_alerts_log_cap(tmp_path):
    p = tmp_path / "log.json"
    for i in range(alerts._LOG_CAP + 50):
        alerts.record_alert(f"Item{i}", {
            "rule": "x", "label": "y", "value": 0, "severity": "info",
        }, path=p)
    log = alerts.load_alerts_log(path=p)
    assert len(log) == alerts._LOG_CAP


def test_format_rules_summary_empty():
    assert alerts.format_rules_summary(None) == ""
    assert alerts.format_rules_summary({}) == ""


def test_format_rules_summary_multi():
    s = alerts.format_rules_summary({
        "price_below": 120,
        "price_drop_pct": 15,
        "volume_spike": 3.0,
        "supply_drop": 2.0,
        "score_above": 85,
    })
    assert "abaixo de R$ 120" in s
    assert "queda 15%" in s
    assert "vol 3x" in s
    assert "oferta 2x" in s
    assert "score >=85" in s


def test_evaluate_score_above_dispara():
    """Score >= threshold gera alerta opportunity."""
    item = {"name": "X", "rules": {"score_above": 85}}
    out = alerts.evaluate_item(item, current_price=100.0,
                                current_score=87)
    score_alerts = [a for a in out if a["rule"] == "score_above"]
    assert len(score_alerts) == 1
    assert score_alerts[0]["severity"] == "opportunity"
    assert score_alerts[0]["value"] == 87
    assert "85" in score_alerts[0]["label"]
    assert "87" in score_alerts[0]["label"]


def test_evaluate_score_above_nao_dispara_abaixo():
    """Score < threshold nao gera alerta."""
    item = {"name": "X", "rules": {"score_above": 85}}
    out = alerts.evaluate_item(item, current_price=100.0,
                                current_score=70)
    assert all(a["rule"] != "score_above" for a in out)


def test_evaluate_score_above_ignora_sem_score():
    """Sem current_score, regra e' ignorada (nao crasha)."""
    item = {"name": "X", "rules": {"score_above": 85}}
    out = alerts.evaluate_item(item, current_price=100.0,
                                current_score=None)
    assert all(a["rule"] != "score_above" for a in out)


def test_evaluate_score_above_sem_rule_nao_dispara():
    """Score alto mas sem regra configurada nao dispara."""
    item = {"name": "X", "rules": {}}
    out = alerts.evaluate_item(item, current_price=100.0,
                                current_score=95)
    assert all(a["rule"] != "score_above" for a in out)


def test_evaluate_score_above_auto_rearm():
    """Score sobe acima do threshold dispara; cai e sobe denovo redispara."""
    item = {"name": "X", "rules": {"score_above": 85},
            "triggered_rules": []}
    # 1a vez: score 87, dispara
    fresh = alerts.evaluate_item(item, current_price=100.0,
                                  current_score=87)
    new = alerts.diff_new_alerts(item, fresh)
    assert any(a["rule"] == "score_above" for a in new)
    # 2a vez: score 87 ainda, nao dispara denovo
    fresh = alerts.evaluate_item(item, current_price=100.0,
                                  current_score=87)
    new = alerts.diff_new_alerts(item, fresh)
    assert all(a["rule"] != "score_above" for a in new)
    # Score cai pra 50 (regra nao mais ativa)
    fresh = alerts.evaluate_item(item, current_price=100.0,
                                  current_score=50)
    new = alerts.diff_new_alerts(item, fresh)
    # 3a vez: score sobe denovo, redispara
    fresh = alerts.evaluate_item(item, current_price=100.0,
                                  current_score=90)
    new = alerts.diff_new_alerts(item, fresh)
    assert any(a["rule"] == "score_above" for a in new)


def test_clear_alerts_log(tmp_path):
    p = tmp_path / "log.json"
    alerts.record_alert("X", {"rule": "r", "label": "l",
                              "value": 0, "severity": "info"}, path=p)
    assert len(alerts.load_alerts_log(path=p)) == 1
    alerts.clear_alerts_log(path=p)
    assert alerts.load_alerts_log(path=p) == []


def test_record_alert_corrupted_json(tmp_path):
    """Log corrompido e' tratado como lista vazia."""
    p = tmp_path / "log.json"
    p.write_text("not json", encoding="utf-8")
    alerts.record_alert("X", {"rule": "r", "label": "l",
                              "value": 0, "severity": "info"}, path=p)
    log = alerts.load_alerts_log(path=p)
    assert len(log) == 1


def test_record_alert_invalid_type(tmp_path):
    """Log com tipo invalido (dict em vez de list) e' tratado como vazio."""
    p = tmp_path / "log.json"
    alerts.record_alert("X", {"rule": "r", "label": "l",
                              "value": 0, "severity": "info"}, path=p)
    # Sobrescreve com dict
    p.write_text('{"bad": "data"}', encoding="utf-8")
    alerts.record_alert("Y", {"rule": "r", "label": "l",
                              "value": 0, "severity": "info"}, path=p)
    log = alerts.load_alerts_log(path=p)
    assert len(log) == 1  # O dict invalido foi ignorado, so' o Y ficou


def test_record_alert_oserror_ignored(tmp_path):
    """Erro de escrita no log e' silencioso."""
    file_path = tmp_path / "afile"
    file_path.write_text("", encoding="utf-8")
    bad = file_path / "log.json"
    alerts.record_alert("X", {"rule": "r", "label": "l",
                              "value": 0, "severity": "info"}, path=bad)
    # nao crashou


def test_load_alerts_log_corrupted_json(tmp_path):
    """JSON corrompido retorna lista vazia."""
    p = tmp_path / "log.json"
    p.write_text("corrupt", encoding="utf-8")
    assert alerts.load_alerts_log(path=p) == []


def test_clear_alerts_log_oserror_ignored(tmp_path):
    """Erro ao limpar log e' silencioso."""
    file_path = tmp_path / "afile"
    file_path.write_text("", encoding="utf-8")
    bad = file_path / "log.json"
    alerts.clear_alerts_log(path=bad)
    # nao crashou
