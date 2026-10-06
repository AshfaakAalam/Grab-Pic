# Event Photo App (FastAPI + PostgreSQL)

Create events and upload photos to them. Metadata lives in PostgreSQL;
image files live in `static/uploads/` (to be replaced by S3/MinIO later).

## 1. Create the PostgreSQL database

Install PostgreSQL first if needed:

```bash
# Ubuntu/Debian
sudo apt install postgresql
# macOS (Homebrew)
brew install postgresql@16 && brew services start postgresql@16
# Windows: use the installer from postgresql.org
```

Open a `psql` shell as the superuser (`sudo -u postgres psql` on Linux, `psql postgres` on macOS, `psql -U postgres` on Windows) and run:

```sql
CREATE USER event_app WITH PASSWORD 'choose-a-strong-password';
CREATE DATABASE event_photo_app OWNER event_app;
\q
```

Check the login works:

```bash
psql "postgresql://event_app:choose-a-strong-password@localhost:5432/event_photo_app" -c "SELECT 1;"
```

## 2. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Configure `.env`

```bash
cp .env.example .env
```

Edit `DATABASE_URL` with your real password. If the password contains special
characters (`@ : / %`), URL-encode them.

## 4. Migrations (Alembic is already configured, no `alembic init` needed)

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

Open the generated file in `migrations/versions/` and read it before applying.
Commit it to git.

## 5. Run

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 (interactive API docs for any JSON routes: `/docs`).
