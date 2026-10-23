"""Testes de db.py/user_store.py (conta + dado pessoal por usuário)."""
from __future__ import annotations

from skinvault.public_site import db, user_store


def test_connect_cria_schema(tmp_path):
    p = tmp_path / "x.db"
    conn = db.connect(p)
    tabelas = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"users", "user_data"} <= tabelas


def test_connect_idempotente(tmp_path):
    p = tmp_path / "x.db"
    db.connect(p).close()
    db.connect(p).close()  # nao deve falhar na 2a chamada (CREATE TABLE IF NOT EXISTS)


# ── users ────────────────────────────────────────────────────

def test_upsert_e_get_user(tmp_path):
    p = tmp_path / "x.db"
    user_store.upsert_user("123", persona_name="Fulano",
                           avatar_url="http://x/a.jpg", path=p)
    u = user_store.get_user("123", path=p)
    assert u["steamid"] == "123"
    assert u["persona_name"] == "Fulano"
    assert u["avatar_url"] == "http://x/a.jpg"
    assert u["created_ts"] is not None


def test_get_user_inexistente(tmp_path):
    p = tmp_path / "x.db"
    db.connect(p).close()
    assert user_store.get_user("999", path=p) is None


def test_upsert_user_atualiza_nome(tmp_path):
    p = tmp_path / "x.db"
    user_store.upsert_user("1", persona_name="A", path=p)
    user_store.upsert_user("1", persona_name="B", path=p)
    assert user_store.get_user("1", path=p)["persona_name"] == "B"


def test_upsert_user_sem_nome_avatar(tmp_path):
    p = tmp_path / "x.db"
    user_store.upsert_user("1", path=p)
    u = user_store.get_user("1", path=p)
    assert u["persona_name"] is None
    assert u["avatar_url"] is None


# ── user_data (load/save json) ────────────────────────────────

def test_load_user_json_default_quando_vazio(tmp_path):
    p = tmp_path / "x.db"
    assert user_store.load_user_json("1", "portfolio", [], path=p) == []
    assert user_store.load_user_json("1", "settings", {}, path=p) == {}


def test_save_e_load_user_json_roundtrip(tmp_path):
    p = tmp_path / "x.db"
    dados = [{"name": "AK-47", "cost": 10.0, "quantity": 2}]
    user_store.save_user_json("1", "portfolio", dados, path=p)
    assert user_store.load_user_json("1", "portfolio", [], path=p) == dados


def test_save_user_json_sobrescreve(tmp_path):
    p = tmp_path / "x.db"
    user_store.save_user_json("1", "portfolio", [{"a": 1}], path=p)
    user_store.save_user_json("1", "portfolio", [{"a": 2}], path=p)
    assert user_store.load_user_json("1", "portfolio", [], path=p) == [{"a": 2}]


def test_user_data_isolado_por_steamid(tmp_path):
    p = tmp_path / "x.db"
    user_store.save_user_json("1", "portfolio", [{"name": "A"}], path=p)
    user_store.save_user_json("2", "portfolio", [{"name": "B"}], path=p)
    assert user_store.load_user_json("1", "portfolio", [], path=p) == [{"name": "A"}]
    assert user_store.load_user_json("2", "portfolio", [], path=p) == [{"name": "B"}]


def test_user_data_isolado_por_kind(tmp_path):
    p = tmp_path / "x.db"
    user_store.save_user_json("1", "portfolio", [{"name": "A"}], path=p)
    user_store.save_user_json("1", "trades", [{"name": "B"}], path=p)
    assert user_store.load_user_json("1", "portfolio", [], path=p) == [{"name": "A"}]
    assert user_store.load_user_json("1", "trades", [], path=p) == [{"name": "B"}]


# ── delete_user ──────────────────────────────────────────────

def test_delete_user_apaga_conta(tmp_path):
    p = tmp_path / "x.db"
    user_store.upsert_user("1", persona_name="Fulano", path=p)
    user_store.delete_user("1", path=p)
    assert user_store.get_user("1", path=p) is None


def test_delete_user_apaga_todo_dado_pessoal(tmp_path):
    p = tmp_path / "x.db"
    user_store.upsert_user("1", path=p)
    user_store.save_user_json("1", "portfolio", [{"name": "A"}], path=p)
    user_store.save_user_json("1", "trades", [{"name": "B"}], path=p)
    user_store.save_user_json("1", "watchlist", [{"name": "C"}], path=p)
    user_store.save_user_json("1", "history", [{"total": 1.0}], path=p)
    user_store.delete_user("1", path=p)
    assert user_store.load_user_json("1", "portfolio", [], path=p) == []
    assert user_store.load_user_json("1", "trades", [], path=p) == []
    assert user_store.load_user_json("1", "watchlist", [], path=p) == []
    assert user_store.load_user_json("1", "history", [], path=p) == []


def test_delete_user_nao_afeta_outros_usuarios(tmp_path):
    p = tmp_path / "x.db"
    user_store.upsert_user("1", persona_name="Um", path=p)
    user_store.upsert_user("2", persona_name="Dois", path=p)
    user_store.save_user_json("2", "portfolio", [{"name": "X"}], path=p)
    user_store.delete_user("1", path=p)
    assert user_store.get_user("2", path=p)["persona_name"] == "Dois"
    assert user_store.load_user_json("2", "portfolio", [], path=p) == [{"name": "X"}]


def test_delete_user_inexistente_nao_quebra(tmp_path):
    p = tmp_path / "x.db"
    user_store.delete_user("999", path=p)  # nao deve levantar excecao
