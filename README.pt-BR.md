# SkinVault

*English version: [README.md](README.md)*

App desktop e web para acompanhar inventário e mercado de skins de **CS2**: quanto vale o que
você tem, quanto você realmente lucrou depois das taxas, e quais itens estão com sinais
de preço interessantes. **Roda 100% local e nunca pede login da Steam** — só lê dados
públicos.

| Scanner de oportunidades | Consulta de mercado |
|---|---|
| ![Scanner](prints/04-scanner.png) | ![Mercado](prints/05-market.png) |
| **Watchlist e alertas** | **Carteira** |
| ![Watchlist](prints/07-watchlist.png) | ![Carteira](prints/01-account.png) |

## O que ele faz

- **Carteira com lucro real** — avalia o inventário público a partir do SteamID e calcula
  P&L **líquido** já descontando a taxa de ~15% do Market, com evolução do valor no tempo.
- **Scanner de oportunidades** — analisa categorias inteiras (rifles, facas, luvas…) e dá
  a cada item um score 0–100 com **breakdown explicável**: preço vs. mediana, spread,
  livro de ofertas, tendência, oferta/demanda, momentum e liquidez.
- **Comparação entre mercados** — confronta o preço Steam com marketplaces de dinheiro
  real (medido em 732 itens: a Steam fica ~36% acima na mediana).
- **Watchlist com alertas** — regras de queda de preço, alvo, pico de volume e queda de
  oferta, com rearme automático e notificação nativa do Windows.
- **Histórico de trades** — taxa de acerto, sequência de resultados, filtros por período.
- **Monitor de eventos do jogo** — detecta mudanças no `items_game.txt` (rotação de drop
  pool, caixas novas) que costumam mexer no mercado.
- **Backup/restauração** dos dados locais e exportação de histórico.

## Decisões de engenharia

**Rate limit da Steam como restrição de projeto.** Os endpoints públicos bloqueiam após
algumas dezenas de chamadas. Por isso o cache é requisito, não otimização: cada página do
Market traz até ~10 variantes do mesmo skin (desgaste × Normal/StatTrak/Souvenir) e o app
grava o lote inteiro de uma vez, cortando o custo de rede em até 10×.

**Sem login, por escolha.** Uma versão anterior sincronizava a conta via cookies de
sessão. Depois de ler o Steam Subscriber Agreement (que proíbe automação sobre a conta),
a funcionalidade foi **removida** — o app ficou só com dados públicos e anônimos, sem
risco de banimento para o usuário.

**Fatos, não previsões.** O scanner descreve o que os dados mostram e explica cada ponto
do score; ele não promete para onde o preço vai.

**Armadilhas de dados documentadas.** Ex.: o endpoint de inventário é servido por CDN e
devolve snapshots velhos (exige cache-buster); a busca por nome precisa de match exato,
senão "StatTrak™ X" devolve a série errada em silêncio. Essas armadilhas estão registradas
em [`AGENTS.md`](AGENTS.md).

## Stack

- **Python 3.9+**, **PyQt6** (UI desktop), **Flask + pywebview** (UI web), **httpx** (HTTP)
- Gráficos desenhados à mão com `QPainter` (sparklines, livro de ofertas, barras, área) —
  sem bibliotecas de charting
- Threads de rede isoladas da UI via `QObject` + sinais
- Empacotado como `.exe` com PyInstaller; dados em `%APPDATA%\SkinVault`

## Números

- ~32 mil linhas de código de aplicação
- **2.394 testes** automatizados (pytest), ~28 mil linhas de teste, rodando em ~1 min
- HTTP isolado num único ponto de mock, então a suíte roda sem rede

## Rodando

```bash
python -m venv venv
venv\Scripts\activate          # Windows  (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt
python -m skinvault --ui        # abre o app desktop
python -m skinvault --web       # abre a interface web
python -m skinvault <SteamID64> # avalia um inventário público pelo terminal
```

Testes:

```bash
pip install pytest
pytest
```

## Estrutura

```
skinvault/
  steam_api.py     acesso público à Steam (inventário, preços, busca, histórico)
  signals.py       sinais e score explicável do scanner
  markets.py       preços de outros mercados para comparação
  alerts.py        motor de regras de alerta
  portfolio.py     avaliação de carteira com taxas
  ssr_cache.py     cache de histórico de preços (TTL 24h)
  gamedata.py      monitor de mudanças nos dados do jogo
  ui/              uma tela por arquivo + componentes e tema
  webapp/          interface web (Flask + pywebview), uma rota por tela
tests/             suíte pytest
```

## Aviso

Projeto pessoal, sem afiliação com a Valve. Não faz recomendação de investimento: os
números são descritivos.
