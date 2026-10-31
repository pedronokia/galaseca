"""Worker do site público -- o ÚNICO processo que fala com a Steam.

Roda em loop, separado do servidor web: escaneia (respeitando o mesmo
`RATE_LIMIT_DELAY_S`/disjuntor de sempre), grava em `scan_store.json`/
`rankings.json`, dorme, repete. `server.py` só LÊ esses arquivos --
nenhum visitante do site dispara uma chamada à Steam (ver AGENTS.md e o
plano desta fase: 1000 visitantes não multiplicam o tráfego porque não
existe "scraping por visitante").

Uso: `python -m galaseca.public_site.worker` (num processo "worker"
separado do "web" no provedor de hospedagem -- Fase 3).
"""
from __future__ import annotations

import logging
import os
import re
import sys
import time

from galaseca import ranking, scan_engine, scan_store, scan_targets, signals
from galaseca.public_site import db_backup, scan_progress, worker_alert
from galaseca._ambiente import ambiente

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
_logger = logging.getLogger("galaseca.worker")

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
    return {cat: sorted(nomes, key=lambda n: -notas.get(n, 50))
            for cat, nomes in categories.items()}


def _on_progress(msg: str) -> None:
    _logger.info(msg)
    m = _PROGRESSO_RE.match(msg)
    if not m:
        return
    try:
        scan_progress.registrar(int(m.group(1)), int(m.group(2)), m.group(3))
    except Exception:
        pass


def run_once(categories: "dict[str, list[str]] | None" = None) -> list[dict]:
    """Um ciclo: escaneia, grava scan_store + ranking. Devolve os resultados."""
    if categories is None:
        categories = categorias_padrao()
    inicio = time.time()
    resultados = scan_engine.run_full_scan(
        _ordenar_por_nota_anterior(categories), on_progress=_on_progress)
    if resultados:
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
    # Termômetro da extração de miniatura (sem requisição extra): se o
    # número ficar igual ao total, o HTML da Steam mudou de formato.
    _logger.info("Itens sem miniatura: %d de %d",
                 sum(1 for r in resultados if not r.get("icon")),
                 len(resultados))
    duracao_min = (time.time() - inicio) / 60
    scan_store.registrar_ciclo(len(resultados), duracao_min)
    _logger.info("Ciclo concluído: %d itens em %.1fmin",
                len(resultados), duracao_min)
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


def main(intervalo_horas: "float | None" = None) -> None:
    """`intervalo_horas=None` lê `GALASECA_WORKER_INTERVAL_HORAS` (env),
    com fallback pro default -- pra ajustar a cadência em produção sem
    mudar código."""
    if intervalo_horas is None:
        intervalo_horas = float(
            ambiente("WORKER_INTERVAL_HORAS",
                           _INTERVALO_HORAS_DEFAULT))
    espera = espera_ate_proximo_ciclo(intervalo_horas)
    if espera > 0:
        _logger.info("Último ciclo terminou há pouco; próximo em %.1f min",
                     espera / 60)
        time.sleep(espera)
    while True:
        try:
            run_once()
        except Exception:
            _logger.error("ciclo do worker falhou", exc_info=True)
        time.sleep(intervalo_horas * 3600)


if __name__ == "__main__":
    main()
