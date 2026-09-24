@echo off
rem Restricted, server-owned observation transport. No production identity override.
set "MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE=D:\Mnemo\phase8.5.11-models\huggingface\hub"
"%~dp0..\.venv\Scripts\python.exe" -m mnemo_server.mcp.cli observe-tunnel-stdio
exit /b %errorlevel%
