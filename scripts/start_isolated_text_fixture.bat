@echo off
rem Temporary owner-authorized fixture. Not the certified production launcher.
cd /d "%~dp0.." || exit /b 2
if not exist ".venv\Scripts\python.exe" exit /b 2
if not defined MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE exit /b 2
if not defined MNEMO_ORDERED_TEXT_FIXTURE_ROOT exit /b 2
".venv\Scripts\python.exe" scripts\serve_ordered_text_fixture.py stdio --root "%MNEMO_ORDERED_TEXT_FIXTURE_ROOT%"
