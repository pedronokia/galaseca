"""Changelog público do site -- mantido manualmente, não gerado do git.

Cada entrada: {data, titulo, itens}. Mais recente primeiro. Existe
porque "Status" (scan_historico) mostra SE o site está saudável, mas não
O QUE mudou -- esta página é sobre produto, não operação.
"""
from __future__ import annotations

ENTRADAS = [
    {
        "data": "2026-11-14",
        "titulo": "Top 20 com preço mais fresco",
        "itens": [
            "Os 20 primeiros do ranking passam a ter o preço atualizado a cada 2 horas, entre as coletas completas de 6 em 6 horas. A página Status mostra quando foi a última atualização.",
        ],
    },
    {
        "data": "2026-11-13",
        "titulo": "Acessibilidade e acabamento (auditoria de interface)",
        "itens": [
            "Navegando com Tab, o item em foco não fica mais escondido atrás do cabeçalho ou da barra de baixo do celular.",
            "Leitores de tela passam a ouvir “Copiado” e quantos itens estão selecionados pra comparar.",
            "Barra do navegador no celular e tela de abertura do app instalado agora são escuras, como o site.",
            "Campos de formulário que só mudavam a borda ganharam o mesmo destaque laranja dos demais ao receber foco.",
            "Nomes de itens não são mais “traduzidos” pelo tradutor automático do navegador.",
            "Toque mais limpo no celular, sem o flash cinza nos botões.",
            "No celular, abas, seletores, paginação e links pequenos ganharam área de toque de ~40px sem mudar o desenho.",
            "Botões dão uma leve encolhida ao serem apertados; títulos e parágrafos não terminam mais com uma palavra sozinha na última linha.",
        ],
    },
    {
        "data": "2026-11-13",
        "titulo": "Novo nome e endereço: Lodout",
        "itens": [
            "O site agora se chama Lodout e passa a ficar em lodout.com.",
            "O endereço antigo (galaseca.com) continua funcionando e vai passar a levar direto pro novo.",
            "Favoritos, notas e comparações salvos no navegador ficam guardados por endereço: quem estava usando o endereço antigo começa do zero no novo.",
        ],
    },
    {
        "data": "2026-11-13",
        "titulo": "Ranking por período, novidades do jogo e preços mais confiáveis",
        "itens": [
            "Ranking: escolha comparar com a coleta anterior, 24 horas, 7 dias ou 30 dias. Setas, variação de nota e o resumo usam a mesma comparação.",
            "Ranking: lista de quem saiu do Top 20 no período escolhido.",
            "Página do item: presença no Top 20 dia a dia nos últimos 30 dias, com a melhor posição.",
            "Página do item: outras versões da mesma skin (desgaste, StatTrak™, Souvenir), com preço mediano e vendas em 24 horas.",
            "Nova página Novidades: mudanças nos arquivos do CS2 (drop semanal, Armory, caixas novas) e os anúncios oficiais da Valve.",
            "Caixa que sai do Armory passa a ser marcada como aposentada sozinha, com a data da mudança nos arquivos do jogo; caixas e cápsulas novas entram na lista acompanhada sem precisar de ajuste manual.",
            "Coleta de preços: quando a Steam pede uma pausa, a coleta espera e continua, em vez de pular itens. O item que estava sendo buscado na hora é tentado de novo no fim.",
            "Coleta de preços: item que mesmo assim fica sem preço continua no site com o preço anterior, com um aviso, em vez de sumir por 6 horas.",
            "Coleta de preços: se a Steam pausou muito numa coleta, a seguinte anda mais devagar e volta ao normal sozinha. Itens que ficam dias sem ninguém vendendo passam a ser tentados uma vez por dia.",
            "Coleta de preços: quando a Steam devolve páginas vazias em sequência (um bloqueio disfarçado), a coleta pausa e tenta de novo, em vez de calcular a nota sem o histórico.",
            "Coleta de preços: se o site for atualizado no meio de uma coleta, ela continua de onde parou. Se a Steam estiver fora do ar, a coleta para cedo e tenta de novo em 1 hora, em vez de 6.",
            "Status: barra de progresso da coleta em andamento e quantos itens vieram com preço novo na última.",
            "Início: item com o preço da coleta anterior ganha um selo no card e na lista, com a hora em que o preço foi coletado.",
        ],
    },
    {
        "data": "2026-11-12",
        "titulo": "Tema escuro",
        "itens": [
            "Site inteiro no tema escuro: fundo quase preto #0a0a0a, texto #e5e5e5, texto secundário #9ca3af e bordas #3f3f46.",
            "Tiles elevadas em #171717 e caixas de destaque no preto #0a0a0a, mantendo o laranja da casa nos botões e foco.",
        ],
    },
    {
        "data": "2026-11-12",
        "titulo": "Cores do site alinhadas ao OpenCode",
        "itens": [
            "Cores do site alinhadas com a identidade do OpenCode (opencode.ai/brand):",
            "Fundo branco puro #ffffff, texto #1F1F1F (Ink), texto secundário #626262 (Ink 70%), bordas #D2D2D2 (Ink 20%).",
            "Rodapé, cartas e caixas de destaque no mesmo esquema monocromático.",
        ],
    },
    {
        "data": "2026-11-12",
        "titulo": "Polimentos de consistência visual nas páginas de erro, admin e conta",
        "itens": [
            "Páginas 404, 429 e 500 ganharam cabeçalho de página (título + descrição), card com CTA e o rodapé padrão com grupos de links.",
            "Painel admin e login de admin ganharam descrição no cabeçalho, card ao redor do formulário e rodapé padrão.",
            "Botões de ação nessas páginas usam o mesmo estilo pílula laranja do resto do site (classe .botao-acao).",
            "Minha watchlist envolve os formulários 'Adicionar item' e 'Alerta no Discord' em cards, igual às demais páginas de conta.",
            "Minha histórico envolve gráfico e tabela em card dentro de .resumo-cards, igual ao resto das páginas de conta.",
            "Excluir conta ganha descrição no cabeçalho e envolve o aviso em .resumo-cards.",
            "Sobre ganha descrição mais completa no cabeçalho da página.",
            "Formulários 'Adicionar item' (Minha conta) e 'Registrar trade' (Meus trades) envolvidos em .resumo-cards > .card, igual aos demais formulários de conta (watchlist, admin login).",
        ],
    },
    {
        "data": "2026-11-12",
        "titulo": "Correções de acessibilidade (teclado e leitor de tela)",
        "itens": [
            "Removido tabindex='-1' dos termos do glossário: todos agora são alcançáveis com a tecla Tab (violação de WCAG 2.1.1 corrigida).",
            "Páginas 404, 429 e 500 passam a ter um único <h1> (o título da página); o logo deixa de ser h1 nessas páginas.",
            "Nav de conta (Trades/Watchlist/Histórico) ganha aria-label='Minhas páginas'.",
            "Erros de validação do login de admin e do webhook da watchlist ganham role='alert' e aria-invalid='true' no campo.",
        ],
    },
    {
        "data": "2026-11-12",
        "titulo": "Otimização de desempenho / LCP",
        "itens": [
            "Preload da fonte Inter (woff2) no <head>: começa a baixar em paralelo com o HTML, em vez de só depois que o CSS é parseado (o @font-face dispara o fetch da fonte).",
            "Preconnect para community.steamstatic.com: abre conexão TCP/TLS antecipadamente pra ícones de item que caem no CDN da Steam quando o cache local não tem o hash.",
        ],
    },
    {
        "data": "2026-11-11",
        "titulo": "O site inteiro no estilo da Apple",
        "itens": [
            "Páginas 404, 429 e 500 ganharam cabeçalho de página (título + descrição), card com CTA e o rodapé padrão com grupos de links.",
            "Painel admin e login de admin ganharam descrição no cabeçalho, card ao redor do formulário e rodapé padrão.",
            "Botões de ação nessas páginas usam o mesmo estilo pílula laranja do resto do site (classe .botao-acao).",
            "Minha watchlist envolve os formulários 'Adicionar item' e 'Alerta no Discord' em cards, igual às demais páginas de conta.",
        ],
    },
    {
        "data": "2026-11-11",
        "titulo": "O site inteiro no estilo da Apple",
        "itens": [
            "O texto do site passou a usar os mesmos tamanhos, pesos e "
            "espaçamentos do apple.com: corpo de 17px, títulos de 32px a "
            "64px e o mesmo desenho de letra",
            "Os botões viraram pílula azul (clicar e comprar, como na "
            "loja da Apple) e os links de texto ficaram azuis sem caixa "
            "em volta",
            "Os cards e as caixas de destaque ganharam o raio de 18px, fio "
            "de 1px e nenhuma sombra -- o bloco do topo da home virou um "
            "painel quase preto com o número da nota em branco",
            "O rodapé virou um bloco cinza de ponta a ponta, com texto de "
            "12px, como o rodapé da Apple",
            "As abas de categoria, o seletor Vitrine/Lista, os campos de "
            "filtro e a barra do celular foram todos refeitos no mesmo "
            "vocabulário visual",
        ],
    },
    {
        "data": "2026-11-11",
        "titulo": "A marca virou aspas e o nome ganhou forma de nome",
        "itens": [
            "O cabeçalho agora mostra só as aspas, sem o disco atrás: é o "
            "desenho que acende ao passar o mouse, como o símbolo da barra "
            "da Apple",
            "O nome do site nos títulos das páginas passou a ser "
            "“Galaseca”, com G maiúsculo -- o resto do texto continua "
            "“galaseca”",
            "O ícone da aba do navegador e o do celular (instalar na tela "
            "de início) passaram a ser as mesmas aspas da barra, sem a "
            "vela vermelha da marca antiga",
        ],
    },
    {
        "data": "2026-11-11",
        "titulo": "Categorias só com nome e contagem",
        "itens": [
            "Os desenhos que ficavam na frente do nome de cada categoria "
            "saíram: a barra de filtros ficou só com o nome e a quantidade "
            "de itens, mais limpa e sem repetir a mesma figura em várias "
            "abas",
            "O seletor Vitrine/Lista também ficou só com as palavras, sem "
            "os desenhos de grade e de lista",
        ],
    },
    {
        "data": "2026-11-11",
        "titulo": "Cabeçalho no ritmo da barra da Apple",
        "itens": [
            "A barra do topo ficou mais fina: agora tem a altura da "
            "barra de navegação do site da Apple e deixa o conteúdo "
            "começar mais cedo",
            "A barra ganhou fundo escuro, como a barra da Apple no modo "
            "escuro: o menu fica em texto claro e o conteúdo branco "
            "começa logo abaixo dela",
            "Os links do menu ficam juntos, com o mesmo respiro entre "
            "eles, em vez de se espalharem até as pontas da barra",
            "A marca virou um símbolo redondo com aspas, no lugar do "
            "nome escrito: a barra fica leve e sobra espaço para o menu",
            "O botão de entrar virou um item discreto da barra, sem a "
            "pílula azul; o símbolo da Steam continua ao lado do texto",
            "No celular, a barra de baixo acompanha a do topo no mesmo "
            "fundo escuro, para as duas parecerem o mesmo sistema",
            "A página aberta não ganha mais um risco embaixo do nome no "
            "menu -- quem usa leitor de tela continua sabendo em qual "
            "página está",
            "A frase de apoio ao lado do botão de entrar saiu da barra; "
            "o que o login desbloqueia continua explicado no FAQ",
        ],
    },
    {
        "data": "2026-11-10",
        "titulo": "Nova identidade visual: tema claro e tranquilo",
        "itens": [
            "A paleta de cores foi refeita: fundo branco e cinza-claro, "
            "com azul só em links e botões, no lugar da mistura de azul, "
            "verde-limão e várias cores de raridade competindo entre si",
            "Cantos recortados, brilho ao redor da raridade, listra "
            "diagonal e a inclinação 3D dos cards ao passar o mouse "
            "saíram -- a hierarquia agora vem do tamanho, peso e espaço, "
            "não de efeitos",
            "Home, item, ranking, comparar, status e as páginas de "
            "leitura (método, FAQ, glossário) passaram a falar a mesma "
            "língua visual",
            "O rodapé se organizou em três grupos de links e o botão de "
            "entrar com a Steam ganhou o ícone da marca",
        ],
    },
    {
        "data": "2026-11-08",
        "titulo": "Gráficos com tooltip e portfólio com mais destaque",
        "itens": [
            "Ícones de itens em resolução mais nítida nas telas de alta "
            "densidade, em vez da mesma imagem pequena esticada",
            "Comparar: o ícone do item voltou ao mesmo tamanho grande "
            "usado no resto do site",
            "Minha conta e Meus trades: o card de lucro ganhou o mesmo "
            "destaque visual que a Nota já tinha na página do item",
            "Meu histórico: o gráfico de valor da carteira agora mostra "
            "data e valor exato ao passar o mouse, com a cor indicando "
            "se subiu ou caiu",
            "A home voltou a mostrar quantos itens novos entraram no "
            "Top 20 desde a última comparação",
            "Status: o gráfico de visitas por dia também ganhou essa "
            "informação ao passar o mouse",
        ],
    },
    {
        "data": "2026-10-29",
        "titulo": "Novo nome e endereço: GalaSeca",
        "itens": [
            "O site agora se chama GalaSeca e fica em galaseca.com",
            "Facas e luvas entraram na coleta (o nome usado na Steam não "
            "batia e esses itens voltavam vazios)",
            "O Ranking passou a mostrar as 20 maiores notas do scan inteiro",
            "No celular, cada item vira um cartão com os rótulos de cada dado",
            "\"Só favoritos\" avisa quando o favorito está em outra página "
            "da lista, com link pra ele",
        ],
    },
    {
        "data": "2026-10-29",
        "titulo": "Tabela mais clara e ações organizadas",
        "itens": [
            "Texto e espaçamento das linhas ficaram mais confortáveis de ler",
            "A tabela destaca um motivo por item; os demais fatores continuam "
            "disponíveis ao expandir a explicação",
            "Favoritar e comparar ficam visíveis; as outras ações foram "
            "agrupadas em um menu",
            "O espaço da miniatura fica reservado mesmo quando a imagem "
            "ainda não está disponível",
            "A etiqueta de caixa descontinuada ficou mais discreta",
        ],
    },
    {
        "data": "2026-10-29",
        "titulo": "Miniaturas das skins e nomes mais fáceis de ler",
        "itens": [
            "A tabela recupera as imagens das skins quando o scan as recebe "
            "da página pública da Steam",
            "O nome do item não fica mais espremido entre os controles; "
            "ações e links ganharam uma linha própria",
        ],
    },
    {
        "data": "2026-10-29",
        "titulo": "Mais clareza na página de recomendações",
        "itens": [
            "O estado dos dados deixa mais claro quando a coleta está atrasada",
            "Filtros ativos podem ser removidos separadamente sem perder os demais",
            "Preços ficam alinhados e a tendência também aparece por escrito",
            "A nota e o risco ganharam explicações visíveis",
            "O cabeçalho da tabela acompanha a rolagem em telas grandes",
        ],
    },
    {
        "data": "2026-10-29",
        "titulo": "Filtros mais compactos no celular",
        "itens": [
            "Nota mínima e preço máximo agora aparecem lado a lado "
            "em telas pequenas",
            "Uma indicação mostra que a tabela pode ser deslizada "
            "para ver as outras colunas",
            "A paginação informa quantos itens estão visíveis e o total "
            "encontrado nos filtros",
        ],
    },
    {
        "data": "2026-10-29",
        "titulo": "Formulários e documentação mais claros",
        "itens": [
            "Formulários de carteira, trades e watchlist agora avisam "
            "quando os dados informados são inválidos",
            "Regras já salvas continuam preservadas quando uma nova "
            "regra é inválida",
            "Login Steam agora confirma que o retorno pertence à sessão "
            "que iniciou o acesso",
            "Documentação da API atualizada com o limite de consultas "
            "e um exemplo fiel à resposta atual",
            "Tabela mais larga em telas grandes; a coluna 'Por quê' "
            "resume os dois primeiros fatores e permite abrir o restante",
        ],
    },
    {
        "data": "2026-10-27",
        "titulo": "Tabela mais leve e CTA de login explicado",
        "itens": [
            "Página principal mostra 10 itens por vez em vez de 20 -- "
            "rola menos pra achar o botão \"Ver mais\"",
            "A nota pessoal por item some atrás de um ícone até você "
            "clicar nele, em vez de ocupar espaço em toda linha",
            "O selo de \"mudou desde sua última visita\" agora tem uma "
            "forma diferente do ▲/▼ de preço, pra não confundir os dois",
            "\"Entrar com Steam\" ganhou uma frase explicando o que você "
            "ganha ao logar (portfólio, trades e watchlist)",
            "Mais acessível pra quem usa leitor de tela nos formulários "
            "de conta, trades, watchlist e login do painel interno",
        ],
    },
    {
        "data": "2026-10-26",
        "titulo": "Página de item, login, PWA, e uma correção de verdade no scan",
        "itens": [
            "Página de detalhe por item, comparador lado a lado, "
            "favoritos, buscas salvas, exportar CSV",
            "Site instalável (PWA) e login do painel interno trocado "
            "por senha de verdade, sem token na URL",
            "Corrigido um bug real que travava o scan inteiro num item "
            "sem preço médio disponível",
            "FAQ, exportar seus próprios dados em JSON, e mais de 50 "
            "ajustes de acessibilidade, SEO e segurança",
        ],
    },
    {
        "data": "2026-10-25",
        "titulo": "Polimentos e infraestrutura técnica",
        "itens": [
            "Copiar nome do item com um clique, agrupar por categoria, "
            "atalho de teclado \"/\" pra buscar",
            "Expandir qualquer linha pra ver o cálculo completo da nota, "
            "não só os 3 motivos principais",
            "Compressão gzip, cache nos arquivos estáticos, "
            "robots.txt/sitemap.xml, página 404 própria",
            "Esta página de changelog e a documentação da API pública",
        ],
    },
    {
        "data": "2026-10-24",
        "titulo": "Redesign visual e correção de um bug real de rate limit",
        "itens": [
            "Visual novo (paleta azul escuro, inspirada na Steam)",
            "Busca por nome, ordenar clicando na coluna, filtros "
            "(categoria/nota/preço), paginação",
            "Ícone de cada item, nome linkado pro Steam Market, "
            "selo pra caixa descontinuada",
            "Página /status com histórico de scans (inclusive os que "
            "falharam) e contador de visitas",
            "Corrigido bug onde o scan martelava a Steam por ~26min "
            "mesmo já bloqueado, sem desistir cedo",
        ],
    },
    {
        "data": "2026-10-23",
        "titulo": "Site público no ar",
        "itens": [
            "Deploy na Oracle Cloud (Always Free), com Docker e HTTPS "
            "automático via Caddy",
            "Login com Steam, portfólio/trades/watchlist/histórico "
            "pessoais, proteção contra abuso",
            "Página de privacidade e exclusão de conta",
        ],
    },
]
