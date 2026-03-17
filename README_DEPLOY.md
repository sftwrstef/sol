# Deploying Sol Space

## Recommended host

Use Render with managed Postgres for the fastest production setup. The repo includes `render.yaml` so Render can provision:

- a Python web service
- a managed Postgres database
- generated session secret
- secure cookie defaults

## Required secrets

Set these in the host environment:

- `SESSION_SECRET`
- `DATABASE_URL`
- `OPENAI_API_KEY` or `OPENROUTERAI_API` or `ANTHROPIC_API_KEY`

## Start command

```bash
gunicorn --bind 0.0.0.0:$PORT app:app
```

## Before public launch

- use managed Postgres, not SQLite
- enforce HTTPS and keep `SESSION_COOKIE_SECURE=true`
- rotate `SESSION_SECRET`
- add rate limiting
- add password reset/email verification
- define chat retention and deletion policy
