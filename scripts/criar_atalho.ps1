<#
.SYNOPSIS
    Cria um atalho do SkinVault na Area de Trabalho.

.DESCRIPTION
    Sem instalador, "abrir o SkinVault" hoje significa rodar
    `python -m skinvault --web` (ou --ui) num terminal. Este script cria
    um atalho .lnk de verdade -- clique duplo, sem terminal, sem decorar
    comando -- usando so' COM nativo do Windows (WScript.Shell), sem
    dependencia nova.

.PARAMETER Modo
    "web" (default, UI Flask + pywebview) ou "ui" (UI Qt classica).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\criar_atalho.ps1
    powershell -ExecutionPolicy Bypass -File scripts\criar_atalho.ps1 -Modo ui
#>
param(
    [ValidateSet("web", "ui")]
    [string]$Modo = "web"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

# pythonw (sem console) -- mesmo binario que `python -m skinvault --web`
# relanca sozinho no Windows (ver AGENTS.md). Prefere o do PATH; cai pro
# irmao de `python` se so' esse existir.
$pythonwCmd = Get-Command pythonw -ErrorAction SilentlyContinue
if ($pythonwCmd) {
    $pythonw = $pythonwCmd.Source
} else {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        Write-Error "Nao encontrei 'python' nem 'pythonw' no PATH. Ative o ambiente do projeto antes de rodar este script."
        exit 1
    }
    $pythonw = Join-Path (Split-Path $pythonCmd.Source) "pythonw.exe"
}
if (-not (Test-Path $pythonw)) {
    Write-Error "pythonw.exe nao existe em '$pythonw'."
    exit 1
}

$icon = Join-Path $projectRoot "skinvault\assets\icon.ico"
if (-not (Test-Path $icon)) {
    Write-Error "Icone nao encontrado em '$icon'."
    exit 1
}

$flag = if ($Modo -eq "web") { "--web" } else { "--ui" }
$rotulo = if ($Modo -eq "web") { "SkinVault" } else { "SkinVault (classico)" }

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "$rotulo.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "-m skinvault $flag"
$shortcut.WorkingDirectory = $projectRoot
$shortcut.IconLocation = $icon
$shortcut.Description = "Abre o $rotulo"
$shortcut.Save()

Write-Host "Atalho criado: $shortcutPath"
