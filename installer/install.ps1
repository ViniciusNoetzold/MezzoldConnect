$ErrorActionPreference = "Stop"

$appName = "Mezzold Connect"
$sourceExe = Join-Path $PSScriptRoot "Mezzold Connect.exe"
$targetDir = Join-Path $env:LOCALAPPDATA $appName
$targetExe = Join-Path $targetDir "Mezzold Connect.exe"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$appName.lnk"
$startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) $appName
$startMenuShortcut = Join-Path $startMenuDir "$appName.lnk"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null
Copy-Item -LiteralPath $sourceExe -Destination $targetExe -Force

$uninstallScript = @"
`$ErrorActionPreference = "Stop"
`$appName = "Mezzold Connect"
`$targetDir = Join-Path `$env:LOCALAPPDATA `$appName
`$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "`$appName.lnk"
`$startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) `$appName
`$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
Get-Process "Mezzold Connect" -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-ItemProperty -Path `$runKey -Name `$appName -ErrorAction SilentlyContinue
Remove-Item -LiteralPath `$desktopShortcut -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath `$startMenuDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath `$targetDir -Recurse -Force -ErrorAction SilentlyContinue
"@
Set-Content -LiteralPath (Join-Path $targetDir "uninstall.ps1") -Value $uninstallScript -Encoding UTF8

$shell = New-Object -ComObject WScript.Shell

foreach ($shortcutPath in @($desktopShortcut, $startMenuShortcut)) {
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $targetExe
    $shortcut.WorkingDirectory = $targetDir
    $shortcut.IconLocation = $targetExe
    $shortcut.Save()
}

$uninstallShortcut = $shell.CreateShortcut((Join-Path $startMenuDir "Desinstalar Mezzold Connect.lnk"))
$uninstallShortcut.TargetPath = "powershell.exe"
$uninstallShortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$targetDir\uninstall.ps1`""
$uninstallShortcut.WorkingDirectory = $targetDir
$uninstallShortcut.Save()

New-ItemProperty `
    -Path $runKey `
    -Name $appName `
    -Value "`"$targetExe`" --background" `
    -PropertyType String `
    -Force | Out-Null

Start-Process -FilePath $targetExe
