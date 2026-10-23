# Run directly from any PowerShell working directory. No install or network needed.
$treePreviousLocation = Get-Location
try {
    Set-Location -LiteralPath $PSScriptRoot
    python -m ascii_tree @args
    $treeExitCode = $LASTEXITCODE
} finally {
    Set-Location -LiteralPath $treePreviousLocation.Path
}
exit $treeExitCode
