# GalaSeca

Site público para acompanhar dados observados no Steam Community Market.
Mostra preços, histórico, notas explicáveis e sinais descritivos; não prevê
retornos nem promete lucro.

O site não dispara consultas à Steam quando alguém visita uma página. Um
worker separado coleta os dados periodicamente, respeita os limites da Steam
e salva os resultados que o site exibe.

## Executar localmente

Requer Python 3.9 ou superior.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-public-site.txt
python scripts/dev_public_site.py
```

O preview local abre em `http://127.0.0.1:5061`. Para executar também o worker localmente, use outro terminal. Ele inicia
ciclos de coleta e respeita os intervalos configurados:

```powershell
python -m galaseca.public_site.worker
```

Para executar testes:

```powershell
python -m pip install pytest
python -m pytest -q
```

## Executar com Docker

```bash
docker compose -f docker-compose.public-site.yml up --build
```

O serviço `web` atende às páginas; o `worker` coleta os dados. Ambos usam o
volume persistente `skinvault_data`. Em produção, o deploy e o proxy reverso
são configurados separadamente pelos arquivos `docker-compose.oracle.yml` e
`deploy/Caddyfile`.

## Estrutura

- `galaseca/public_site/`: aplicação Flask, rotas, templates, CSS, JavaScript,
  persistência e worker do site.
- `galaseca/`: lógica de domínio usada pelo site e pelo worker (Steam pública,
  catálogo, sinais e recomendações).
- `tests/`: testes do site e da lógica compartilhada que ele utiliza.
- `scripts/dev_public_site.py`: preview local com recarga de templates.

Os arquivos em `data/` podem conter banco, chave de sessão e dados locais.
Não os apague durante limpezas de código nem os adicione ao Git.

## Princípios

- O site nunca recebe senha, cookie de sessão ou chave privada da Steam.
  Login de visitante, quando usado, passa pelo Steam OpenID.
- A coleta de preços roda no worker separado; uma visita não inicia um scan.
- Outras ações com rede acontecem apenas quando o visitante as solicita.
- Limites e períodos de espera definidos em `galaseca/steam_api.py`.
- Percentuais são expressos de 0 a 100.
- O que a tela mostra descreve dados passados; não é recomendação de
  investimento.

## Aviso

Projeto independente, sem afiliação com a Valve. Desempenho passado não
garante resultados futuros.
