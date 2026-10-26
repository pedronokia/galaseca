"""Smoke test pós-deploy: confirma que as rotas principais do site
público respondem com o status esperado.

Não substitui a suíte de testes (que roda contra o código, sem rede) --
isto é contra o site de VERDADE, depois de um deploy, pra pegar erro de
config/infra que só aparece em produção (env var faltando, Caddy mal
configurado, etc.).

Uso:
    python scripts/smoke_test.py https://seudominio.com
"""
from __future__ import annotations

import sys

import httpx

# (caminho, status esperado) -- /admin sem token sempre nega (404), por
# isso está na lista: confirma que a rota continua fechada por padrão.
_ROTAS = [
    ("/healthz", 200),
    ("/readyz", 200),
    ("/", 200),
    ("/sobre", 200),
    ("/metodo", 200),
    ("/faq", 200),
    ("/status", 200),
    ("/ranking", 200),
    ("/privacidade", 200),
    ("/api/recommendations", 200),
    ("/api/health", 200),
    ("/robots.txt", 200),
    ("/sitemap.xml", 200),
    ("/feed.xml", 200),
    ("/static/manifest.json", 200),
    ("/sw.js", 200),
    ("/admin", 404),
    ("/pagina-que-nao-existe", 404),
]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Uso: python scripts/smoke_test.py https://seudominio.com")
        return 2
    base = argv[1].rstrip("/")
    falhas = 0
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        for caminho, esperado in _ROTAS:
            url = base + caminho
            try:
                resp = client.get(url)
                ok = resp.status_code == esperado
            except httpx.HTTPError as e:
                ok = False
                resp = None
                print(f"ERRO  {caminho}: {e}")
            if resp is not None:
                marca = "OK  " if ok else "FALHOU"
                print(f"{marca} {caminho}: {resp.status_code} (esperado {esperado})")
            if not ok:
                falhas += 1
    print(f"\n{len(_ROTAS) - falhas}/{len(_ROTAS)} rotas OK")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
