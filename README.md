# Revozi Backend API

FastAPI backend for the Revozi Feedback Response Assistant.

## Quick Start

### Option 1: Docker Compose
```bash
docker-compose up -d
# Run migrations
docker-compose exec api alembic upgrade head
# Seed demo data
docker-compose exec api python -m scripts.seed
```

### Option 2: Local Development
```bash
# 1. Start PostgreSQL (local or via Docker)
docker run -d --name revozi-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=revozi -p 5432:5432 postgres:16-alpine

# 2. Set up Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your settings

# 4. Run migrations
alembic upgrade head

# 5. Seed demo data (optional)
python -m scripts.seed

# 6. Start the server
uvicorn app.main:app --reload --port 8000
```

### API Docs
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Environment Variables

See `.env.example` for all required variables.

| Variable | Required | Description |
|----------|----------|-------------|
| DATABASE_URL | Yes | PostgreSQL connection string |
| JWT_SECRET_KEY | Yes | Secret for signing JWT tokens |
| SECRET_KEY | Yes | Application secret key |
| CORS_ORIGINS | Yes | Comma-separated allowed origins |
| OPENAI_API_KEY | No* | OpenAI API key for analysis |
| ANTHROPIC_API_KEY | No* | Anthropic API key for analysis |
| STRIPE_SECRET_KEY | No | Stripe secret key for billing |
| STRIPE_WEBHOOK_SECRET | No | Stripe webhook signing secret |

*At least one LLM API key recommended for full analysis. Falls back to heuristic analysis without one.

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /api/v1/health | No | Health check |
| POST | /api/v1/auth/signup | No | Create account |
| POST | /api/v1/auth/login | No | Login |
| POST | /api/v1/auth/refresh | Cookie | Refresh access token |
| POST | /api/v1/auth/logout | No | Logout |
| POST | /api/v1/auth/forgot-password | No | Password reset |
| GET | /api/v1/users/me | JWT | Current user |
| GET | /api/v1/workspaces | JWT | List workspaces |
| GET | /api/v1/workspaces/:id | JWT | Get workspace |
| PATCH | /api/v1/workspaces/:id | JWT | Update workspace |
| GET | /api/v1/workspaces/:id/feedback | JWT | List feedback (paginated) |
| POST | /api/v1/workspaces/:id/feedback | JWT | Create feedback |
| GET | /api/v1/workspaces/:id/feedback/:id | JWT | Feedback detail |
| POST | /api/v1/feedback/:id/drafts/:id/regenerate | JWT | Regenerate draft |
| PATCH | /api/v1/feedback/:id/drafts/:id | JWT | Edit draft |
| POST | /api/v1/feedback/:id/drafts/:id/reply | JWT | Post reply |
| GET | /api/v1/workspaces/:id/insights | JWT | Weekly insights |
| GET | /api/v1/billing/subscription | JWT | Get subscription |
| POST | /api/v1/billing/checkout | JWT | Create checkout |
| POST | /api/v1/billing/webhook | Stripe | Webhook handler |
| GET | /api/v1/admin/workspaces | Admin | List all workspaces |
| GET | /api/v1/admin/metrics | Admin | System metrics |

## Testing
```bash
pytest tests/ -v
```

## Demo Account
After running the seed script:
- Email: demo@revozi.com
- Password: demo123

## Security Notes
- JWT access tokens (30min) + HTTP-only refresh cookies (7 days)
- bcrypt password hashing
- Admin endpoints require role=admin
- Reply posting requires explicit user approval
- No auto-posting of responses
- AI suggestions clearly labeled as suggestions
- No PII in analysis logs
