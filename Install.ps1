# Codex Flow 1.2.0 -- offline launcher for Windows PowerShell 5.1 / PowerShell 7.
# Does not install Python, change the machine execution policy, or call a model.
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$SkillOnly,
    [switch]$NativeAgents,
    [switch]$ReplaceEdited,
    [switch]$Uninstall,
    [switch]$Doctor,
    [string]$Repo,
    [string]$PythonExe,
    [string]$CodexHome,
    [string]$SkillsDir
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
try {
    if ($Uninstall -and $Doctor) { throw 'Choose either -Uninstall or -Doctor.' }
    if (($Uninstall -or $Doctor) -and ($SkillOnly -or $NativeAgents -or $ReplaceEdited)) {
        throw '-SkillOnly, -NativeAgents and -ReplaceEdited are install-only options.'
    }
    if ($Doctor -and $DryRun) { throw '-Doctor is already read-only; omit -DryRun.' }
    if ($Repo -and -not $Doctor) { throw '-Repo belongs to -Doctor, not global installation.' }
    $scriptFile = Join-Path $PSScriptRoot 'payload\codex-flow\scripts\flowctl.py'
    if (-not (Test-Path -LiteralPath $scriptFile -PathType Leaf)) {
        throw 'Archive layout is incomplete. Extract the entire ZIP, not only Install.ps1.'
    }
    Write-Host '[1/3] Finding Python 3.11 or newer...'
    $candidates = @()
    if ($PythonExe) {
        $candidates += [pscustomobject]@{ Exe = $PythonExe; Prefix = @() }
    } else {
        foreach ($name in @('py', 'python', 'python3')) {
            $found = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($null -ne $found) {
                $prefix = @()
                if ($name -eq 'py') { $prefix = @('-3') }
                $candidates += [pscustomobject]@{ Exe = $found.Source; Prefix = $prefix }
            }
        }
    }
    $selected = $null
    foreach ($candidate in $candidates) {
        $probeArgs = @($candidate.Prefix) + @('-c', 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 11)')
        try {
            & $candidate.Exe @probeArgs *> $null
            if ($LASTEXITCODE -eq 0) { $selected = $candidate; break }
        } catch { }
    }
    if ($null -eq $selected) {
        throw 'Python 3.11+ was not found. Supply -PythonExe "C:\path\python.exe", or use the manual skill-only installation in README.ru.md. No runtime was downloaded.'
    }
    $action = 'install'
    if ($Uninstall) { $action = 'uninstall' }
    if ($Doctor) { $action = 'doctor' }
    $callArgs = @($selected.Prefix) + @($scriptFile, $action)
    if ($DryRun) { $callArgs += '--dry-run' }
    if ($SkillOnly) { $callArgs += '--skill-only' }
    if ($NativeAgents) { $callArgs += '--native-agents' }
    if ($ReplaceEdited) { $callArgs += '--replace-edited' }
    if ($CodexHome) { $callArgs += @('--codex-home', $CodexHome) }
    if ($SkillsDir) { $callArgs += @('--skills-dir', $SkillsDir) }
    if ($Repo) { $callArgs += @('--repo', $Repo) }
    Write-Host ('[2/3] Running local ' + $action + ' preflight and operation...')
    & $selected.Exe @callArgs
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw ('Operation failed with exit code ' + $code + '. Read the error above; do not overwrite files manually.') }
    Write-Host '[3/3] Local operation finished.'
    if ($action -eq 'install' -and -not $DryRun) {
        Write-Host 'Restart Codex and open a new thread. Select Codex Flow and enter: init'
        Write-Host 'CLI/IDE invocation: $codex-flow init'
    }
    exit 0
} catch {
    [Console]::Error.WriteLine('ERROR: ' + $_.Exception.Message)
    exit 2
}
