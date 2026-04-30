# soporte_app_kill_processes.ps1 — Cierre de emergencia para EVE iT
# ==============================================================================

Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "Soporte App — cierre de emergencia EVE iT" -ForegroundColor Yellow
Write-Host "=========================================================" -ForegroundColor Cyan

$CurrentPid = $PID
Write-Host "PID del script de soporte: $CurrentPid"

# 1. Definir patrones de búsqueda
$Keywords = @(
    "eve-it",
    "eve_it",
    "market_command",
    "main_suite",
    "app_controller",
    "quick_order",
    "window_automation",
    "C:\Users\Azode\Downloads\eve-it-main\eve-it-main"
)

$WindowTitles = @(
    "EVE iT",
    "Market Command",
    "Quick Order Update"
)

# 2. Buscar procesos python/pythonw
Write-Host "`nBuscando procesos sospechosos..." -ForegroundColor Gray

$ProcessesToKill = @()

# Obtener procesos Python con CommandLine
try {
    $AllPython = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%.exe'"
    
    foreach ($p in $AllPython) {
        if ($p.ProcessId -eq $CurrentPid) { continue }
        
        $cmdLine = $p.CommandLine
        $match = $false
        foreach ($k in $Keywords) {
            if ($cmdLine -like "*$k*") {
                $match = $true
                $reason = "CommandLine contiene '$k'"
                break
            }
        }
        
        if ($match) {
            $ProcessesToKill += [PSCustomObject]@{
                Id      = $p.ProcessId
                Name    = $p.Name
                Reason  = $reason
                Cmd     = $cmdLine
            }
        }
    }
} catch {
    Write-Host "Error al inspeccionar CommandLine: $_" -ForegroundColor Red
}

# Buscar por títulos de ventana
foreach ($title in $WindowTitles) {
    $wins = Get-Process | Where-Object { $_.MainWindowTitle -like "*$title*" }
    foreach ($w in $wins) {
        if ($w.Id -eq $CurrentPid) { continue }
        # Evitar meter duplicados
        if ($ProcessesToKill.Id -notcontains $w.Id) {
            $ProcessesToKill += [PSCustomObject]@{
                Id      = $w.Id
                Name    = $w.ProcessName
                Reason  = "Título de ventana contiene '$title'"
                Cmd     = "N/A"
            }
        }
    }
}

# 3. Ejecutar limpieza
if ($ProcessesToKill.Count -eq 0) {
    Write-Host "No se encontraron procesos activos de EVE iT." -ForegroundColor Green
} else {
    foreach ($proc in $ProcessesToKill) {
        Write-Host "Matando PID $($proc.Id): $($proc.Name)" -ForegroundColor Yellow
        Write-Host "  Razón: $($proc.Reason)" -ForegroundColor Gray
        if ($proc.Cmd -ne "N/A") {
            Write-Host "  Cmd: $($proc.Cmd)" -ForegroundColor DarkGray
        }
        
        try {
            Stop-Process -Id $proc.Id -Force -ErrorAction Stop
            Write-Host "  [OK] Proceso detenido." -ForegroundColor Green
        } catch {
            Write-Host "  [ERROR] No se pudo matar el proceso: $_" -ForegroundColor Red
        }
    }
}

# 4. Liberar teclas modificadoras (Shift, Ctrl, Alt)
Write-Host "`nLiberando teclas modificadoras (Ctrl, Shift, Alt)..." -ForegroundColor Cyan

$Signature = @"
[DllImport("user32.dll")]
public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, uint dwExtraInfo);
"@
try {
    $User32 = Add-Type -MemberDefinition $Signature -Name "User32KeyHelper" -Namespace "Win32Functions" -PassThru
    
    $KEYEVENTF_KEYUP = 0x0002
    
    # Virtual Keys
    $VK_LSHIFT   = 0xA0
    $VK_RSHIFT   = 0xA1
    $VK_LCONTROL = 0xA2
    $VK_RCONTROL = 0xA3
    $VK_LMENU    = 0xA4 # Alt
    $VK_RMENU    = 0xA5 # Alt Gr
    
    $keys = @($VK_LSHIFT, $VK_RSHIFT, $VK_LCONTROL, $VK_RCONTROL, $VK_LMENU, $VK_RMENU)
    
    foreach ($k in $keys) {
        $User32::keybd_event([byte]$k, 0, $KEYEVENTF_KEYUP, 0)
    }
    Write-Host "[OK] Teclas liberadas." -ForegroundColor Green
} catch {
    Write-Host "[!] No se pudieron liberar las teclas automáticamente." -ForegroundColor Yellow
}

# 5. Verificación final
Write-Host "`nVerificando si quedan restos..." -ForegroundColor Gray
$Remaining = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%.exe'" | Where-Object {
    $p = $_
    $match = $false
    foreach ($k in $Keywords) { if ($p.CommandLine -like "*$k*") { $match = $true; break } }
    $match -and ($p.ProcessId -ne $CurrentPid)
}

if ($Remaining) {
    Write-Host "ATENCIÓN: Aún quedan procesos sospechosos:" -ForegroundColor Red
    $Remaining | ForEach-Object { Write-Host "  PID: $($_.ProcessId) - $($_.Name)" }
} else {
    Write-Host "Limpieza completada con éxito." -ForegroundColor Green
}

Write-Host "`n=========================================================" -ForegroundColor Cyan
Write-Host "Listo. Si el problema continúa, reinicia Windows antes" -ForegroundColor White
Write-Host "de volver a abrir EVE iT." -ForegroundColor White
Write-Host "=========================================================" -ForegroundColor Cyan
