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
| `SKINVAULT_ADMIN_PASSWORD_HASH` | Hash da senha do `/admin/login` (gerar com `scripts/hash_admin_password.py`). Sem ela, a rota sempre devolve 404. | ausente |
| `SKINVAULT_ADMIN_DISCORD_WEBHOOK` | Webhook do Discord do DONO (não do usuário) pra alertar quando o worker passar `SKINVAULT_WORKER_ALERT_HORAS` sem trazer item nenhum -- ver `worker_alert.py`. | ausente (sem alerta) |
| `SKINVAULT_WORKER_ALERT_HORAS` | Horas sem sucesso antes do alerta acima disparar. | `3` |

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

## Proteção contra abuso

`rate_limit.py` limita tentativas por IP em `/login`/`/login/callback`
(10/min) e nos formulários de `/conta` (30/min) — hand-rolled, em
memória, sem dependência nova (mesmo espírito do disjuntor de rate
limit da Steam). **Limitação real:** o contador é por PROCESSO, não
compartilhado entre workers do gunicorn — com `--workers 2` o limite
efetivo dobra (2x10/min, 2x30/min). Suficiente contra um script ingênuo
martelando uma rota; não é proteção contra um ataque distribuído de
verdade. Se o tráfego justificar mais rigor, trocar por um backend
compartilhado (Redis via Flask-Limiter, por exemplo) é o próximo passo
natural — não implementado aqui de propósito, pra não trazer
dependência/infra nova sem necessidade comprovada.

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

## Deploy numa VM (ex. Oracle Cloud "Always Free")

