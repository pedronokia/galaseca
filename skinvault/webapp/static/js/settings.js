// Tela de Configuracoes -- Fase 6. Cada controle salva sozinho (igual
// o SettingsScreen do Qt); backup/restore ficam numa secao a parte.
document.addEventListener("DOMContentLoaded", () => {
  const statusEl = document.getElementById("settings-status");
  const backupsBody = document.getElementById("backups-body");
  const backupsEmpty = document.getElementById("backups-empty");

  const elAutoBackup = document.getElementById("s-auto-backup");
  const elKeepBackups = document.getElementById("s-keep-backups");
  const elStartMin = document.getElementById("s-start-min");
  const elMinTray = document.getElementById("s-min-tray");
  const elOverlay = document.getElementById("s-overlay");
  const elCacheTtl = document.getElementById("s-cache-ttl");
  const elFeeRate = document.getElementById("s-fee-rate");

  let loading = true;

  function loadSettings() {
    fetch("/api/settings").then((r) => r.json()).then((s) => {
      loading = true;
      elAutoBackup.checked = !!s.auto_backup;
      elKeepBackups.value = s.keep_backups;
      elStartMin.checked = !!s.start_minimized;
      elMinTray.checked = !!s.minimize_to_tray_on_close;
      elOverlay.checked = !!s.overlay_mode;
      elCacheTtl.value = s.cache_ttl_hours;
      elFeeRate.value = s.fee_rate;
      loading = false;
    });
  }
  loadSettings();

  function save(key, value) {
    if (loading) return;
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [key]: value }),
    })
      .then((r) => r.json())
      .then((payload) => {
        if (payload.error) {
          statusEl.textContent = "Erro: " + payload.error;
          return;
        }
        statusEl.textContent = "Salvo.";
      });
  }

  elAutoBackup.addEventListener("change", () => save("auto_backup", elAutoBackup.checked));
  elKeepBackups.addEventListener("change", () => save("keep_backups", Number(elKeepBackups.value)));
  elStartMin.addEventListener("change", () => save("start_minimized", elStartMin.checked));
  elMinTray.addEventListener("change", () => save("minimize_to_tray_on_close", elMinTray.checked));
  elOverlay.addEventListener("change", () => save("overlay_mode", elOverlay.checked));
  elCacheTtl.addEventListener("change", () => save("cache_ttl_hours", Number(elCacheTtl.value)));
  elFeeRate.addEventListener("change", () => save("fee_rate", Number(elFeeRate.value)));

  document.getElementById("btn-reset").addEventListener("click", () => {
    window.skinvaultConfirm(
      "Restaurar as configurações desta tela para o padrão? "
      + "Seus dados (inventário, trades, watchlist) não são afetados.",
      { title: "Restaurar padrões", confirmLabel: "Restaurar" },
    ).then((ok) => {
      if (!ok) return;
      fetch("/api/settings/reset", { method: "POST" }).then(() => {
        statusEl.textContent = "Configurações restauradas para o padrão.";
        loadSettings();
      });
    });
  });

  const fmtSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  };
  const fmtDate = (ts) => new Date(ts * 1000).toLocaleString("pt-BR");

  function renderBackups(backups) {
    backupsBody.innerHTML = "";
    backupsEmpty.hidden = backups.length > 0;
    for (const b of backups) {
      const tr = document.createElement("tr");
      const tdName = document.createElement("td");
      tdName.textContent = fmtDate(b.mtime);
      tdName.title = b.name;
      const tdSize = document.createElement("td");
      tdSize.className = "num";
      tdSize.textContent = fmtSize(b.size);
      const tdActions = document.createElement("td");
      tdActions.className = "row-actions";
      const restoreBtn = document.createElement("button");
      restoreBtn.type = "button";
      restoreBtn.textContent = "Restaurar";
      restoreBtn.addEventListener("click", () => {
        window.skinvaultConfirm(
          `Restaurar o backup ${b.name}? Os dados atuais SERÃO SUBSTITUÍDOS.`,
          { title: "Restaurar backup", confirmLabel: "Restaurar", danger: true },
        ).then((ok) => {
          if (!ok) return;
          fetch("/api/settings/restore", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: b.path }),
          })
            .then((r) => r.json())
            .then((payload) => {
              if (payload.error) {
                statusEl.textContent = "Erro: " + payload.error;
                return;
              }
              statusEl.textContent = `Restaurados ${payload.count} arquivos.`;
            });
        });
      });
      tdActions.appendChild(restoreBtn);
      tr.append(tdName, tdSize, tdActions);
      backupsBody.appendChild(tr);
    }
  }

  function loadBackups() {
    fetch("/api/settings/backups").then((r) => r.json())
      .then((data) => renderBackups(data.backups || []));
  }
  loadBackups();

  document.getElementById("btn-backup-now").addEventListener("click", () => {
    statusEl.textContent = "Fazendo backup…";
    fetch("/api/settings/backup", { method: "POST" })
      .then((r) => r.json())
      .then((payload) => {
        if (payload.error) {
          statusEl.textContent = "Erro: " + payload.error;
          return;
        }
        statusEl.textContent = "Backup criado.";
        renderBackups(payload.backups || []);
      });
  });
});
