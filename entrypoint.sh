#!/bin/sh
# Entrypoint do site público -- roda como root só o tempo necessário
# pra corrigir a posse de /data, depois cede o processo principal
# (gunicorn do "web" ou "python -m ...worker" do "worker") pro usuário
# sem privilégio `galaseca` (achado de auditoria, skill docker-
# security-guide, 2026-11-05: a imagem rodava como root inteira,
# nenhum USER no Dockerfile).
#
# O chown é necessário (não cosmético): o volume nomeado `skinvault_
# data` já existe em produção com dado real (banco de contas, scan,
# chave de sessão), criado quando o container ainda rodava como root
# -- sem corrigir a posse aqui, o primeiro deploy com usuário não-root
# perderia acesso de escrita ao próprio banco. `chown -R` é idempotente
# (só ajusta dono, nunca apaga/recria nada), então rodar em todo start
# é seguro mesmo depois que a posse já estiver certa.
#
# `exec su ... -c 'exec "$0" "$@"' -- "$@"` (em vez de `su -c "$*"`)
# preserva os argumentos como array, não como string recolada -- sem
# isso, o CMD padrão do "web" (`/bin/sh -c "gunicorn --bind ... ${PORT:-8000} ..."`,
# que vem embrulhado pelo Docker quando o CMD é shell-form) ou o
# `command:` do "worker" (`python -m galaseca.public_site.worker`)
# podiam quebrar com argumento que tenha espaço.
set -e
chown -R galaseca:galaseca /data
exec su -s /bin/sh galaseca -c 'exec "$0" "$@"' -- "$@"
