# Setup (clean checkout)

This repo has two parts:
- `api` (FastAPI server)
- `client` (PyQt client)

## 1) Create venv and install deps

Windows 10/11 (Python 3.10.x, 32-bit required for API/Client because of Firebird):
```powershell
cd api
py -3.10-32 -m venv venv
venv\Scripts\activate
pip install -r requirements.win.txt
```

Windows 7 (Python 3.8.x only, 32-bit required for API/Client because of Firebird):
```powershell
cd api
py -3.8-32 -m venv venv
venv\Scripts\activate
pip install -r requirements.win7.txt
```

macOS (Python 3.10.x):
```bash
cd api
python3.10 -m venv venv
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
- API and client must use 32-bit Python on Windows because Firebird client is 32-bit.
- Bitness must match: Python, PyInstaller, and Firebird client DLL should all be x86.
- `fbclient.dll` path in the spec files is absolute. Install Firebird client in the same path
  or edit the spec to match your machine.
