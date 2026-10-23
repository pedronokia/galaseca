# SkinVault — site público

Dashboard público de recomendações (Fase 1) + login "Entrar com Steam" com
portfólio/trades/watchlist pessoais (Fase 2). Pacote separado do app
desktop (`skinvault/ui/`, `skinvault/webapp/`) e sem nenhuma dependência
deles — ver `AGENTS.md` do repositório pra contexto completo de por quê.

## Dois processos, sempre

- **`web`** — serve as páginas (`server.py`/`wsgi.py`). Só LÊ dado já
  guardado (cache de preço, `scan_store.json`, SQLite). Nunca fala com a
  Steam numa requisição de visitante.
- **`worker`** (`worker.py`) — o ÚNICO processo que fala com a Steam.
  Escaneia a cada `SKINVAULT_WORKER_INTERVAL_HORAS` (default 6h),
  respeitando o mesmo limite de ~20 req/min de sempre.

Se só o `web` estiver no ar, o dashboard mostra "nenhum scan salvo" pra
sempre — o `worker` é obrigatório, não opcional.

## Variáveis de ambiente

| Variável | Pra quê | Default |
|---|---|---|
| `SKINVAULT_DATA_DIR` | Onde fica `public_site.db`, `scan_store.json`, `public_site_secret.key`, etc. **Precisa de disco persistente** — se o volume não sobrevive a um redeploy, toda conta/portfólio/trade é perdida. | `data/` do repositório |
| `PORT` | Porta que o `web` escuta — a maioria dos provedores injeta essa variável sozinha. | `8000` |
| `SKINVAULT_WORKER_INTERVAL_HORAS` | Intervalo entre ciclos do `worker`. | `6` |
| `SKINVAULT_PUBLIC_SITE_SECURE_COOKIES` | `1` em produção (HTTPS) pra marcar o cookie de sessão como `Secure`. Deixe **vazio/ausente** testando local em `http://`, senão o navegador descarta o cookie e o login nunca "pega". | ausente |

## Rodar local (sem Docker)

```bash
python scripts/dev_public_site.py          # web, http://127.0.0.1:5061
python -m skinvault.public_site.worker      # worker, noutro terminal
```

## Rodar com Docker

```bash
docker compose -f docker-compose.public-site.yml up --build
```

Sobe `web` (porta 8000) e `worker`, compartilhando um volume Docker pro
`SKINVAULT_DATA_DIR`. Pra produção de verdade (hospedagem com domínio e
HTTPS), ver a seção abaixo.

## Hospedagem — o que importa antes de escolher

1. **Precisa de dois processos** (`web` + `worker`) — confirme que o plano/
   provedor escolhido cobre os dois (muitos free tier só dão UM processo
   web, sem worker em background).
2. **Precisa de disco persistente** pro `SKINVAULT_DATA_DIR` — sem isso,
   toda conta criada por login Steam, todo portfólio/trade/watchlist some
   no próximo deploy ou reinício. Container efêmero (sem volume) só serve
   pro `web` de um dashboard público puro, sem login nenhum.
3. **HTTPS correto importa pro login.** `server.py` já aplica `ProxyFix`
   (confia em `X-Forwarded-Proto` de um proxy reverso), mas o provedor
   precisa terminar HTTPS de verdade — login Steam (OpenID) exige que o
   `realm`/`return_to` enviado bata com o protocolo real.
4. **Nenhum hosting específico está configurado aqui de propósito** — o
   `Dockerfile.public-site` roda em qualquer host que aceite uma imagem
   Docker com volume persistente (VPS com Docker, Fly.io, Render com disco
   pago, etc.). Termos de free tier mudam com frequência: confirme no
   provedor escolhido, no momento do deploy, que os itens 1-2 acima estão
   cobertos — não assuma pelo que este arquivo diz hoje.

## Backup

`public_site.db` (contas + portfólio/trades/watchlist de todo mundo) é um
arquivo SQLite só — copiar esse arquivo é o backup inteiro. Fazer isso
periodicamente, fora do volume de produção, é responsabilidade de quem
operar o site (nada aqui agenda backup automático ainda).
