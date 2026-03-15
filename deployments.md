```markdown
# Deployment Guide — FlashLearn

## Stack
- Backend: FastAPI — Docker container on Railway
- Frontend: React/Vite — Docker + Nginx container on Railway
- Database: PostgreSQL — Railway managed plugin
- CI/CD: GitHub Actions

---

## Project Structure Required
```
flashlearn/
├── backend/
│   ├── Dockerfile
│   ├── main.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   └── .env.example
├── docker-compose.yml
├── .github/
│   └── workflows/
│       └── ci.yml
├── CLAUDE.md
├── DESIGN.md
└── deployment.md
```

---

## Step 1 — Dockerfiles

### backend/Dockerfile
```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### frontend/Dockerfile
```dockerfile
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

### frontend/nginx.conf
```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

---

## Step 2 — Docker Compose (local testing only)

### docker-compose.yml
```yaml
version: '3.8'

services:
  db:
    image: postgres:16
    restart: always
    environment:
      POSTGRES_DB: flashlearn
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://postgres:postgres@db:5432/flashlearn
      GEMINI_API_KEY: ${GEMINI_API_KEY}
      SECRET_KEY: ${SECRET_KEY}
      CORS_ORIGINS: http://localhost:3000
    depends_on:
      - db
    restart: always

  frontend:
    build:
      context: ./frontend
      args:
        VITE_API_URL: http://localhost:8000
    ports:
      - "3000:80"
    depends_on:
      - backend
    restart: always

volumes:
  postgres_data:
```

### Test locally before deploying
```bash
# Copy and fill in your env
cp .env.example .env

# Build and run everything
docker compose up --build

# App should be at http://localhost:3000
# API should be at http://localhost:8000/docs

# Tear down
docker compose down
```

---

## Step 3 — Environment Variables

### backend/.env.example
```
GEMINI_API_KEY=
SECRET_KEY=
DATABASE_URL=
CORS_ORIGINS=
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
```

### frontend/.env.example
```
VITE_API_URL=
```

### Generate a SECRET_KEY
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Step 4 — Database Migrations on Startup

In backend/main.py, run Alembic migrations automatically on startup:

```python
from alembic.config import Config
from alembic import command

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run migrations on every startup
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    yield

app = FastAPI(lifespan=lifespan)
```

This ensures Railway always has the latest schema on deploy.

---

## Step 5 — GitHub Actions CI/CD

### .github/workflows/ci.yml
```yaml
name: CI/CD

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test-backend:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: flashlearn_test
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install pytest pytest-asyncio httpx

      - name: Run tests
        run: |
          cd backend
          pytest tests/ -v
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/flashlearn_test
          SECRET_KEY: test-secret-key-for-ci
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          CORS_ORIGINS: http://localhost:5173

  test-frontend:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: |
          cd frontend
          npm ci

      - name: Run tests
        run: |
          cd frontend
          npm run test

  deploy-backend:
    needs: [test-backend, test-frontend]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'

    steps:
      - uses: actions/checkout@v4

      - name: Install Railway CLI
        run: npm install -g @railway/cli

      - name: Deploy backend
        run: |
          cd backend
          railway up --service flashlearn-backend
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}

  deploy-frontend:
    needs: [test-backend, test-frontend]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'

    steps:
      - uses: actions/checkout@v4

      - name: Install Railway CLI
        run: npm install -g @railway/cli

      - name: Deploy frontend
        run: |
          cd frontend
          railway up --service flashlearn-frontend
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
```

---

## Step 6 — Railway Setup (do this once manually)

### 1. Create Railway project
- Go to railway.app
- New Project → Deploy from GitHub repo
- Select your flashlearn repo

### 2. Add PostgreSQL
- Inside your Railway project → Add Plugin → PostgreSQL
- Railway automatically sets DATABASE_URL in the environment
- Copy the DATABASE_URL — you'll need it locally too

### 3. Add Backend service
- New Service → GitHub Repo → select flashlearn
- Set root directory: /backend
- Railway auto-detects Dockerfile
- Add environment variables:
```
GEMINI_API_KEY=your_key
SECRET_KEY=your_generated_secret
CORS_ORIGINS=https://your-frontend.up.railway.app
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
```
- Deploy → copy the generated URL e.g. https://flashlearn-backend.up.railway.app

### 4. Add Frontend service
- New Service → GitHub Repo → select flashlearn
- Set root directory: /frontend
- Add environment variables:
```
VITE_API_URL=https://flashlearn-backend.up.railway.app
```
- Deploy → copy the generated URL e.g. https://flashlearn-frontend.up.railway.app

### 5. Update CORS
- Go back to backend service
- Update CORS_ORIGINS to your actual frontend URL
- Redeploy backend

### 6. Add secrets to GitHub
- Go to GitHub repo → Settings → Secrets → Actions
- Add:
```
RAILWAY_TOKEN        — from Railway dashboard → Account → Tokens
GEMINI_API_KEY       — your Gemini key
```

---

## Step 7 — Verify Deployment

```bash
# Check backend is live
curl https://your-backend.up.railway.app/health

# Expected response
{ "status": "ok" }

# Check API docs are accessible
open https://your-backend.up.railway.app/docs
```

Add a health check endpoint to backend/main.py:
```python
@app.get("/health")
def health():
    return {"status": "ok"}
```

---

## Deployment Checklist
- [ ] docker compose up works locally
- [ ] All tests pass locally
- [ ] .env.example files are filled in correctly
- [ ] SECRET_KEY is generated and set in Railway
- [ ] DATABASE_URL is set from Railway PostgreSQL plugin
- [ ] CORS_ORIGINS matches actual frontend Railway URL
- [ ] VITE_API_URL matches actual backend Railway URL
- [ ] GitHub secrets RAILWAY_TOKEN and GEMINI_API_KEY are set
- [ ] /health endpoint returns 200
- [ ] Full flow works on live URL: register → upload → flashcards → quiz

---

## Common Issues

**CORS error on frontend**
— CORS_ORIGINS in backend does not match the frontend URL exactly. No trailing slash.

**DATABASE_URL not found**
— Railway PostgreSQL plugin not linked to backend service. Go to Railway → backend service → Variables → check DATABASE_URL is injected.

**Migrations not running**
— Alembic lifespan hook not added to main.py. See Step 4.

**Frontend shows blank page**
— VITE_API_URL is wrong or not set. Check frontend Railway service variables.

**CI passes but deploy fails**
— RAILWAY_TOKEN secret is missing or expired. Regenerate in Railway dashboard.
```
---

> "Read deployment.md and implement everything in it — Dockerfiles, docker-compose, GitHub Actions workflow, and the health check endpoint."
