---
name: lodout-visual-check
description: Rodar a regressão visual do site lodout.com (captura as telas com Playwright e compara com as imagens-base) — usar quando pedir para conferir o visual, validar uma mudança de layout, regerar as imagens-base ou investigar drift entre telas do site.
---

# lodout-visual-check

Regressão visual do site público do repo `lodout`. O script é
`tests/visual/visual_regression.py`: semeia um dataset fixo, congela o
relógio, sobe o Flask em thread e captura 6 telas (home, ranking e
página de item × 1280x900 e 390x844) com Playwright, bloqueando toda
rede externa. Compara pixel a pixel contra `tests/visual/baseline/`
(canal ≤16 de diferença; no máximo 0,5% dos pixels mudados).

## Regra de ouro

**Imagens-base só valem renderizadas no Linux do CI.** No Windows a
pilha de fontes é outra — capturas locais servem para INSPEÇÃO
(`tests/visual/current/`, ignorado pelo git), nunca para virar base.
Nunca commite PNG gerado no Windows em `tests/visual/baseline/`.

## Conferir visual localmente (rápido, pra olhar)

```powershell
# no repo lodout
python tests/visual/visual_regression.py   # captura em tests/visual/current/
```

Abra os PNGs de `tests/visual/current/` para inspecionar. Sem base
comparável no Windows, o script avisa "sem base" e sai 0 — é esperado.

## Validar no CI (é isso que decide)

O job `visual` de `.github/workflows/tests.yml` roda a cada push/PR:

1. Captura no ubuntu-latest e compara com a base comitada;
2. Diferença acima da tolerância → job falha (diff ampliado vai no
   artefato `visual-diff`, junto com `relatorio.json` por página).

```bash
gh run list --workflow tests --limit 3
gh run view <id> --json jobs --jq '.jobs[] | {name, conclusion}'
gh run download <id> --name visual-diff   # diffs + relatorio.json
```

## Regerar a base (mudança de layout DE propósito)

1. Commita o layout novo e faz push;
2. Dispara a regeneração (roda no Linux):

```bash
gh workflow run tests --field atualizar_baselines=true --ref main
gh run watch <id> --exit-status --interval 15
gh run download <id> --name visual-baselines --dir baselines-novas
```

3. Copia os 6 PNGs para `tests/visual/baseline/`, commita e push. Este
   commit é o registro de quando a identidade visual mudou.

Alternativa pela UI: Actions → tests → Run workflow → marcar
"atualizar_baselines".

## Teste de contrato (sem navegador, rápido)

`python -m pytest tests/test_design_contract.py` trava os tokens Apple
no `style.css` (fonte Inter Variable auto-hospedada com @font-face,
corpo 17px/1.47/-0.022em, títulos 32/48/64 peso 600, pílula 980px,
cards raio 18px sem sombra, rodapé #f5f5f7 12px, grade 980px) e a
existência dos arquivos de fonte/licença OFL em `static/fonts/`. Se um
token mudar de propósito, ajuste o teste no mesmo commit.

## Se a base divergir sem motivo aparente

- O CI atualizou a imagem do runner (fontes/lib novas): regenere a base
  e commite — tolerância por pixel cobre antialiasing, não fontes novas;
- Alguém mexeu em CSS/template: compare o diff ampliado por página para
  achar o elemento e decida se é bug ou mudança de propósito;
- Ajustes finos de tolerância: `--tolerancia` (canal 0-255) e
  `--fracao-max` (0-1) no script, e o job do CI usa os padrões.
