"""Varre o site público implantado em busca de link interno quebrado.

Começa em `/`, segue só links do MESMO domínio (nunca Steam/GitHub/
externos -- isso quebraria o orçamento de requisições deles, não o
nosso), e reporta qualquer `<a href>` que devolva 4xx/5xx. Não é
substituto de teste automatizado (roda contra o site de VERDADE, depois
de um deploy) -- mesmo espírito do `smoke_test.py`, mas pra achar link
morto que a lista fixa de rotas dele não cobre (ex. um /item/<nome> que
sumiu do scan mais recente).

Uso:
    python scripts/check_broken_links.py https://seudominio.com
    python scripts/check_broken_links.py https://seudominio.com --limite 60
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.parse

import httpx

_HREF_RE = re.compile(r'href="([^"]+)"')


def _links_na_pagina(html: str) -> list[str]:
    return _HREF_RE.findall(html)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("base_url", help="ex: https://seudominio.com")
    parser.add_argument("--limite", type=int, default=80,
                        help="máximo de páginas a visitar (default: 80)")
    args = parser.parse_args(argv[1:])

    base = args.base_url.rstrip("/")
    host = urllib.parse.urlparse(base).netloc

    visitados: dict[str, int] = {}
    pendentes = [base + "/"]

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        while pendentes and len(visitados) < args.limite:
            url = pendentes.pop(0)
            if url in visitados:
                continue
            try:
                resp = client.get(url)
                status = resp.status_code
            except httpx.HTTPError as e:
                status = 0
                print(f"ERRO ao buscar {url}: {e}")
            visitados[url] = status
            if status >= 400 or status == 0:
                continue
            if "text/html" not in resp.headers.get("content-type", ""):
                continue
            for href in _links_na_pagina(resp.text):
                absoluto = urllib.parse.urljoin(url, href)
                partes = urllib.parse.urlparse(absoluto)
                if partes.netloc != host:
                    continue  # externo -- nunca seguir (Steam, GitHub, etc.)
                limpo = partes._replace(fragment="").geturl()
                if limpo not in visitados and limpo not in pendentes:
                    pendentes.append(limpo)

    print(f"\n{len(visitados)} página(s) visitada(s).")
    quebrados = {u: s for u, s in visitados.items() if s >= 400 or s == 0}
    for url, status in quebrados.items():
        print(f"QUEBRADO  {url}  ({status})")

    if not quebrados:
        print("Nenhum link quebrado encontrado.")
    return 1 if quebrados else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
