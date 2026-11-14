"""Gera lodout/public_site/static/og-image.png (prévia padrão ao
compartilhar o site) a partir de og_cards.cartao_padrao().

Uso: python scripts/gerar_og_image.py
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lodout.public_site import og_cards  # noqa: E402

destino = (Path(__file__).resolve().parent.parent / "lodout" / "public_site"
           / "static" / "og-image.png")
destino.write_bytes(og_cards.cartao_padrao())
print(destino)
