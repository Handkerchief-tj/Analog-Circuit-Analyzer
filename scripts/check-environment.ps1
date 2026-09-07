param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")

& $Python -c "import sys, SLiCAP, fastapi, pydantic, PySide6, sfg_prototype; from importlib.metadata import version; assert sys.version_info[:2] == (3, 12); assert SLiCAP.__version__ == '5.2.1'; print('Python', sys.version.split()[0]); print('SLiCAP', SLiCAP.__version__); print('PySide6', PySide6.__version__); print('FastAPI', fastapi.__version__); print('Pydantic', pydantic.__version__); print('sfg-prototype', version('sfg-prototype'))"
if ($LASTEXITCODE -ne 0) { throw "Python environment check failed." }

$env:PYTHONPATH = Join-Path $root "backend"
$env:PYTHONDONTWRITEBYTECODE = "1"
& $Python -m pytest (Join-Path $root "backend\tests") -q -p no:cacheprovider
if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }
