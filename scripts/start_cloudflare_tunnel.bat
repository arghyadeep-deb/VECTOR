@echo off
REM VECTOR — Cloudflare Quick Tunnel launcher.
REM Gives VECTOR a real public HTTPS front door (Cloudflare edge terminates TLS;
REM VECTOR itself stays plain HTTP behind it — see VECTOR_TLS_TERMINATED=1 in .env
REM and core/runtime/tls.py). This is a QUICK tunnel: the hostname is randomly
REM assigned by Cloudflare on every start and is NOT stable across restarts.
REM A stable custom hostname (e.g. vector.yourdomain.com) requires a named
REM tunnel bound to a real domain in the owner's Cloudflare account — that
REM account currently has zero zones, so this is the best available option
REM until a domain is added.
REM
REM The assigned URL for the current run is always in the log below, and also
REM queryable live via cloudflared's local metrics endpoint:
REM   curl http://127.0.0.1:20241/quicktunnel

setlocal
set "REPO=C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
set "LOG=%REPO%\data\logs\cloudflared_tunnel.log"

if not exist "%REPO%\data\logs" mkdir "%REPO%\data\logs"

REM Don't stack duplicate tunnels — clear out any previous instance first.
taskkill /F /IM cloudflared.exe >nul 2>&1

echo ==== VECTOR Cloudflare tunnel start %DATE% %TIME% ==== >> "%LOG%"
start "VECTOR-Tunnel" /min cmd /c "cloudflared tunnel --url http://localhost:8000 --metrics 127.0.0.1:20241 >> "%LOG%" 2>&1"

endlocal