Escolhido por ser a única opção pesquisada em 2026 que entrega os três
requisitos acima sem comprometer nada: VM de verdade (sem container
"dormindo"), disco persistente incluso, sem limite de tempo.
`docker-compose.oracle.yml` soma HTTPS automático (Caddy + Let's Encrypt)
por cima do `docker-compose.public-site.yml`, sem alterar `web`/`worker`.

1. Crie a instância (shape Ampere `VM.Standard.A1.Flex`, Ubuntu), com IP
   público. Abra as portas **80 e 443** (TCP) tanto na *Security List*/NSG
   da VCN (painel da Oracle) quanto no firewall do SO (`iptables`/`ufw`
   dentro da VM) — a Oracle filtra nos dois lugares, e esquecer um deles é
   o erro mais comum. **Não abra a 8000** — ela só precisa ser alcançável
   de dentro da própria VM (o Caddy fala com `web:8000` pela rede interna
   do Docker).
2. Instale Docker + plugin Compose na VM (`curl -fsSL https://get.docker.com | sh`
   e `apt install docker-compose-plugin`, ou o pacote equivalente da
   distro).
3. Aponte um domínio pro IP público da VM (registro DNS tipo A). Sem
   domínio próprio, um serviço gratuito como DuckDNS resolve — Caddy só
   precisa de um nome que resolva de verdade, não de um domínio pago.
4. Copie o repositório pra VM (`git clone`) e rode:
   ```bash
   SITE_DOMAIN=seudominio.exemplo docker compose \
     -f docker-compose.public-site.yml -f docker-compose.oracle.yml \
     up --build -d
   ```
   Na primeira subida o Caddy pede o certificado Let's Encrypt sozinho —
   não precisa de `certbot` nem configuração manual de TLS.
5. Confirme em `https://seudominio.exemplo/healthz` → `{"ok": true}`.

## Backup

`db_backup.py` roda a cada ciclo do `worker` (chamado de dentro de
`run_once`) e faz um backup rotativo LOCAL de `public_site.db` em
`DATA_DIR/backups/`, via `sqlite3.Connection.backup()` (seguro mesmo com
o `web` escrevendo ao mesmo tempo) -- no máximo 1 por dia, guarda os
últimos 7. O mesmo ciclo também zipa `scanner_last.json`/
`scan_historico.json`/`rankings.json` (os JSON globais do dashboard) em
`DATA_DIR/backups/json-*.zip`, mesma cadência -- até a 2a rodada
(2026-10-25) só o banco de contas tinha backup; perder esses JSON
significava perder o scan atual sem nenhum jeito de recuperar sem
esperar o próximo ciclo. Isso protege contra corrupção/bug de
aplicação, **não** contra perder a VM inteira: pra isso, copiar os
arquivos de `DATA_DIR/backups/` pra fora da VM periodicamente (`scp`)
continua sendo manual -- um destino externo de verdade (S3, Backblaze)
pediria credenciais que não dá pra configurar sem uma conta.

## Monitoramento externo (uptime)

`/healthz` já existe pronto pra isso -- responde `{"ok": true}` sempre
que o processo `web` está de pé (não verifica se o scan está fresco; pra
isso, ver `/api/health`). Serviços gratuitos como
[UptimeRobot](https://uptimerobot.com/) ou
[Better Uptime](https://betteruptime.com/) checam essa URL a cada alguns
minutos e avisam por e-mail se parar de responder. Precisa de conta num
desses serviços -- passo que só o dono do site pode fazer (criação de
conta de terceiros não é algo que um agente de IA deveria fazer por
você).

## Deploy automático (CI/CD)

`.github/workflows/deploy.yml` roda depois que `tests.yml` passa em push
pra `main`, e faz SSH na VM pra atualizar só o `web` (nunca o `worker` --
reiniciá-lo dispara um scan na hora, o que não deve acontecer num horário
imprevisível por causa de um deploy). Precisa de 3 secrets no repositório
(Settings → Secrets and variables → Actions, só o dono configura):
`ORACLE_HOST`, `ORACLE_SSH_KEY` (conteúdo do `.key` da VM), `SITE_DOMAIN`.
Sem os secrets configurados, o workflow falha sem fazer nada (não quebra
o deploy manual, que continua funcionando do mesmo jeito de sempre).

## Painel admin

`/admin` mostra buscas populares, últimos ciclos, backups, latência por
rota, erros agregados e progresso do scan -- sem precisar de SSH. Login
de verdade em `/admin/login` (usuário único, é o dono do site -- sem
"esqueci a senha"): senha com hash via `werkzeug.security` (PBKDF2/
scrypt, zero dependência nova), sessão, sem token na URL (que vazava em
log/referrer na versão anterior). Gere o hash com:

```bash
python scripts/hash_admin_password.py
```

e cole o resultado em `SKINVAULT_ADMIN_PASSWORD_HASH` (env var). Sem
ela definida, `/admin` e `/admin/login` sempre devolvem 404 -- nunca
abre "sem senha" por padrão.

## Segurança (headers)

O Caddyfile aplica HSTS, Content-Security-Policy (`script-src 'self'` --
por isso todo JS da página fica em `static/app.js`, nunca inline, e as
violações chegam em `/api/csp-report`), `X-Content-Type-Options` e
`Referrer-Policy`. O 429 do rate limit e o 500 de erro interno têm
página própria (`429.html`/`500.html`), e todo 500 fica registrado em
`DATA_DIR/errors.log` (rotativo, 1MB x 3).

## Liveness vs. readiness

`/healthz` responde `{"ok": true}` sempre que o processo `web` está de
pé -- não confere mais nada. `/readyz` confere se dá pra abrir o banco
de contas (quando existe) sem exceção; devolve 503 com o motivo se
falhar. Um orquestrador que decide "pode receber tráfego" deveria
checar `/readyz`, não `/healthz`.

## Painel admin: métricas além dos backups

Além de backups/erros/buscas populares, o `/admin` mostra latência
média por rota (`latencia.py` -- em memória, por worker do gunicorn,
zera num restart), erros agregados por tipo e um gráfico de erros por
dia (`erro_stats.py`), e o progresso do ciclo de scan em andamento
(`scan_progress.py` -- sem isso, só dava pra ver olhando `docker logs`
do worker).

## Cache de ícone

`icon_cache.py` serve o ícone do item pelo próprio domínio
(`/icone/<hash>.jpg`), com cache em disco -- a primeira visita busca do
CDN da Steam (`steamstatic.com`, infraestrutura pública estática, sem
rate limit documentado -- diferente do market/inventory, que é o
endpoint sensível de sempre) e cacheia; todas as próximas são leitura
local. Falha de rede nunca derruba a página: cai no redirect pro CDN
direto.

## Scripts de apoio (manuais, não automáticos)

- `scripts/check_env_drift.py` -- compara as env vars esperadas (tabela
  acima) contra o ambiente atual. Rodar via SSH na VM ou
  `docker compose exec web python scripts/check_env_drift.py`.
- `scripts/check_tls_expiry.py <dominio> [dias_limite]` -- confere
  quantos dias faltam pro certificado TLS expirar (conecta de verdade
  na porta 443, sem dependência nova). `.github/workflows/tls-check.yml`
  roda isto 1x/dia contra `SITE_DOMAIN` (secret já existente do
  `deploy.yml`) e falha a Action se faltar pouco tempo.
- `scripts/minify_static.py` -- minificação leve (remove comentário/
  espaço ocioso) de `style.css`/`app.js`, chamada só dentro do
  `Dockerfile.public-site` no build da imagem; nunca roda sobre o
  código-fonte do repositório.

## Logs do container

`docker-compose.public-site.yml`/`docker-compose.oracle.yml` configuram
o driver `json-file` do Docker com `max-size: 10m, max-file: 3` pros
serviços `web`/`worker`/`caddy` -- sem isso, o log de stdout/stderr do
container (onde vai o access log do gunicorn e os `print()` do worker)
cresce sem limite no disco da VM. Separado do `errors.log` da aplicação
(que já rotacionava em 1MB) -- aquele é só os 500 registrados pelo
Flask; este é a saída bruta do processo.
