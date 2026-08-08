@echo off
setlocal enabledelayedexpansion

echo Running uv lock...
uv lock
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%

echo Running ruff format...
uv run ruff format .
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%

echo Running ruff check...
uv run ruff check .
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%

echo Running mypy...
uv run mypy --strict mnemo-core/mnemo mnemo-core/tests mnemo-server/mnemo_server
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%

echo Running pytest...
uv run pytest --cov=mnemo --cov-report=term-missing
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%

echo Running pre-commit...
uv run pre-commit run --all-files
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%

echo Building mnemo-core...
cd mnemo-core
uv build
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
cd ..

echo Building mnemo-server...
cd mnemo-server
uv build
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
cd ..

echo Running twine check...
uv run twine check dist/*
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%

echo ALL CHECKS PASSED
