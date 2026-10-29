# AlertaSkins — contexto para agentes

Este repositório mantém **um único produto: o site público AlertaSkins**.
Não recrie o app desktop nem a UI web paralela. O preview local do próprio
site (`scripts/dev_public_site.py`) e o worker de coleta continuam necessários.

## Stack e estrutura

- Python 3.9+, Flask, SQLite e `httpx`; dependências em
  `requirements-public-site.txt`.
- `skinvault/public_site/`: rotas, templates, CSS, JavaScript, autenticação,
  persistência, testes operacionais e worker do site.
- Alguns módulos de domínio em `skinvault/` são dependências diretas do site
  ou do worker (Steam pública, catálogo, coleta, recomendações, sinais,
  aposentadorias e trades). Antes de remover um módulo, confira imports diretos
  e dinâmicos e rode os testes.
- `scripts/dev_public_site.py`: preview local. Produção usa
  `Dockerfile.public-site`, `docker-compose.public-site.yml`,
  `docker-compose.oracle.yml` e `.github/workflows/`.
- `tests/`: testes do site e dos módulos compartilhados que ele usa.

## Produto e segurança

- A fonte de dados do mercado é a Steam Community Market pública. Nunca peça,
  leia ou armazene senha, cookie de sessão ou chave privada da Steam.
- A autenticação opcional do site usa Steam OpenID; não automatize ações na
  conta Steam.
- Visitar páginas públicas não inicia scans. O processo `worker` é o único
  responsável pela coleta de preços e respeita os limites da Steam.
- Consultas de rede em telas do visitante só acontecem por ação explícita,
  fora do carregamento automático da página.
- O site descreve dados observados; não promete retorno nem faz previsão.
- Mantenha validação, CSRF, limites de tentativas e codificação de saída nas
  rotas que recebem dados.
- Não adicione segredos, arquivos `.env`, chaves, bancos locais ou dados
  pessoais ao Git.

## Dados locais e persistência

- `data/` é armazenamento local e pode conter banco de contas, chave de sessão,
  caches e logs. **Nunca o apague em uma limpeza de código**.
- Use `skinvault._paths.atomic_write_text` / `atomic_write_bytes` para arquivos
  persistentes, não `Path.write_text` diretamente.
- Para registros JSON, use `load_json_record`; JSON malformado é colocado em
  quarentena em vez de ser tratado como registro vazio.
- Backups do site e do banco têm regras próprias em `public_site/db_backup.py`.
- Evite defaults de caminho capturados na definição de funções; resolva o
  caminho atual dentro da função para que testes possam isolá-lo.

## Steam e análise

- `steam_api.RATE_LIMIT_DELAY_S` é a fonte única dos intervalos. Consulte o
  valor no momento da chamada; não o copie para constantes ou defaults.
- Respeite o disjuntor de rate limit da Steam. Não faça requisições extras de
  diagnóstico nem retry imediato após 429.
- Uma listing page sem histórico pode ser throttle silencioso. Em varreduras,
  várias respostas vazias em sequência são suspeita de bloqueio, não prova de
  que cada item não tem histórico.
- Em `_find_query`, priorize nome exato, depois substring, e só então
  correspondência aproximada explicitamente permitida. Não retorne o primeiro
  resultado do laço.
- Datas da Steam sem ano referem-se ao ano corrente; normalize-as antes de
  gerar chaves persistentes.
- Percentuais internos usam escala de **0 a 100**. Não multiplique por 100
  uma segunda vez.
- Evidência histórica do modelo: momentum reverte à média em skins; a inversão
  não se aplica a caixas, cujo comportamento de longo prazo é diferente.
  O preço absoluto também foi um sinal forte. Não use resultados contaminados
  por lookahead nem transforme resultados passados em promessa de lucro.
- Registros de aposentadoria de caixas exigem fonte factual. Não invente data
  de saída do drop pool; consulte `retirements.py` e os dados persistidos.

### Evidência histórica do modelo

- O backtest de 2026-07-28 encontrou reversão à média em skins em todos os
  horizontes medidos. A inversão de momentum e multi-período melhorou o
  ranking de skins, mas piorou caixas a 365 dias; por isso a reversão não
  é aplicada a containers.
- O preço absoluto foi um sinal forte a 365 dias (IC −0,2635 no geral,
  −0,3036 em caixas e −0,0415 em skins). O ajuste de nível de preço fica
  restrito a containers porque os testes em skins não justificaram ativá-lo.
- No estudo de coortes, caixas recém-aposentadas tiveram retorno histórico
  maior que caixas ativas, mas a amostra era pequena e o efeito decaiu com o
  tempo. Sem data registrada, usar o status atual numa amostra histórica é
  lookahead; `case_status(..., as_of=...)` corrige apenas caixas com data.
- O contexto de topo deve evitar pontos horários isolados: uma compra atípica
  pode distorcer o máximo. Sinais descrevem essas medições passadas; não
  constituem previsão ou promessa de retorno.

## Interface pública

- Preserve o tema existente e o vocabulário em português para usuários
  iniciantes. Explique termos e estados em vez de exibir códigos internos.
- Mantenha navegação por teclado, foco visível, rótulos acessíveis e layouts
  utilizáveis em celular e desktop.
- O CSP não permite estilos inline. Prefira classes e regras em `style.css`.
- As telas que exibem preços carregam primeiro os valores já guardados; não
  faça fetch automático ao abrir a página.
- A conexão SSE é compartilhada pelo `app.js`; não abra outra `EventSource`
  por tela.
- Ações destrutivas pedem confirmação antes de enviar a requisição.

## Testes e comandos

O pytest isola `DATA_DIR` e bloqueia chamadas de rede. Testes que simulam rede
devem substituir o ponto de acesso por mock. A suíte é:

```bash
python -m pip install -r requirements-public-site.txt pytest
python -m pytest -q
```

Para validar a página no navegador, use o preview local e confira desktop,
celular, console e fluxo de teclado. O deploy automático atualiza `web` depois
que o workflow de testes passa. O `worker` não recarrega código sozinho: só
recebe o build novo com `[restart-worker]` na mensagem do commit. Ao subir ele
espera o próximo ciclo contado do último registrado, então reiniciar fora de um
scan não gera requisição à Steam; reiniciar no meio de um scan interrompe a coleta.
