# SkinVault  *(nome de trabalho — pode trocar)*

Painel de controle **local** do teu inventário de CS2. **Teus dados ficam no teu PC.**

## A ideia em uma linha
Um app desktop que mostra quanto vale teu inventário, se você está pagando caro numa
skin, e te avisa quando o preço de algo que você quer cai — **sem nunca pedir teu
login do Steam.**

## Por que existe (o diferencial / o "moat")
As ferramentas populares (SIH e cia.) rodam dentro da tua sessão do navegador e podem
**agir pela tua conta** — por isso o medo recorrente de *"isso é seguro?"*. O SkinVault
só lê **dados públicos** (teu SteamID + preços públicos do Market). Ele **não loga, não
automatiza ação de conta** — então não tem como roubar item nem te dar ban. Ele
**informa**; o clique de comprar é teu, no Steam.

## Pra quem é
O **colecionador / jogador** que quer cuidar do que tem e não ser passado pra trás.
**NÃO** é ferramenta de flip/arbitragem — flip esbarra na taxa de ~15% do Steam + grana
presa na Wallet, e atrai o público de aposta. O valor limpo está no comprador.

## Escopo (MVP primeiro — não construir tudo de uma vez)
- **v1 (MVP):** SteamID → inventário + valor total + gráfico de valor no tempo +
  veredito "tá caro/barato" por skin.
- **v2:** Watchlist + alerta de preço (notificação desktop).
- **v3:** Radar de 2025 (impacto de trade-up, risco da reversão de 8 dias), multi-mercado.

## Stack
Reaproveita o que já domino do projeto Future: **Python + PyQt6** (UI), chamadas de
**API pública** (`httpx` — mais simples que automação de navegador), empacotamento em
**.exe** (PyInstaller). O motor é quase o mesmo do bot, repontado: feed ao vivo →
inventário; gráfico de saldo → gráfico de valor; alerta na tray → alerta de preço.

## Como pretende ganhar (honesto)
- **Grátis:** valor do inventário + gráfico básico.
- **Pago** (licença única via Gumroad/Lemon Squeezy): alertas, histórico longo, mais análise.
- O colecionador paga **você** em vez do tool web grátis porque confia nos dados ficarem
  no PC dele.

## Nota honesta (não apagar)
Tem concorrente **grátis** nesse mercado. Antes de investir semanas, **validar** que o
colecionador paga pelo ângulo trust/local (ex.: post no r/GlobalOffensiveTrade). Isto
aqui é aposta de **portfólio EM CIMA** de renda ativa (freela) — não no lugar dela.

## Status
Pré-MVP. Esqueleto montado. **Próximo passo:** o "momento mágico" — `steam_api.py`
puxando o valor de um inventário real a partir de um SteamID.
