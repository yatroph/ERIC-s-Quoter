# ERIC's Quoter

A small GDI Ainsworth desktop app that creates a new Excel costing workbook from the supplied templates.

## Install on Windows

Download the latest `ERICs-Quoter-Setup` executable from the
[GitHub releases page](https://github.com/yatroph/ERIC-s-Quoter/releases/latest),
run it, and launch **ERIC's Quoter** from the Start menu.

The installer is built for 64-bit Windows 10 and Windows 11. Python and the
app's libraries are bundled, so they do not need to be installed separately.
The current installer is not code-signed, so Windows may display an
**Unknown publisher** or SmartScreen confirmation prompt.

## Test it in VS Code

The repository already includes a project-local `.venv` and an F5 launch profile.

1. Open this folder in VS Code.
2. Press **F5**.
3. Choose **Multi-location** or **Multi-year contract**.
4. Enter the customer, optional project scope, and location details.
5. Select **Create & open workbook**.

If the environment needs to be rebuilt:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

The app never edits either source workbook. Generated files receive unique names and default to `Documents\GDI Quotes`.

Recent customer names are stored only in the current Windows user's local app
data folder. They are not uploaded anywhere.

## Developer checks

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Build the release installer

Inno Setup 6 must be installed. Then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build-release.ps1 -Version 1.0.0
```

The versioned installer is written to `dist\installer`.
