# soporte_app_kill_processes.ps1
# ==============================================================================
Write-Host 'Soporte App - Cierre de emergencia' -ForegroundColor Yellow

$CurrentPid = $PID
$Keywords = @('eve-it', 'eve_it', 'market_command', 'quick_order', 'window_automation')

Write-Host 'Buscando procesos...'
$Procs = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%.exe'"
foreach ($p in $Procs) {
    if ($p.ProcessId -eq $CurrentPid) { continue }
    $Match = $false
    foreach ($k in $Keywords) { if ($p.CommandLine -like "*$k*") { $Match = $true; break } }
    if ($Match) {
        Write-Host "Matando PID $($p.ProcessId)"
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

Write-Host 'Liberando teclas...'
$sig = @'
using System;
using System.Runtime.InteropServices;
public static class User32 {
    [DllImport("user32.dll")]
    public static extern void keybd_event(byte b, byte s, uint f, UIntPtr e);
}
'@
try {
    Add-Type -TypeDefinition $sig -ErrorAction SilentlyContinue
    $keys = @(0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5)
    foreach ($k in $keys) { [User32]::keybd_event([byte]$k, 0, 2, [UIntPtr]::Zero) }
    Write-Host 'Teclas liberadas.'
} catch {
    Write-Host 'Error liberando teclas.'
}

Write-Host 'Listo.'
