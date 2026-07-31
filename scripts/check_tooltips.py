"""Audita QPushButton sem setToolTip em arquivos user-facing.

Regra do projeto: todo botao precisa de tooltip explicando o que acontece
ao clicar. O check varre `skinvault/gui.py` e `skinvault/ui/*.py` procurando
linhas `<var> = QPushButton(...)` e verifica se `<var>.setToolTip(` aparece
ate 10 linhas depois. Reporta faltantes com path:linha:texto.

Uso:
    python scripts/check_tooltips.py
    # exit 0 = tudo OK, exit 1 = ha botoes sem tooltip
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [ROOT / "skinvault" / "gui.py"] + sorted(
    (ROOT / "skinvault" / "ui").glob("*.py")
)

ASSIGN_RE = re.compile(r"^(\s*)((?:self\.)?_?\w+)\s*=\s*QPushButton\(")
WINDOW = 10  # linhas depois pra procurar setToolTip


def audit_file(path: Path) -> list[tuple[int, str, str]]:
    """Retorna [(line_no, var_name, snippet)] de botoes sem tooltip."""
    lines = path.read_text(encoding="utf-8").splitlines()
    missing: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        m = ASSIGN_RE.match(line)
        if not m:
            continue
        var = m.group(2)
        tooltip_pat = re.compile(
            r"\b" + re.escape(var) + r"\.setToolTip\("
        )
        window = lines[i : i + 1 + WINDOW]
        if any(tooltip_pat.search(w) for w in window):
            continue
        missing.append((i + 1, var, line.strip()))
    return missing


def main() -> int:
    total = 0
    for path in TARGETS:
        if not path.exists():
            continue
        misses = audit_file(path)
        if not misses:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for line_no, var, snippet in misses:
            print(f"{rel}:{line_no}: {var}  -- {snippet}")
            total += 1
    if total:
        print(f"\n{total} botao(s) sem setToolTip em ate {WINDOW} linhas.")
        return 1
    print("OK: todo QPushButton tem setToolTip em ate 10 linhas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
