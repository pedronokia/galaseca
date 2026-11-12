"""Gera as imagens de fixture da regressão visual (roda uma vez).

Uso:  python tests/visual/fixtures/_gerar_fixtures.py

Desenha ícones 192px e 384px totalmente determinísticos (degradê fixo +
formas geométricas em posições fixas, zero aleatoriedade) e grava os
.WebP com qualidade fixa -- os bytes comitados são a FONTE; este script
nunca precisa rodar de novo a menos que o design da fixture mude de
propósito. Os nomes seguem `<hash>-<tamanho>.webp`, o mesmo par que
`visual_regression.py` copia para `DATA_DIR/icon_cache/<hash>.v3.<tam>.webp`.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

PASTA = Path(__file__).resolve().parent

# (hash, cor inicial do degradê, cor final, cor das formas)
PALETAS = [
    ("fixa-galaseca", (0, 113, 227), (0, 40, 90), (255, 255, 255)),
    ("fixb-galaseca", (249, 115, 22), (120, 40, 0), (255, 245, 230)),
]


def _desenhar(tamanho: int, inicio, fim, formas) -> Image.Image:
    """Ícone quadrado: degradê vertical + círculo + arco + anel."""
    imagem = Image.new("RGB", (tamanho, tamanho), fim)
    pixel = imagem.load()
    for y in range(tamanho):
        t = y / (tamanho - 1)
        cor = tuple(
            round(inicio[i] + (fim[i] - inicio[i]) * t) for i in range(3))
        for x in range(tamanho):
            pixel[x, y] = cor
    desenho = ImageDraw.Draw(imagem)
    # Círculo central (40% do lado) e anel fino (60%).
    desenho.ellipse(
        [0.30 * tamanho, 0.30 * tamanho, 0.70 * tamanho, 0.70 * tamanho],
        fill=formas)
    desenho.ellipse(
        [0.45 * tamanho, 0.45 * tamanho, 0.55 * tamanho, 0.55 * tamanho],
        fill=(round(inicio[0] * 0.4), round(inicio[1] * 0.4),
              round(inicio[2] * 0.4)))
    desenho.arc(
        [0.20 * tamanho, 0.20 * tamanho, 0.80 * tamanho, 0.80 * tamanho],
        start=200, end=90, fill=formas, width=max(2, tamanho // 48))
    # Cantos: dois tracinhos horizontais (mesma posição relativa em
    # qualquer tamanho -- os 192px são um "retrato fiel" dos 384px).
    y_top = round(0.10 * tamanho)
    y_bottom = round(0.88 * tamanho)
    desenho.line(
        [round(0.08 * tamanho), y_top, round(0.30 * tamanho), y_top],
        fill=formas, width=max(1, tamanho // 96))
    desenho.line(
        [round(0.70 * tamanho), y_bottom, round(0.92 * tamanho), y_bottom],
        fill=formas, width=max(1, tamanho // 96))
    return imagem


def main() -> None:
    for hash_icone, inicio, fim, formas in PALETAS:
        for tamanho in (192, 384):
            destino = PASTA / f"{hash_icone}-{tamanho}.webp"
            _desenhar(tamanho, inicio, fim, formas).save(
                destino, format="WEBP", quality=80, method=4)
            print(f"gerado: {destino.name}")


if __name__ == "__main__":
    main()
