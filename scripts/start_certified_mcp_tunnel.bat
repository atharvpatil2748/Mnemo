@echo off
rem Transport-only bridge. Production identity and credentials are server-owned.
set "MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE=D:\Mnemo\phase8.5.11-models\huggingface\hub"
"%~dp0..\.venv\Scripts\python.exe" -m mnemo_server.mcp.cli certified-tunnel-stdio
exit /b %errorlevel%
