# Preserve later user edits and remove only the managed Codex Flow installation.
[CmdletBinding()]
param([switch]$DryRun, [string]$PythonExe, [string]$CodexHome, [string]$SkillsDir)
$ErrorActionPreference = 'Stop'
$options = @{}
if ($DryRun) { $options.DryRun = $true }
if ($PythonExe) { $options.PythonExe = $PythonExe }
if ($CodexHome) { $options.CodexHome = $CodexHome }
if ($SkillsDir) { $options.SkillsDir = $SkillsDir }
& (Join-Path $PSScriptRoot 'Install.ps1') -Uninstall @options
exit $LASTEXITCODE
