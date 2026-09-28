@echo off
REM Start the local Qdrant vector database that code intelligence (vc_search / vc_index / vc_graph ...) needs.
REM Native binary, bound to 127.0.0.1 only, storage in %USERPROFILE%\.vector\qdrant. Not started automatically
REM (owner rule: no extra localhost servers by default). Stop it with scripts\stop_code_intel.bat.
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vectorcode\code_intel\qdrant"
if not exist "%USERPROFILE%\.vector\qdrant" mkdir "%USERPROFILE%\.vector\qdrant"
set QDRANT__SERVICE__HOST=127.0.0.1
set QDRANT__SERVICE__HTTP_PORT=6333
set QDRANT__SERVICE__GRPC_PORT=6334
set QDRANT__STORAGE__STORAGE_PATH=%USERPROFILE%\.vector\qdrant\storage
set QDRANT__STORAGE__SNAPSHOTS_PATH=%USERPROFILE%\.vector\qdrant\snapshots
set QDRANT__TELEMETRY_DISABLED=true
start "VECTOR Qdrant" /min qdrant.exe
