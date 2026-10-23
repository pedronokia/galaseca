"""Testes de user_watchlist.py (watchlist pessoal, site público)."""
from __future__ import annotations

from skinvault.public_site import user_watchlist


def test_load_items_vazio(tmp_path):
    p = tmp_path / "x.db"
    assert user_watchlist.load_items("1", path=p) == []


def test_add_item(tmp_path):
    p = tmp_path / "x.db"
    out = user_watchlist.add_item("1", "AK-47", 10.0, path=p)
    assert len(out) == 1
    assert out[0]["name"] == "AK-47"
    assert out[0]["target"] == 10.0
    assert out[0]["rules"] == {}
    assert out[0]["triggered_rules"] == []


def test_add_item_sem_target(tmp_path):
    p = tmp_path / "x.db"
    out = user_watchlist.add_item("1", "AK-47", path=p)
    assert out[0]["target"] == 0.0


def test_update_rules(tmp_path):
    p = tmp_path / "x.db"
    user_watchlist.add_item("1", "AK-47", path=p)
    out = user_watchlist.update_rules(
        "1", "AK-47", {"price_below": 5.0}, baseline_price=20.0, path=p)
    assert out[0]["rules"] == {"price_below": 5.0}
    assert out[0]["baseline_price"] == 20.0


def test_update_rules_reseta_triggered_rules(tmp_path):
    p = tmp_path / "x.db"
    user_watchlist.add_item("1", "AK-47", path=p)
    items = user_watchlist.load_items("1", path=p)
    items[0]["triggered_rules"] = ["price_below"]
    from skinvault.public_site import user_store
    user_store.save_user_json("1", "watchlist", items, path=p)
    out = user_watchlist.update_rules("1", "AK-47", {"price_below": 5.0}, path=p)
    assert out[0]["triggered_rules"] == []


def test_update_rules_inexistente_devolve_none(tmp_path):
    p = tmp_path / "x.db"
    assert user_watchlist.update_rules("1", "Nada", {}, path=p) is None


def test_remove_item(tmp_path):
    p = tmp_path / "x.db"
    user_watchlist.add_item("1", "AK-47", path=p)
    user_watchlist.add_item("1", "M4A4", path=p)
    assert user_watchlist.remove_item("1", "AK-47", path=p) is True
    restantes = user_watchlist.load_items("1", path=p)
    assert [it["name"] for it in restantes] == ["M4A4"]


def test_remove_item_inexistente(tmp_path):
    p = tmp_path / "x.db"
    assert user_watchlist.remove_item("1", "Nada", path=p) is False


def test_itens_isolados_por_usuario(tmp_path):
    p = tmp_path / "x.db"
    user_watchlist.add_item("1", "AK-47", path=p)
    user_watchlist.add_item("2", "M4A4", path=p)
    assert [it["name"] for it in user_watchlist.load_items("1", path=p)] == ["AK-47"]
    assert [it["name"] for it in user_watchlist.load_items("2", path=p)] == ["M4A4"]
