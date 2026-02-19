# DB Cutover (SQLite -> Postgres on free tier)

## Recommended free target
- **Neon free Postgres** (best free option currently).
- Keep Render web service, point `DATABASE_URL` to Neon connection string.

## Steps

1. Create Neon project (free), copy pooled `DATABASE_URL`.
2. In local shell:
   ```bash
   export DATABASE_URL='postgresql://...'
   ./scripts/migrate_sqlite_to_postgres.sh
   ```
3. Validate data in Postgres:
   ```bash
   DATABASE_URL="$DATABASE_URL" python3 manage.py shell -c "from companies.models import Company; print(Company.objects.count())"
   ```
4. In Render service settings:
   - Set `DATABASE_URL` to Neon URL
   - Redeploy
5. Run migrations on Render deploy command (or release command):
   ```bash
   python manage.py migrate --noinput
   ```

## Rollback
- Revert `DATABASE_URL` on Render to old DB URL and redeploy.

## Notes
- `pgloader` path is much faster for large DBs.
- Fallback dump/loaddata is slower and can be memory-heavy.
- If needed, run migration in off-peak window and put app in maintenance mode during final sync.
