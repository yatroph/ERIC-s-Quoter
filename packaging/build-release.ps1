param(
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version = "1.1.1"
)

$ErrorActionPreference = "Stop"
$packagingRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $packagingRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$spec = Join-Path $packagingRoot "ERICsQuoter.spec"
$innoScript = Join-Path $packagingRoot "ERICsQuoter.iss"
$innoCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
$innoCandidates = @(
    $(if ($innoCommand) { $innoCommand.Source }),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
$innoCompiler = $innoCandidates | Select-Object -First 1

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment not found at $python"
}
if (-not (Test-Path -LiteralPath $innoCompiler)) {
    throw "Inno Setup 6 was not found in PATH or a standard installation folder."
}

$projectMetadata = Get-Content -LiteralPath (Join-Path $projectRoot "pyproject.toml") -Raw
$versionMatch = [regex]::Match($projectMetadata, '(?m)^version\s*=\s*"(?<version>\d+\.\d+\.\d+)"')
if (-not $versionMatch.Success) {
    throw "Could not read the project version from pyproject.toml."
}
if ($Version -ne $versionMatch.Groups['version'].Value) {
    throw "Requested version $Version does not match pyproject.toml version $($versionMatch.Groups['version'].Value)."
}

$versionParts = $Version.Split('.')
$versionTuple = "($($versionParts[0]), $($versionParts[1]), $($versionParts[2]), 0)"
$versionChecks = @(
    @{
        Path = Join-Path $projectRoot "erics_quoter\__init__.py"
        Text = "__version__ = `"$Version`""
    },
    @{
        Path = Join-Path $packagingRoot "version-info.txt"
        Text = "filevers=$versionTuple"
    },
    @{
        Path = Join-Path $packagingRoot "version-info.txt"
        Text = "StringStruct(u'ProductVersion', u'$Version')"
    },
    @{
        Path = Join-Path $packagingRoot "ERICsQuoter.iss"
        Text = "#define MyAppVersion `"$Version`""
    }
)
foreach ($check in $versionChecks) {
    $contents = Get-Content -LiteralPath $check.Path -Raw
    if (-not $contents.Contains($check.Text)) {
        throw "Release version $Version is not synchronized in $($check.Path)."
    }
}

Push-Location $projectRoot
try {
    & $python -m pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
    & $python -m pytest
    if ($LASTEXITCODE -ne 0) { throw "Automated tests failed." }
    & $python -m PyInstaller --noconfirm --clean $spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
    & $innoCompiler "/DMyAppVersion=$Version" $innoScript
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed." }

    $installer = Join-Path $projectRoot "dist\installer\ERICs-Quoter-Setup-v$Version.exe"
    if (-not (Test-Path -LiteralPath $installer)) {
        throw "Installer build completed without producing $installer"
    }
    Write-Output "Installer: $installer"
}
finally {
    Pop-Location
}
