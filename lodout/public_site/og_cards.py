"""Imagens de prévia (Open Graph, 1200x630) pra quando um link do Lodout
é colado no Discord, WhatsApp, X etc.

- `cartao_padrao()`: marca + frase do site. Gera o `static/og-image.png`
  (via scripts/gerar_og_image.py) usado pelas páginas sem imagem própria.
- `cartao_item(...)`: um por item, com ícone, nome, nota, preço e a cor
  da raridade. Feito só com dado já guardado (scan + ícone já em cache
  local): gerar a prévia nunca consulta a Steam nem o CDN dela.

Pillow já é dependência do site (icon_cache.py); a fonte é a mesma Inter
variável que o site serve (static/fonts), com eixo de peso.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from lodout import _paths
from lodout._paths import atomic_write_bytes

LARGURA, ALTURA = 1200, 630
_FONTE = Path(__file__).parent / "static" / "fonts" / "inter-latin-opsz-normal.woff2"

# Mesmas cores do tema (style.css :root e .raridade-*, .nota-*).
_FUNDO = (22, 22, 22)          # --bg #161616
_SUPERFICIE = (30, 30, 30)     # --surface #1e1e1e
_TEXTO = (255, 255, 255)
_TEXTO_FRACO = (179, 179, 179)  # --text-muted
_LARANJA = (249, 115, 22)      # --accent
_CORES_NOTA = {"alta": (34, 160, 74), "media": (217, 119, 6),
               "baixa": (179, 179, 179)}
_CORES_RARIDADE = {
    "consumer": (176, 195, 217), "industrial": (94, 152, 217),
    "milspec": (75, 105, 255), "restricted": (136, 71, 255),
    "classified": (211, 44, 230), "covert": (235, 75, 75),
    "dourado": (228, 174, 57),
}
# Cache em disco: ~185 itens x poucas dezenas de KB. Teto pra não
# acumular versões antigas (nota/preço mudam a cada coleta).
_CACHE_MAX_ARQUIVOS = 800


def _fonte(tamanho: int, peso: int = 400) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(_FONTE), tamanho)
    try:
        f.set_variation_by_axes([32 if tamanho >= 32 else 14, peso])
    except (OSError, ValueError):
        pass
    return f


def _quebrar(texto: str, fonte, largura_max: int, linhas_max: int) -> "list[str]":
    """Quebra por palavra; corta com reticências se passar de linhas_max."""
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        teste = f"{atual} {p}".strip()
        if fonte.getlength(teste) <= largura_max:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    if len(linhas) > linhas_max:
        linhas = linhas[:linhas_max]
        ultima = linhas[-1]
        while ultima and fonte.getlength(ultima + "…") > largura_max:
            ultima = ultima[:-1]
        linhas[-1] = ultima.rstrip() + "…"
    return linhas


def _aspas(d: ImageDraw.ImageDraw, x: int, y: int, tamanho: int,
           cor=_LARANJA) -> None:
    """As aspas do logo: o caractere “ da própria Inter, em negrito."""
    d.text((x, y), "\u201c", font=_fonte(tamanho, 800), fill=cor)


def _estrela(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
             cor) -> None:
    """★ desenhada (a Inter servida pelo site não tem o glifo)."""
    import math
    pontos = []
    for i in range(10):
        raio = r if i % 2 == 0 else r * 0.45
        ang = -math.pi / 2 + i * math.pi / 5
        pontos.append((cx + raio * math.cos(ang), cy + raio * math.sin(ang)))
    d.polygon(pontos, fill=cor)


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def cartao_padrao() -> bytes:
    img = Image.new("RGB", (LARGURA, ALTURA), _FUNDO)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, LARGURA, 10], fill=_LARANJA)
    _aspas(d, 92, 70, 220)
    d.text((96, 245), "Lodout", font=_fonte(150, 750), fill=_TEXTO)
    frase = "Notas e preços de skins de CS2,\ncom dados públicos da Steam."
    y = 430
    for linha in frase.split("\n"):
        d.text((100, y), linha, font=_fonte(42, 450), fill=_TEXTO_FRACO)
        y += 56
    d.text((100, ALTURA - 70), "lodout.com", font=_fonte(30, 600),
           fill=_LARANJA)
    return _png(img)


def _nota_classe(nota: "int | float | None") -> str:
    nota = nota or 0
    return "alta" if nota >= 70 else ("media" if nota >= 45 else "baixa")


def cartao_item(nome_fmt: str, nota: "int | None", preco_fmt: str,
                raridade: "str | None" = None,
                icone: "bytes | None" = None) -> bytes:
    """1200x630: ícone à esquerda (se houver), nome, nota e preço."""
    cor_rar = _CORES_RARIDADE.get(raridade or "", _LARANJA)
    img = Image.new("RGB", (LARGURA, ALTURA), _FUNDO)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, LARGURA, 10], fill=cor_rar)

    # Quadro do ícone, com o fio da cor de raridade (como no site).
    qx, qy, qt = 70, 105, 420
    d.rounded_rectangle([qx, qy, qx + qt, qy + qt], radius=28,
                        fill=_SUPERFICIE, outline=cor_rar, width=4)
    if icone:
        try:
            ic = Image.open(io.BytesIO(icone)).convert("RGBA")
            ic.thumbnail((qt - 60, qt - 60), Image.LANCZOS)
            img.paste(ic, (qx + (qt - ic.width) // 2,
                           qy + (qt - ic.height) // 2), ic)
        except Exception:
            icone = None
    if not icone:
        _aspas(d, qx + qt // 2 - 75, qy + qt // 2 - 120, 260,
               cor=(90, 90, 90))

    x = qx + qt + 60
    largura_txt = LARGURA - x - 70
    y = 110
    f_nome = _fonte(54, 700)
    estrela = nome_fmt.startswith("★")
    nome = nome_fmt.lstrip("★ ").strip() if estrela else nome_fmt
    recuo = 50 if estrela else 0
    for i, linha in enumerate(_quebrar(nome, f_nome, largura_txt - recuo, 3)):
        if i == 0 and estrela:
            _estrela(d, x + 19, y + 33, 20, cor_rar)
            d.text((x + recuo, y), linha, font=f_nome, fill=_TEXTO)
        else:
            d.text((x, y), linha, font=f_nome, fill=_TEXTO)
        y += 66

    y = max(y + 24, 330)
    if nota is not None:
        d.text((x, y), "Nota", font=_fonte(30, 500), fill=_TEXTO_FRACO)
        d.text((x, y + 34), f"{int(nota)}", font=_fonte(120, 800),
               fill=_CORES_NOTA[_nota_classe(nota)])
        d.text((x + _fonte(120, 800).getlength(f"{int(nota)}") + 14, y + 104),
               "/100", font=_fonte(34, 500), fill=_TEXTO_FRACO)
    if preco_fmt:
        # Depois do "87 /100" de verdade: nota 100 tem 3 dígitos.
        fim_nota = x
        if nota is not None:
            fim_nota = (x + _fonte(120, 800).getlength(f"{int(nota)}") + 14
                        + _fonte(34, 500).getlength("/100"))
        px = max(x + 300, int(fim_nota) + 50)
        tam = 56
        while tam > 34 and _fonte(tam, 700).getlength(preco_fmt) > LARGURA - 60 - px:
            tam -= 2
        d.text((px, y), "Preço", font=_fonte(30, 500), fill=_TEXTO_FRACO)
        d.text((px, y + 62 + (56 - tam) // 2), preco_fmt,
               font=_fonte(tam, 700), fill=_TEXTO)

    f_rod = _fonte(30, 600)
    d.text((x, ALTURA - 70), "lodout.com", font=f_rod, fill=_LARANJA)
    d.text((x + f_rod.getlength("lodout.com") + 12, ALTURA - 70),
           "· dados públicos da Steam", font=_fonte(30, 400),
           fill=_TEXTO_FRACO)
    return _png(img)


def _dir_cache() -> Path:
    return Path(_paths.DATA_DIR) / "og_cache"


def cartao_item_em_cache(nome_fmt: str, nota, preco_fmt: str,
                         raridade: "str | None",
                         icone: "bytes | None") -> bytes:
    """`cartao_item` com cache em disco pela combinação dos dados -- nota
    ou preço novos geram arquivo novo; os velhos saem pelo teto."""
    chave = hashlib.sha1("|".join([
        nome_fmt, str(nota), preco_fmt, raridade or "",
        hashlib.sha1(icone).hexdigest() if icone else "-",
        "v2"]).encode("utf-8")).hexdigest()
    pasta = _dir_cache()
    caminho = pasta / f"{chave}.png"
    try:
        return caminho.read_bytes()
    except OSError:
        pass
    dados = cartao_item(nome_fmt, nota, preco_fmt, raridade, icone)
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(caminho, dados)
        arquivos = sorted(pasta.glob("*.png"), key=lambda p: p.stat().st_mtime)
        for velho in arquivos[:-_CACHE_MAX_ARQUIVOS]:
            velho.unlink(missing_ok=True)
    except OSError:
        pass
    return dados
