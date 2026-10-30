"""Cache local de ícone dos itens.

Decisão nova (2a rodada, 2026-10-25): até aqui o `<img>` sempre apontava
direto pro CDN da Steam (`community.cloudflare.steamstatic.com`) de
propósito -- comentário antigo em `server.py` dizia que o site público
"nunca baixa/cacheia o ícone". Isso valia pra evitar qualquer tráfego
NOVO contra endpoint sensível da Steam (ver AGENTS.md: o rate limit real
é no market/inventory, não no CDN de imagem). O CDN de imagem é
infraestrutura pública estática, sem rate limit documentado, e
praticamente todo site que mostra item de CS2 hotlinka nela -- cachear
localmente aqui reduz UMA dependência externa no carregamento da
página (e evita o navegador do visitante mandar referrer pra
`steamstatic.com`), sem reintroduzir o risco que a decisão original
evitava.

Primeira visita busca e cacheia em disco; todas as próximas são leitura
local, sem rede. Falha de rede nunca derruba a página -- quem chama
decide o fallback (redirecionar pro CDN direto).
"""
from __future__ import annotations

from pathlib import Path

from galaseca._paths import DATA_DIR

_CACHE_DIR = DATA_DIR / "icon_cache"
_CDN_URL_TPL = (
    "https://community.cloudflare.steamstatic.com/economy/image/{hash}/192fx192f")
_TIMEOUT = 5.0


def _caminho(hash_icone: str) -> Path:
    nome_seguro = "".join(c for c in hash_icone if c.isalnum())[:128]
    return _CACHE_DIR / f"{nome_seguro}.jpg"


def obter(hash_icone: str) -> "bytes | None":
    """Bytes da imagem, do cache de disco ou buscando (e cacheando) do
    CDN da Steam. None se o hash for inválido ou a busca falhar -- quem
    chama decide o fallback.

    A rota `/icone/<hash>.jpg` (server.py) passa o `<hash>` da URL direto
    pra cá, sem validar nada -- é QUALQUER visitante, sem login. Até
    2026-10-27 só `_caminho()` sanitizava (pro nome do arquivo em disco);
    a requisição de rede usava `hash_icone` cru, sem passar pelo mesmo
    filtro. O host de destino é fixo (`_CDN_URL_TPL` já tem o domínio
    embutido antes do `{hash}`, então não dá pra redirecionar pra outro
    host por aqui), mas um hash arbitrário ainda fazia o servidor buscar
    (e cachear em disco) qualquer path dentro de steamstatic.com por
    conta de qualquer um -- sanitiza ANTES de usar nos dois lugares,
    não só no caminho do arquivo."""
    hash_seguro = "".join(c for c in (hash_icone or "") if c.isalnum())[:128]
    if not hash_seguro:
        return None
    p = _caminho(hash_seguro)
    if p.exists():
        try:
            return p.read_bytes()
        except OSError:
            pass
    try:
        import httpx
        resp = httpx.get(_CDN_URL_TPL.format(hash=hash_seguro), timeout=_TIMEOUT)
        if resp.status_code != 200 or not resp.content:
            return None
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        p.write_bytes(resp.content)
        return resp.content
    except Exception:
        return None
