@echo off
cd /d "%~dp0"

:: Clean stale proxy file so we can detect when the tunnel is actually ready
if exist proxies_local.txt del proxies_local.txt

echo Starting proxy tunnels...
start "ProxyTunnels" /MIN python proxy_tunnel.py

:: Wait for proxies_local.txt to appear (max 15 seconds)
set /a WAITED=0
:wait_loop
if exist proxies_local.txt goto tunnel_ready
if %WAITED% GEQ 15 (
    echo ERROR: Proxy tunnel did not produce proxies_local.txt after 15s.
    echo        Check the proxy tunnel window for errors.
    goto cleanup
)
timeout /t 1 /nobreak >nul
set /a WAITED+=1
goto wait_loop

:tunnel_ready
:: Verify the file has content
for %%A in (proxies_local.txt) do if %%~zA==0 (
    echo ERROR: proxies_local.txt is empty — no tunnels started.
    goto cleanup
)
echo Proxy tunnels ready (%WAITED%s).

echo.
echo Resetting incomplete matches...
python reset_incomplete.py
if errorlevel 1 (
    echo WARNING: reset_incomplete.py failed, continuing anyway...
)

echo.
echo Starting historical ingest...
hltv-ingest --concurrent-tabs 1 --proxy-file proxies_local.txt
echo.
echo Historical ingest finished.

:cleanup
echo Shutting down proxy tunnels...
taskkill /F /FI "WINDOWTITLE eq ProxyTunnels" >nul 2>&1
:: Also kill any lingering python proxy_tunnel processes
wmic process where "commandline like '%%proxy_tunnel%%'" call terminate >nul 2>&1
echo Done.
pause
