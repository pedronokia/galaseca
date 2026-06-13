"""Diagnostico da renovacao automatica de sessao Steam.

RODE DEPOIS DE FAZER LOGIN no app (pra capturar o steamRefresh_steam novo).

O que faz:
  1. Carrega a sessao salva e mostra quais cookies de auth existem.
  2. Confirma se o refresh token (steamRefresh_steam) foi capturado.
  3. Forca uma renovacao real (refresh) contra a Steam e valida o
     novo token — sem esperar o token diario expirar.

Nao altera nada destrutivo: em sucesso, persiste a sessao renovada
(novos cookies), que e' exatamente o que o app faz no boot.
"""
import sys

from skinvault import steam_session as ss

s = ss.load()
if s is None:
    print("Nenhuma sessao salva. Faca login no app primeiro.")
    sys.exit(1)

print(f"steamid: {s.steamid}")
auth_keys = [k for k in ss._AUTH_COOKIES if s.cookies.get(k)]
print(f"cookies de auth presentes: {auth_keys}")

has_refresh = bool(s.cookies.get("steamRefresh_steam"))
print(f"refresh token (steamRefresh_steam) capturado: {has_refresh}")
if not has_refresh:
    print()
    print("=> Sessao foi capturada ANTES do fix (sem refresh token).")
    print("   Faca LOGOUT e LOGIN no app uma vez; rode este script de novo.")
    sys.exit(2)

print()
print("Token de acesso atual valido agora?", ss.validate(s))
print("Forcando renovacao via refresh token...")
secure_before = s.cookies.get("steamLoginSecure")
ok = ss.refresh(s)
print(f"  refresh() retornou: {ok}")
if ok:
    changed = s.cookies.get("steamLoginSecure") != secure_before
    print(f"  steamLoginSecure mudou: {changed}")
    print(f"  sessao renovada valida: {ss.validate(s)}")
    ss.persist(s)
    print("  sessao renovada persistida.")
    print()
    print("=> SUCESSO: a renovacao automatica funciona. A partir de agora")
    print("   o app renova sozinho no boot — sem relogin a cada 24h.")
else:
    print()
    print("=> refresh() falhou. Possiveis causas: refresh token expirado,")
    print("   ou o endpoint finalizelogin mudou. Me mostre a saida acima.")
