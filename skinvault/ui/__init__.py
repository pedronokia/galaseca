"""Pacote de UI do SkinVault (F11+).

Estrutura:
  theme.py           paleta + tipografia + helpers de stylesheet
  components.py      Sidebar, Breadcrumb, Footer, Card, StatCard, SegmentedControl
  widgets.py         MiniSparkline, DepthChart, MonthBarChart, ValueChart (migrados)
  screen_router.py   QStackedWidget que faz gating por sessao
  login_gate.py      tela inicial bloqueante sem login
  account_screen.py  Tela 1 - Minha Conta + Inventario
  history_screen.py  Tela 2 - Meu Historico
  scanner_screen.py  Tela 3 - Scanner Premium (locked overlay)
  profile_fetcher.py avatar + nome do perfil Steam publico
  toast.py           ToastManager (singleton global de toasts) + ToastWidget
"""
