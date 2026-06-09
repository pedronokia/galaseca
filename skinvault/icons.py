"""Cache local de icones do Steam CDN.

Steam serve icones via:
  https://community.cloudflare.steamstatic.com/economy/image/<hash>/96fx96f

Onde <hash> e' uma string base64-url-safe extraida do HTML do market.
Cache local em `data/icons/<sha256_short>.png` — sanitiza hash (que pode
ter `:` e `/`) via SHA-256 truncado.

Filosofia:
- Network-free no caminho UI principal (local_path() so' checa disco)
- Fetch sincrono em modo direto, ou em batch via ensure_cached()
- Falha silenciosa: se CDN nao responde, retorna None — UI fica sem
  icone mas nao quebra
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from skinvault._paths import DATA_DIR

ICONS_DIR = DATA_DIR / "icons"

# 96x96 e' o tamanho usado pela aba "Meu Historico" do Steam (visualmente
# ~50px nas telas de hoje, mas serve em monitores HiDPI tambem).
_CDN_URL_TPL = (
    "https://community.cloudflare.steamstatic.com/economy/image/"
    "{hash}/96fx96f"
)
_TIMEOUT = 10.0


def cache_path(icon_hash: str) -> Path:
    """Path local pro icone. SHA-256 trunca pra nome seguro de arquivo
    (icon_hash original pode ter '/' e ':').
    """
    safe = hashlib.sha256(icon_hash.encode("utf-8")).hexdigest()[:32]
    return ICONS_DIR / f"{safe}.png"


def local_path(icon_hash: str | None) -> Path | None:
    """Retorna path local SE icone ja' em cache (>0 bytes). None caso
    contrario — nunca faz rede.
    """
    if not icon_hash:
        return None
    p = cache_path(icon_hash)
    try:
        return p if p.exists() and p.stat().st_size > 0 else None
    except OSError:
        return None


def fetch(icon_hash: str, timeout: float = _TIMEOUT) -> Path | None:
    """Baixa do CDN se faltar em cache, retorna path. None se falhar.

    Sincrono — chame em background pra nao travar UI.
    """
    if not icon_hash:
        return None
    p = cache_path(icon_hash)
    if p.exists() and p.stat().st_size > 0:
        return p
    try:
        import httpx
    except ImportError:
        return None
    url = _CDN_URL_TPL.format(hash=icon_hash)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code != 200 or not resp.content:
                return None
            ICONS_DIR.mkdir(parents=True, exist_ok=True)
            p.write_bytes(resp.content)
            return p
    except Exception:
        return None


def ensure_cached(icon_hashes: list[str | None]) -> dict[str, Path]:
    """Garante que todos os hashes estejam em cache (baixa os que faltam).

    Retorna dict {hash: path} dos que tiveram sucesso. Hashes None/vazios
    sao ignorados.
    """
    out: dict[str, Path] = {}
    seen: set[str] = set()
    for h in icon_hashes:
        if not h or h in seen:
            continue
        seen.add(h)
        p = local_path(h)
        if p is None:
            p = fetch(h)
        if p is not None:
            out[h] = p
    return out
