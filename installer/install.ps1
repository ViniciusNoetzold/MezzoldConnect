$ErrorActionPreference = "Stop"

$appName = "Mezzold Connect"
$sourceExe = Join-Path $PSScriptRoot "Mezzold Connect.exe"
$targetDir = Join-Path $env:LOCALAPPDATA $appName
$targetExe = Join-Path $targetDir "Mezzold Connect.exe"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$appName.lnk"
$startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) $appName
$startMenuShortcut = Join-Path $startMenuDir "$appName.lnk"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

function Replace-ExecutableSafely {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Target
    )

    $tempTarget = "$Target.new"
    $backupTarget = "$Target.bak"
    Remove-Item -LiteralPath $tempTarget -Force -ErrorAction SilentlyContinue

    Copy-Item -LiteralPath $Source -Destination $tempTarget -Force
    $sourceHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash
    $tempHash = (Get-FileHash -LiteralPath $tempTarget -Algorithm SHA256).Hash
    if ($sourceHash -ne $tempHash) {
        Remove-Item -LiteralPath $tempTarget -Force -ErrorAction SilentlyContinue
        throw "A copia do executavel falhou na verificacao de integridade."
    }

    if (!(Test-Path -LiteralPath $Target)) {
        Move-Item -LiteralPath $tempTarget -Destination $Target -Force
        return
    }

    try {
        Remove-Item -LiteralPath $backupTarget -Force -ErrorAction SilentlyContinue
        Move-Item -LiteralPath $Target -Destination $backupTarget -Force
        try {
            Move-Item -LiteralPath $tempTarget -Destination $Target -Force
        } catch {
            if ((Test-Path -LiteralPath $backupTarget) -and !(Test-Path -LiteralPath $Target)) {
                Move-Item -LiteralPath $backupTarget -Destination $Target -Force
            }
            throw
        }
    } catch {
        Remove-Item -LiteralPath $tempTarget -Force -ErrorAction SilentlyContinue
        throw "Nao foi possivel substituir o aplicativo. Feche o Mezzold Connect e o envio em segundo plano, depois execute o instalador novamente."
    }
}

New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null
Replace-ExecutableSafely -Source $sourceExe -Target $targetExe

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
