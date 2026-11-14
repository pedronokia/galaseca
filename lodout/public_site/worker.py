"""Worker do site público -- o ÚNICO processo que fala com a Steam.

Roda em loop, separado do servidor web: escaneia (respeitando o mesmo
`RATE_LIMIT_DELAY_S`/disjuntor de sempre), grava em `scan_store.json`/
`rankings.json`, dorme, repete. `server.py` só LÊ esses arquivos --
nenhum visitante do site dispara uma chamada à Steam (ver AGENTS.md e o
plano desta fase: 1000 visitantes não multiplicam o tráfego porque não
existe "scraping por visitante").

Uso: `python -m lodout.public_site.worker` (num processo "worker"
separado do "web" no provedor de hospedagem -- Fase 3).
"""
from __future__ import annotations

import json
import logging
import os
import re
import signal
import sys
import time
from pathlib import Path

from lodout import (
    gamedata, ranking, scan_engine, scan_store, scan_targets, signals,
    steam_news,
)
from lodout import _paths
from lodout._paths import atomic_write_text, load_json_record
from lodout.public_site import db_backup, scan_progress, worker_alert
from lodout._ambiente import ambiente

_PROGRESSO_RE = re.compile(r"^\[(\d+)/(\d+)\] (.+)$")

# `logging` em vez de `print(..., file=sys.stderr)` -- achado ao vivo em
# 2026-10-26: o print do except em main() só mostrava `str(e)`
# ("'<=' not supported..."), sem o traceback. Descobrir ONDE a exceção
# nascia exigiu reproduzir o bug manualmente numa sessão à parte --
# `exc_info=True` grava o traceback completo de graça, sem precisar
# disso da próxima vez.
logging.basicConfig(
    level=logging.INFO, stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(message)s")
_logger = logging.getLogger("lodout.worker")

_INTERVALO_HORAS_DEFAULT = 6.0
_TOP_RANKING = 20

# Adesivos somam ~9700 itens entre as 4 categorias (torneio/autógrafo/
# comunidade/evento) -- um ciclo completo incluindo eles levaria ~22h por
# forca do RATE_LIMIT_DELAY_S (2 req/item x 4s x ~9900 itens). Sem eles, o
# ciclo cobre ~170 itens (armas/caixas/cápsulas) em ~23min, o que cabe num
# intervalo de poucas horas. Adesivos podem entrar numa varredura própria,
# mais espaçada, se um dia fizer sentido pro produto.
_CATEGORIAS_PESADAS = (
    "Adesivos de torneio", "Adesivos de autógrafo",
    "Adesivos da comunidade", "Adesivos de evento",
)


def categorias_padrao() -> "dict[str, list[str]]":
    """`scan_targets.SCAN_BY_CATEGORY` sem as categorias de adesivo."""
    return {k: v for k, v in scan_targets.SCAN_BY_CATEGORY.items()
            if k not in _CATEGORIAS_PESADAS}


# Ritmo adaptativo: multiplica a pausa entre itens quando o ciclo
# anterior levou 429, e volta devagar pro normal em ciclos limpos.
_RITMO_MAX = 2.0
_RITMO_SOBE = 1.25
_RITMO_DESCE = 0.9


def _ritmo_do_ciclo(historico: "list[dict]") -> float:
    """Ritmo deste ciclo a partir do último registrado. Sem dado de
    pausas (ciclo antigo), 1.0."""
    if not historico:
        return 1.0
    ultimo = historico[-1]
    pausas = ultimo.get("pausas_429")
    anterior = float(ultimo.get("ritmo") or 1.0)
    if not isinstance(pausas, int):
        return 1.0
    if pausas > 0:
        return round(min(_RITMO_MAX, anterior * _RITMO_SOBE), 2)
    return round(max(1.0, anterior * _RITMO_DESCE), 2)


# Item que fica `_SEM_ANUNCIO_CICLOS` ciclos seguidos sem preço, SEM ter
# levado bloqueio, provavelmente não tem anúncio no Market: passa a ser
# tentado só uma vez a cada `_SEM_ANUNCIO_ESPERA_H` horas. Volta ao
# normal na primeira vez que trouxer preço.
_SEM_ANUNCIO_CICLOS = 3
_SEM_ANUNCIO_ESPERA_H = 24.0
# Acima desta fração dos alvos sem preço no mesmo ciclo, é falha geral.
_SEM_ANUNCIO_FRACAO_MAX = 0.2


def _caminho_sem_anuncio() -> Path:
    return Path(_paths.DATA_DIR) / "scan_sem_anuncio.json"


def _carregar_sem_anuncio() -> "dict[str, dict]":
    dados = load_json_record(_caminho_sem_anuncio(), {})
    return dados if isinstance(dados, dict) else {}


def _tirar_itens_em_espera(categories: "dict[str, list[str]]",
                           registro: "dict[str, dict]",
                           agora: float) -> "tuple[dict[str, list[str]], list[str]]":
    """Categorias sem os itens em espera (sem anúncio, tentados há menos
    de `_SEM_ANUNCIO_ESPERA_H`). Devolve também os nomes que ficaram de
    fora."""
    limite = agora - _SEM_ANUNCIO_ESPERA_H * 3600
    fora: "list[str]" = []

    def _em_espera(nome: str) -> bool:
        r = registro.get(nome) or {}
        return (int(r.get("seguidas") or 0) >= _SEM_ANUNCIO_CICLOS
                and float(r.get("ultima") or 0) > limite)

    novas = {}
    for cat, nomes in categories.items():
        ficam = []
        for n in nomes:
            if _em_espera(n):
                fora.append(n)
            else:
                ficam.append(n)
        novas[cat] = ficam
    return novas, fora


def _atualizar_sem_anuncio(registro: "dict[str, dict]",
                           vieram: "set[str]", sem_preco: "list[str]",
                           agora: float) -> "dict[str, dict]":
    """Conta falhas seguidas sem bloqueio; zera quem trouxe preço. Item
    que falhou por 429 não mexe na contagem (não diz nada do item)."""
    novo = {k: v for k, v in registro.items() if k not in vieram}
    for nome in sem_preco:
        anterior = novo.get(nome) or {}
        novo[nome] = {"seguidas": int(anterior.get("seguidas") or 0) + 1,
                      "ultima": agora}
    return novo


def _ordenar_por_nota_anterior(
        categories: "dict[str, list[str]]") -> "dict[str, list[str]]":
    """Reordena os nomes de cada categoria pela nota do scan anterior
    (desc). Se o ciclo for interrompido pelo bloqueio da Steam (comum,
    ver as regras de rate limit e cooldown da Steam em AGENTS.md, os itens
    já conhecidos como mais relevantes
    ficam com dado fresco antes dos nunca vistos -- tratados como nota
    50 (nem primeiro, nem último), não penalizados por serem novos."""
    scan = scan_store.load_last_scan()
    notas = {r["name"]: r.get("score", 50) for r in scan["results"]} if scan else {}
    # Quem ficou sem preço novo no ciclo anterior (está no site com dado
    # velho) vai na frente -- é o dado mais atrasado do site.
    atrasados = {r["name"] for r in scan["results"]
                 if r.get("mantido_do_ciclo_anterior")} if scan else set()
    return {cat: sorted(nomes, key=lambda n: (n not in atrasados,
                                              -notas.get(n, 50)))
            for cat, nomes in categories.items()}


# Até quanto tempo um item que falhou no ciclo atual continua no site
# com o dado do ciclo anterior (marcado como tal). Depois disso some --
# preço de dois dias atrás já não é "o preço" de nada.
_MANTER_ANTERIOR_MAX_H = 48.0


def _manter_do_ciclo_anterior(novos: "list[dict]", anterior: "dict | None",
                              alvos: "set[str]",
                              agora: "float | None" = None) -> "list[dict]":
    """Resultados do scan anterior pros itens-alvo que NÃO voltaram neste
    ciclo, marcados com `mantido_do_ciclo_anterior`. Sem isto, um item
    que falhou uma vez sumia do site por 6h e aparecia como "saiu do Top
    20" no ranking sem ter mudado nada."""
    if not anterior:
        return []
    agora = time.time() if agora is None else agora
    vieram = {r["name"] for r in novos}
    limite = agora - _MANTER_ANTERIOR_MAX_H * 3600
    mantidos = []
    for r in anterior.get("results") or []:
        nome = r.get("name")
        if nome in vieram or nome not in alvos:
            continue
        coletado = r.get("coletado_em") or anterior.get("ts") or 0
        if coletado < limite:
            continue
        mantidos.append({**r, "coletado_em": coletado,
                         "mantido_do_ciclo_anterior": True})
    return mantidos


# Eventos do gamedata que trazem um container novo pro jogo.
_EVENTOS_CONTAINER_NOVO = ("new_container", "xpshop_added")


def _com_containers_novos(
        categories: "dict[str, list[str]]") -> "dict[str, list[str]]":
    """Inclui no scan as caixas/cápsulas que `gamedata` viu aparecer nos
    arquivos do jogo, sem esperar alguém editar `scan_targets.py`. Só
    entra nome traduzido (o de mercado) e com sufixo reconhecível --
    nome interno cru (`crate_...`) não existe no Market."""
    try:
        eventos = gamedata.load_events_log()
    except Exception:
        _logger.warning("log de eventos do jogo ilegível", exc_info=True)
        return categories
    ja = {n for nomes in categories.values() for n in nomes}
    extra: "dict[str, list[str]]" = {}
    for ev in eventos:
        if not isinstance(ev, dict) or ev.get("type") not in _EVENTOS_CONTAINER_NOVO:
            continue
        interno = str(ev.get("internal") or "")
        nome = str(ev.get("name") or "")
        if not interno.startswith("crate_") or not nome or nome == interno:
            continue
        if nome.endswith(" Case"):
            cat = "Caixas"
        elif nome.endswith(" Capsule"):
            cat = "Cápsulas"
        else:
            continue
        if cat not in categories or nome in ja:
            continue
        ja.add(nome)
        extra.setdefault(cat, []).append(nome)
    if not extra:
        return categories
    _logger.info("Containers novos incluídos no scan: %s",
                 ", ".join(n for ns in extra.values() for n in ns))
    return {cat: list(nomes) + extra.get(cat, [])
            for cat, nomes in categories.items()}


# Checkpoint do ciclo em andamento (2026-11-13): antes, um reinício no
# meio do scan perdia o ciclo inteiro (o resultado só era gravado no
# fim) -- por isso o deploy do worker exigia escolher a hora. Agora o
# worker grava o que já coletou a cada `_CHECKPOINT_A_CADA` itens e, ao
# subir, retoma de onde parou se o checkpoint for recente.
_CHECKPOINT_A_CADA = 5
_CHECKPOINT_MAX_H = 3.0

# Pedido de parada (SIGTERM do `docker stop`/deploy): o laço do scan
# termina entre dois itens, com o checkpoint gravado.
_parar = False
_escaneando = False


def _ao_receber_sigterm(signum, frame) -> None:
    global _parar
    _parar = True
    _logger.info("Pedido de parada recebido; encerrando entre dois itens")
    if not _escaneando:
        raise SystemExit(0)


def _caminho_checkpoint() -> Path:
    return Path(_paths.DATA_DIR) / "scan_parcial.json"


def _carregar_checkpoint(agora: float) -> "dict | None":
    """{"inicio", "results"} do ciclo interrompido, ou None se não há,
    está ilegível ou é velho demais pra ainda ser "este" ciclo."""
    try:
        dados = json.loads(_caminho_checkpoint().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(dados, dict):
        return None
    inicio = dados.get("inicio")
    results = dados.get("results")
    if (not isinstance(inicio, (int, float)) or not isinstance(results, list)
            or agora - inicio > _CHECKPOINT_MAX_H * 3600):
        return None
    results = [r for r in results
               if isinstance(r, dict) and "name" in r and "score" in r]
    return {"inicio": float(inicio), "results": results}


def _gravar_checkpoint(inicio: float, results: "list[dict]") -> None:
    try:
        atomic_write_text(_caminho_checkpoint(), json.dumps(
            {"inicio": inicio, "results": results}, ensure_ascii=False,
            default=str))
    except OSError:
        _logger.warning("não gravou o checkpoint do scan", exc_info=True)


def _apagar_checkpoint() -> None:
    try:
        _caminho_checkpoint().unlink()
    except FileNotFoundError:
        pass
    except OSError:
        _logger.warning("não apagou o checkpoint do scan", exc_info=True)


def _on_progress(msg: str) -> None:
    _logger.info(msg)
    m = _PROGRESSO_RE.match(msg)
    if not m:
        return
    try:
        scan_progress.registrar(int(m.group(1)), int(m.group(2)), m.group(3))
    except Exception:
        pass


def _verificar_arquivos_do_jogo() -> None:
    """Uma consulta por ciclo ao espelho dos arquivos do CS2 no GitHub
    (`gamedata.check_for_updates`) -- não fala com a Steam, então não
    entra na conta do rate limit. Se o items_game.txt mudou, grava os
    eventos e a data de saída do Armory em `retirements`, que a nota lê.
    Roda ANTES do scan pra caixa recém-aposentada já sair com o status
    novo neste mesmo ciclo. Falha aqui só vira aviso no log."""
    try:
        resultado = gamedata.check_for_updates()
    except Exception:
        _logger.warning("checagem dos arquivos do jogo falhou", exc_info=True)
        return
    if resultado.get("error"):
        _logger.warning("checagem dos arquivos do jogo: erro de %s",
                        resultado["error"])
    elif resultado.get("changed"):
        commit = resultado.get("commit") or {}
        _logger.info("Arquivos do jogo mudaram (%s, %s): %d evento(s)",
                     (commit.get("sha") or "")[:7], commit.get("date"),
                     len(resultado.get("events") or []))


def run_once(categories: "dict[str, list[str]] | None" = None) -> list[dict]:
    """Um ciclo: checa os arquivos do jogo, escaneia, grava scan_store +
    ranking. Devolve os resultados."""
    global _escaneando
    if categories is None:
        categories = categorias_padrao()
    _verificar_arquivos_do_jogo()
    categories = _com_containers_novos(categories)
    agora = time.time()
    sem_anuncio = _carregar_sem_anuncio()
    categories, em_espera = _tirar_itens_em_espera(
        categories, sem_anuncio, agora)
    if em_espera:
        _logger.info("Em espera (sem anúncio, 1 tentativa/dia): %s",
                     ", ".join(em_espera))
    alvos = {n for nomes in categories.values() for n in nomes}
    anterior = scan_store.load_last_scan()
    historico_ciclos = scan_store.load_historico_ciclos()
    ritmo = _ritmo_do_ciclo(historico_ciclos)
    fonte, fator_preco = _fonte_do_ciclo(historico_ciclos)
    if fonte == "pagina":
        _logger.info("Modo 1 requisição por item (fator de preço %s)",
                     fator_preco)
    if ritmo > 1.0:
        _logger.info("Ciclo anterior levou 429: ritmo %.2fx", ritmo)
    inicio = time.time()
    checkpoint = _carregar_checkpoint(inicio)
    ja_coletados: "list[dict]" = list(checkpoint["results"]) if checkpoint else []
    inicio_ciclo = checkpoint["inicio"] if checkpoint else inicio
    if ja_coletados:
        _logger.info("Retomando ciclo interrompido: %d itens já coletados",
                     len(ja_coletados))
    acumulados = list(ja_coletados)

    def _on_resultado(r: dict) -> None:
        acumulados.append(r)
        if len(acumulados) % _CHECKPOINT_A_CADA == 0:
            _gravar_checkpoint(inicio_ciclo, acumulados)

    falhas: "list[str]" = []
    relatorio: dict = {}
    # Quem tinha histórico no ciclo anterior: página sem histórico agora,
    # em sequência, é suspeita de throttle silencioso (scan_engine).
    tinham_historico = {
        r["name"] for r in (anterior or {}).get("results") or []
        if ((r.get("data_quality") or {}).get("n") or 0) > 0}
    _escaneando = True
    try:
        novos = scan_engine.run_full_scan(
            _ordenar_por_nota_anterior(categories), on_progress=_on_progress,
            falhas=falhas, ritmo=ritmo, relatorio=relatorio,
            tinham_historico=tinham_historico,
            pular={r["name"] for r in ja_coletados},
            on_resultado=_on_resultado,
            prioridade=_prioridade_do_scan_anterior() or None,
            fonte=fonte, fator_preco=fator_preco,
            cancelled=lambda: _parar)
    finally:
        _escaneando = False
    if _parar:
        # Parada pedida no meio: guarda o que veio e deixa o ciclo pra
        # ser retomado no próximo start, sem gravar scan/ranking parcial.
        _gravar_checkpoint(inicio_ciclo, acumulados)
        _logger.info("Scan interrompido com %d itens no checkpoint",
                     len(acumulados))
        return []
    novos = ja_coletados + novos
    if relatorio.get("throttle_silencioso"):
        _logger.warning("Throttle silencioso detectado %d vez(es)",
                        relatorio["throttle_silencioso"])
    sem_preco = relatorio.get("sem_preco") or []
    # Falha em massa (rede da VM fora, Steam mudou a página) não é "item
    # sem anúncio": só conta quando o ciclo trouxe preço pra maioria.
    # Sem esta trava, 3 ciclos sem rede punham o site inteiro em espera.
    if sem_preco and (not novos
                      or len(sem_preco) > _SEM_ANUNCIO_FRACAO_MAX * len(alvos)):
        _logger.warning("%d itens sem preço sem bloqueio: falha geral, "
                        "contagem de sem-anúncio não mexida", len(sem_preco))
        sem_preco = []
    try:
        atomic_write_text(_caminho_sem_anuncio(), json.dumps(
            _atualizar_sem_anuncio(
                sem_anuncio, {r["name"] for r in novos}, sem_preco,
                time.time()),
            ensure_ascii=False))
    except OSError:
        _logger.warning("não gravou scan_sem_anuncio.json", exc_info=True)
    if relatorio.get("comparacao_fontes"):
        _logger.info("Listing page vs priceoverview: %s",
                     relatorio["comparacao_fontes"])
    # Ciclo sem NENHUM item novo (Steam bloqueando tudo) não regrava
    # nada: o scan anterior continua valendo inteiro, como antes.
    mantidos = (_manter_do_ciclo_anterior(novos, anterior, alvos)
                if novos else [])
    if falhas:
        _logger.info("Sem resultado neste ciclo (%d): %s", len(falhas),
                     ", ".join(falhas[:30]))
    resultados = novos + mantidos
    if novos:
        scan_store.save_last_scan("Todas as categorias", resultados)
        # Ordena ANTES de cortar: `resultados` vem na ordem do scan
        # (categoria por categoria), então `[:20]` direto pegava os 20
        # primeiros escaneados, não as 20 maiores notas. Desempate pela
        # nota bruta (antes do clamp em 100) também aqui -- sem isso,
        # o corte em 20 podia excluir por acaso um item com nota bruta
        # maior que um dos 20 escolhidos, só por ordem de chegada.
        ranking.save_snapshot(sorted(
            resultados, key=lambda r: (
                -r.get("score", 0), -signals.raw_score(r.get("breakdown"))),
        )[:_TOP_RANKING])
    _apagar_checkpoint()
    # Termômetro da extração de miniatura (sem requisição extra): se o
    # número ficar igual ao total, o HTML da Steam mudou de formato.
    _logger.info("Itens sem miniatura: %d de %d",
                 sum(1 for r in novos if not r.get("icon")),
                 len(novos))
    duracao_min = (time.time() - inicio) / 60
    scan_store.registrar_ciclo(
        len(novos), duracao_min, alvos=len(alvos),
        mantidos=len(mantidos), falhas=falhas,
        extras={
            "ritmo": ritmo,
            "pausas_429": relatorio.get("pausas_429", 0),
            "throttle_silencioso": relatorio.get("throttle_silencioso", 0),
            "abortado": bool(relatorio.get("abortado")),
            "fonte": fonte,
            "em_espera": em_espera,
            "comparacao_fontes": relatorio.get("comparacao_fontes"),
            "comparacao_tendencia": relatorio.get("comparacao_tendencia"),
        })
    _logger.info("Ciclo concluído: %d itens novos (+%d mantidos do ciclo "
                 "anterior) em %.1fmin", len(novos), len(mantidos),
                 duracao_min)
    # Anúncios oficiais do CS2 -- DEPOIS do scan pra nunca atrasar a
    # coleta de preço; 1 requisição a cada ~6h no máximo e família própria
    # no disjuntor (ver steam_news.py).
    try:
        _logger.info("Notícias oficiais: %s", steam_news.atualizar_noticias())
    except Exception:
        _logger.warning("busca de notícias falhou", exc_info=True)
    # Backup do banco de contas/portfolio pessoal -- auto-limitado a 1x/
    # ~20h por `fazer_backup_se_necessario`, então chamar a cada ciclo
    # (mesmo de 6 em 6h) não produz backup demais.
    try:
        db_backup.fazer_backup_se_necessario()
    except Exception:
        _logger.warning("backup do banco falhou", exc_info=True)
    # Backup dos JSON globais do dashboard (scan_store/ranking) -- achado
    # da 2a rodada (2026-10-25): só o SQLite tinha backup até aqui.
    try:
        db_backup.fazer_backup_json_se_necessario()
    except Exception:
        _logger.warning("backup dos JSON falhou", exc_info=True)
    # Alerta Discord do dono se o worker ficar horas sem trazer item
    # nenhum (ver worker_alert.py) -- sem webhook configurado, é no-op.
    try:
        worker_alert.verificar_e_alertar(scan_store.load_historico_ciclos())
    except Exception:
        _logger.warning("alerta de atraso falhou", exc_info=True)
    # Alerta Discord do dono se o ciclo voltou com cobertura baixa ou
    # viu throttle silencioso -- mesmo webhook, dedup próprio de 24 h.
    try:
        worker_alert.verificar_qualidade_e_alertar(
            scan_store.load_historico_ciclos())
    except Exception:
        _logger.warning("alerta de qualidade do scan falhou", exc_info=True)
    # Alerta Discord do dono se o disco da VM estiver ficando cheio --
    # mesmo webhook/env var do alerta acima, checagem independente.
    try:
        worker_alert.verificar_disco_e_alertar()
    except Exception:
        _logger.warning("alerta de disco falhou", exc_info=True)
    return resultados


def espera_ate_proximo_ciclo(intervalo_horas: float,
                             now: "float | None" = None) -> float:
    """Segundos até o próximo ciclo, contados do fim do último ciclo
    registrado (`scan_store.registrar_ciclo`). 0 sem histórico ou quando o
    ciclo já está atrasado.

    Existe para reiniciar o worker não custar um scan: antes, `main()`
    escaneava assim que subia, então todo deploy de código do worker
    dependia de decidir à mão quando pagar ~28 min de requisições à Steam
    fora da cadência (2026-10-29)."""
    historico = scan_store.load_historico_ciclos()
    if not historico:
        return 0.0
    ultimo = max(float(c["ts"]) for c in historico)
    agora = time.time() if now is None else now
    return max(0.0, ultimo + intervalo_horas * 3600 - agora)


# Ciclo que não trouxe NENHUM item (Steam em manutenção, rede da VM fora,
# bloqueio longo): em vez de deixar o site 6 h a mais com dado velho, tenta
# de novo em 1 h, depois 2 h, 4 h... nunca mais rápido que isso e nunca
# depois do intervalo normal. Cada tentativa custa poucas requisições
# (o ciclo aborta cedo se a Steam segue fora -- ver scan_engine).
_RETENTATIVA_VAZIO_H = (1.0, 2.0, 4.0)


def _espera_apos_ciclo(intervalo_horas: float, vazios_seguidos: int) -> float:
    """Segundos até o próximo ciclo depois de um ciclo terminar."""
    if vazios_seguidos <= 0:
        return intervalo_horas * 3600
    idx = min(vazios_seguidos, len(_RETENTATIVA_VAZIO_H)) - 1
    horas = min(intervalo_horas, _RETENTATIVA_VAZIO_H[idx])
    _logger.info("Ciclo sem nenhum item (%d seguido(s)): nova tentativa "
                 "em %.1f h", vazios_seguidos, horas)
    return horas * 3600


# Modo de 1 requisição por item (scan_engine `fonte="pagina"`): só com
# LODOUT_SCAN_FONTE=pagina E uma medição recente do modo sombra que
# mostre a listing page batendo com o priceoverview. A razão medida vira
# o fator de conversão do preço do book.
_FONTE_PAGINA_MIN_ITENS = 50
_FONTE_PAGINA_MIN_CONCORDA = 95.0
_FONTE_PAGINA_MIN_MEDIANA = 90.0
_FONTE_PAGINA_MIN_VOLUME = 85.0


def _fonte_do_ciclo(historico: "list[dict]") -> "tuple[str, float | None]":
    """("pagina", fator) se ligado e validado; senão ("ambas", None).

    Usa o ciclo mais recente que TEM comparação (no modo página quase
    não há priceoverview pra comparar). Quando o histórico de ciclos não
    tiver mais nenhuma comparação boa, um ciclo volta ao modo completo e
    mede de novo -- o modo se revalida sozinho."""
    if str(ambiente("SCAN_FONTE", "ambas")).strip().lower() != "pagina":
        return "ambas", None
    for c in reversed(historico):
        comp = c.get("comparacao_fontes")
        if not isinstance(comp, dict):
            continue
        n = comp.get("itens_preco") or 0
        if n < _FONTE_PAGINA_MIN_ITENS:
            continue
        razao = comp.get("razao_preco")
        concorda = comp.get("preco_concorda_pct") or 0
        # Mediana e volume entram na nota: precisam ter sido medidos e
        # concordar também (medição antiga, sem mediana, não libera).
        mediana_ok = (comp.get("mediana_concorda_pct") or 0) >= _FONTE_PAGINA_MIN_MEDIANA
        volume_ok = (comp.get("volume_concorda_pct") or 0) >= _FONTE_PAGINA_MIN_VOLUME
        if isinstance(razao, (int, float)) and razao > 0 \
                and concorda >= _FONTE_PAGINA_MIN_CONCORDA \
                and mediana_ok and volume_ok:
            return "pagina", float(razao)
        return "ambas", None  # medição mais recente reprovou
    return "ambas", None


def _prioridade_do_scan_anterior() -> "dict[str, float]":
    """Chave de ordem global do próximo ciclo (menor primeiro): quem está
    no site com dado do ciclo anterior vem antes de tudo; depois, maior
    nota primeiro. Nome nunca visto fica no meio (nota 50)."""
    scan = scan_store.load_last_scan()
    if not scan:
        return {}
    out = {}
    for r in scan["results"]:
        nota = float(r.get("score") or 0)
        out[r["name"]] = (-1000.0 if r.get("mantido_do_ciclo_anterior")
                          else 0.0) - nota
    return out


# ── Rodada rápida do Top 20 (2026-11-13) ─────────────────────────────
# Entre duas coletas completas, a cada `LODOUT_TOP_RAPIDO_HORAS` (padrão
# 2 h; 0 desliga) o worker atualiza só os 20 itens do ranking atual: são
# os mais vistos do site, e assim o preço deles nunca passa de ~2 h.
# ~40 requisições por rodada (+~22% no total com ciclo de 6 h), no mesmo
# ritmo/disjuntor da coleta completa. O ranking em si só é recalculado na
# coleta completa -- 20 itens frescos contra 165 de horas atrás não
# formam um Top 20 justo.
_TOP_RAPIDO_HORAS_DEFAULT = 2.0
# Não começa rodada rápida se a coleta completa estiver a menos disto.
_TOP_RAPIDO_MARGEM_S = 30 * 60


def rodada_top() -> "list[dict]":
    """Atualiza os itens do Top 20 atual no scan_store, sem mexer no
    ranking, no histórico de coletas nem no checkpoint. Devolve os
    resultados novos ([] se não havia o que fazer ou foi interrompida)."""
    global _escaneando
    snaps = ranking.load_snapshots()
    scan = scan_store.load_last_scan()
    if not snaps or not scan:
        return []
    nomes = [it["name"] for it in snaps[-1].get("items", [])]
    por_nome = {r["name"]: r for r in scan["results"]}
    nomes = [n for n in nomes if n in por_nome]
    if not nomes:
        return []
    categorias: "dict[str, list[str]]" = {}
    for n in nomes:
        categorias.setdefault(por_nome[n].get("category") or "Top 20",
                              []).append(n)
    tinham_historico = {
        n for n in nomes
        if ((por_nome[n].get("data_quality") or {}).get("n") or 0) > 0}
    inicio = time.time()
    _logger.info("Rodada rápida do Top 20: %d itens", len(nomes))
    _escaneando = True
    try:
        novos = scan_engine.run_full_scan(
            categorias, on_progress=_logger.info,
            ritmo=_ritmo_do_ciclo(scan_store.load_historico_ciclos()),
            relatorio={}, tinham_historico=tinham_historico,
            cancelled=lambda: _parar)
    finally:
        _escaneando = False
    if _parar or not novos:
        return []
    # Relê: entre o início e agora nada mais escreve o scan_store (o
    # worker é um processo só), mas reler deixa claro que é merge.
    scan = scan_store.load_last_scan() or scan
    frescos = {r["name"]: r for r in novos}
    resultados = [frescos.get(r["name"], r) for r in scan["results"]]
    scan_store.save_last_scan(scan["category"], resultados, now=scan["ts"])
    duracao = (time.time() - inicio) / 60
    scan_store.registrar_rodada_top(len(novos), len(nomes), duracao)
    _logger.info("Rodada rápida concluída: %d de %d em %.1fmin",
                 len(novos), len(nomes), duracao)
    return novos


def _dormir_com_rodadas_top(espera_s: float, permitido: bool = True) -> None:
    """Dorme `espera_s` até a próxima coleta completa, fazendo rodadas
    rápidas do Top 20 no caminho. Sem rodada quando desligado, quando a
    última coleta não trouxe nada (Steam fora) ou quando a completa está
    perto demais."""
    try:
        horas = float(ambiente("TOP_RAPIDO_HORAS", _TOP_RAPIDO_HORAS_DEFAULT))
    except (TypeError, ValueError):
        horas = _TOP_RAPIDO_HORAS_DEFAULT
    if not permitido or horas <= 0:
        time.sleep(espera_s)
        return
    passo = horas * 3600
    fim = time.time() + espera_s
    while True:
        falta = fim - time.time()
        if falta <= passo + _TOP_RAPIDO_MARGEM_S:
            time.sleep(max(0.0, falta))
            return
        time.sleep(passo)
        if _parar:
            return
        try:
            rodada_top()
        except Exception:
            _logger.error("rodada rápida do Top 20 falhou", exc_info=True)
        if _parar:
            return


def main(intervalo_horas: "float | None" = None) -> None:
    """`intervalo_horas=None` lê `LODOUT_WORKER_INTERVAL_HORAS` (env),
    com fallback pro default -- pra ajustar a cadência em produção sem
    mudar código."""
    if intervalo_horas is None:
        intervalo_horas = float(
            ambiente("WORKER_INTERVAL_HORAS",
                           _INTERVALO_HORAS_DEFAULT))
    signal.signal(signal.SIGTERM, _ao_receber_sigterm)
    espera = espera_ate_proximo_ciclo(intervalo_horas)
    if espera > 0 and _carregar_checkpoint(time.time()):
        _logger.info("Há um ciclo interrompido recente: retomando agora")
        espera = 0
    if espera > 0:
        _logger.info("Último ciclo terminou há pouco; próximo em %.1f min",
                     espera / 60)
        _dormir_com_rodadas_top(espera)
    vazios_seguidos = 0
    while True:
        try:
            trouxe = bool(run_once())
        except Exception:
            _logger.error("ciclo do worker falhou", exc_info=True)
            trouxe = False
        if _parar:
            return
        vazios_seguidos = 0 if trouxe else vazios_seguidos + 1
        _dormir_com_rodadas_top(
            _espera_apos_ciclo(intervalo_horas, vazios_seguidos),
            permitido=trouxe)


if __name__ == "__main__":
    main()
