# HORIZON Backend API

## Install
From `D:\Horizon` with the project virtual environment activated:

```powershell
python -m pip install -r backend/requirements.txt
```

## Run
```powershell
python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

## Test
Open:
- http://127.0.0.1:8000/api/health
- http://127.0.0.1:8000/docs

The API reads the existing PostgreSQL database. It does not create or modify tables.
