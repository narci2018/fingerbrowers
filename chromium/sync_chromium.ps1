# sync_chromium.ps1 - Automated shallow sync for Chromium kernel
$env:Path = "C:\Tools2\fingerbrowers\depot_tools;$env:Path"
$env:HTTP_PROXY = "http://127.0.0.1:10808"
$env:HTTPS_PROXY = "http://127.0.0.1:10808"
$env:DEPOT_TOOLS_WIN_TOOLCHAIN = "0"
$env:GYP_MSVS_VERSION = "2022"

Write-Host "=========================================="
Write-Host " [PhantomBrowser] Chromium Source Code Sync"
Write-Host " Proxy: http://127.0.0.1:10808"
Write-Host " Mode: Shallow Checkout (--no-history --shallow)"
Write-Host "=========================================="

& "C:\Tools2\fingerbrowers\depot_tools\gclient.bat" sync --no-history --shallow --nohooks -j 4
