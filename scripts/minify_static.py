"""Minifica style.css/app.js IN-PLACE -- chamado só no build da imagem
Docker (Dockerfile.public-site), nunca sobre o código-fonte do repositório
(a cópia minificada vive dentro da imagem, não no Git).

Minificação "leve" de propósito: só remove comentário e linha em branco
ociosa, nunca reescreve token. Um minificador de JS de verdade precisa de
um parser pra não quebrar string literal/regex -- sem isso aqui, arriscado
demais pra um ganho pequeno (os dois arquivos juntos têm poucos KB). CSS
usa a mesma lógica conservadora, mesmo sendo mais seguro de comprimir.

Uso: `python scripts/minify_static.py [pasta]` (default:
skinvault/public_site/static).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_PASTA_DEFAULT = Path("skinvault/public_site/static")


def minify_css(texto: str) -> str:
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.DOTALL)
    linhas = [l.strip() for l in texto.splitlines()]
    return "\n".join(l for l in linhas if l) + "\n"


def minify_js(texto: str) -> str:
    # Só remove bloco /* */ e linha que COMEÇA com "//" (depois de
    # trim) -- nunca um "// comentário" no fim de uma linha de código,
    # que poderia estar dentro de uma string ("http://..." não começa
    # a linha com "//", então não bate aqui).
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.DOTALL)
    linhas = []
    for linha in texto.splitlines():
        if linha.strip().startswith("//"):
            continue
        linhas.append(linha.rstrip())
    return "\n".join(l for l in linhas if l.strip()) + "\n"


def main(argv: list[str]) -> None:
    pasta = Path(argv[1]) if len(argv) > 1 else _PASTA_DEFAULT
    css = pasta / "style.css"
    js = pasta / "app.js"
    if css.exists():
        antes = len(css.read_bytes())
        css.write_text(minify_css(css.read_text(encoding="utf-8")), encoding="utf-8")
        print(f"style.css: {antes} -> {len(css.read_bytes())} bytes")
    if js.exists():
        antes = len(js.read_bytes())
        js.write_text(minify_js(js.read_text(encoding="utf-8")), encoding="utf-8")
        print(f"app.js: {antes} -> {len(js.read_bytes())} bytes")


if __name__ == "__main__":
    main(sys.argv)
