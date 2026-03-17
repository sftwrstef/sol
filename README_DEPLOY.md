# Deploying Sol Space on Vercel + Supabase

## Stack

- Vercel runs the Flask app as a Python serverless function via `api/index.py`
- Supabase provides Postgres
- Vercel environment variables provide secrets

## Supabase

1. In Supabase, open the database connection settings.
2. Copy the transaction pooler connection string.
3. Use the `psycopg2`/SQLAlchemy form and keep `sslmode=require`.
4. Set that value as `DATABASE_URL` in Vercel.

This app also accepts `SUPABASE_DB_URL`, but `DATABASE_URL` should be the primary value.

## Vercel Environment Variables

Set these in Vercel before the first deploy:

- `DATABASE_URL`
- `SESSION_SECRET`
- `SESSION_COOKIE_SECURE=true`
- `SESSION_COOKIE_SAMESITE=Lax`
- `OPENROUTERAI_API` if you are using OpenRouter
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` if needed

## Notes

- `public/` is used for frontend assets so Vercel can serve them directly.
- The app switches SQLAlchemy to `NullPool` on Vercel and works with Supabase pooler URLs.
- Use the transaction pooler, not a raw direct connection, for serverless deployments.

## Before public launch

- add rate limiting
- add password reset/email verification
- define chat retention and deletion policy
- verify Supabase backups and restoration settings
