"""Testes do icon_backfill (Phase C)."""
from __future__ import annotations

import json

from skinvault import icon_backfill


LISTING_HTML_WITH_ICON = '''
<html>
<body>
<img id="mainContentsThumbnailImg" src="https://community.cloudflare.steamstatic.com/economy/image/AAA111:BBB222/360fx360f">
</body>
</html>
'''

LISTING_HTML_WITHOUT_ICON = '''
<html><body>Sem imagem aqui</body></html>
'''


# ── extract_icon_hash ─────────────────────────────────────


def test_extract_icon_hash_pega_do_html():
    assert icon_backfill.extract_icon_hash(
        LISTING_HTML_WITH_ICON,
    ) == "AAA111:BBB222"


def test_extract_icon_hash_none_quando_ausente():
    assert icon_backfill.extract_icon_hash(LISTING_HTML_WITHOUT_ICON) is None


def test_extract_icon_hash_none_vazio():
    assert icon_backfill.extract_icon_hash("") is None
    assert icon_backfill.extract_icon_hash(None) is None  # type: ignore


# ── names_pending_backfill ─────────────────────────────────


def test_names_pending_dedup_e_filtra_com_icon():
    events = [
        {"name": "A", "icon_url": None},
        {"name": "A", "icon_url": None},
        {"name": "B", "icon_url": "xyz"},  # ja tem icon — skip
        {"name": "C"},  # sem icon_url field
        {"name": "C"},
    ]
    pending = icon_backfill.names_pending_backfill(events)
    assert pending == ["A", "C"]


def test_names_pending_ignora_nomes_vazios():
    events = [
        {"name": "", "icon_url": None},
        {"name": None, "icon_url": None},
        {"name": "X", "icon_url": None},
    ]
    assert icon_backfill.names_pending_backfill(events) == ["X"]


# ── backfill_market_events ─────────────────────────────────


def _write_events(path, events):
    path.write_text(
        json.dumps(events, ensure_ascii=False),
        encoding="utf-8",
    )


def test_backfill_atualiza_eventos_e_salva(tmp_path):
    p = tmp_path / "events.json"
    _write_events(p, [
        {"name": "Caixa A", "icon_url": None, "price": 1.0},
        {"name": "Caixa A", "icon_url": None, "price": 2.0},
        {"name": "Caixa B", "icon_url": None, "price": 3.0},
    ])

    def fake_fetcher(name: str) -> str | None:
        return {"Caixa A": "hash_a", "Caixa B": "hash_b"}.get(name)

    result = icon_backfill.backfill_market_events(
        path=p, throttle_s=0, fetcher=fake_fetcher,
    )

    assert result["total_names"] == 2
    assert result["fetched"] == 2
    assert result["names_resolved"] == 2
    assert result["events_updated"] == 3

    data = json.loads(p.read_text("utf-8"))
    assert data[0]["icon_url"] == "hash_a"
    assert data[1]["icon_url"] == "hash_a"
    assert data[2]["icon_url"] == "hash_b"


def test_backfill_preserva_icones_existentes(tmp_path):
    p = tmp_path / "events.json"
    _write_events(p, [
        {"name": "Z", "icon_url": "preserved_hash"},
        {"name": "Y", "icon_url": None},
    ])

    def fetcher(name):
        return "y_hash" if name == "Y" else None

    result = icon_backfill.backfill_market_events(
        path=p, throttle_s=0, fetcher=fetcher,
    )

    data = json.loads(p.read_text("utf-8"))
    # Z mantem o hash original; Y ganha hash novo
    assert data[0]["icon_url"] == "preserved_hash"
    assert data[1]["icon_url"] == "y_hash"
    assert result["events_updated"] == 1


def test_backfill_max_names_limita_consultas(tmp_path):
    p = tmp_path / "events.json"
    _write_events(p, [
        {"name": f"N{i}", "icon_url": None} for i in range(10)
    ])
    called = []

    def fetcher(name):
        called.append(name)
        return f"hash_{name}"

    result = icon_backfill.backfill_market_events(
        path=p, throttle_s=0, max_names=3, fetcher=fetcher,
    )

    assert len(called) == 3
    assert result["fetched"] == 3
    assert result["total_names"] == 10  # total no JSON, nao limitado
    assert result["events_updated"] == 3


def test_backfill_interruption_check_aborta(tmp_path):
    p = tmp_path / "events.json"
    _write_events(p, [
        {"name": f"N{i}", "icon_url": None} for i in range(10)
    ])
    counter = {"n": 0}

    def fetcher(name):
        counter["n"] += 1
        return None  # nao resolve nada

    def interrupted():
        return counter["n"] >= 2  # aborta depois de 2

    result = icon_backfill.backfill_market_events(
        path=p, throttle_s=0, fetcher=fetcher,
        interruption_check=interrupted,
    )

    # Abortou: fetched <= 2 (interrupcao checada antes de cada fetch)
    assert result["fetched"] <= 2


def test_backfill_progress_callback(tmp_path):
    p = tmp_path / "events.json"
    _write_events(p, [
        {"name": "A", "icon_url": None},
        {"name": "B", "icon_url": None},
    ])
    progress: list[tuple] = []
    icon_backfill.backfill_market_events(
        path=p, throttle_s=0,
        fetcher=lambda n: "h",
        on_progress=lambda i, n, name: progress.append((i, n, name)),
    )
    assert progress == [(1, 2, "A"), (2, 2, "B")]


def test_backfill_path_inexistente_retorna_zero(tmp_path):
    p = tmp_path / "no_existe.json"
    result = icon_backfill.backfill_market_events(
        path=p, throttle_s=0, fetcher=lambda n: "x",
    )
    assert result["total_names"] == 0
    assert result["events_updated"] == 0
    assert not p.exists()  # nao cria arquivo vazio


def test_backfill_sem_pending_nao_salva(tmp_path):
    """Se todos eventos ja' tem icon_url, backfill nao toca o arquivo."""
    p = tmp_path / "events.json"
    _write_events(p, [
        {"name": "A", "icon_url": "h1"},
        {"name": "B", "icon_url": "h2"},
    ])
    mtime_before = p.stat().st_mtime

    called = []
    icon_backfill.backfill_market_events(
        path=p, throttle_s=0, fetcher=lambda n: called.append(n) or "x",
    )
    assert called == []  # nada pendente
    # arquivo nao foi reescrito (mtime inalterado)
    assert p.stat().st_mtime == mtime_before
