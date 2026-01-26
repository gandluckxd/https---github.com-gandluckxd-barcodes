# Setup (clean checkout)

This repo has two parts:
- `api` (FastAPI server)
- `client` (PyQt client)

## 1) Create venv and install deps

Windows 10/11:
```powershell
cd api
py -3.8 -m venv venv
venv\Scripts\activate
pip install -r requirements.win.txt
```

Windows 7 (build target):
```powershell
cd api
py -3.8 -m venv venv
venv\Scripts\activate
pip install -r requirements.win7.txt
```

macOS:
```bash
cd api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.mac.txt
```

Repeat the same for `client` (use the corresponding requirements file in `client/`).

## 2) Build executables

API:
```powershell
cd api
pyinstaller BarcodesApi.spec
pyinstaller BarcodesApi.win7.spec
```

Client:
```powershell
cd client
pyinstaller BarcodesClient.spec
pyinstaller BarcodesClient.win7.spec
```

## Notes

- Windows 7 compatibility depends on Python 3.8 and PyInstaller 4.x.
- `fbclient.dll` path in the spec files is absolute. Install Firebird client in the same path
  or edit the spec to match your machine.
