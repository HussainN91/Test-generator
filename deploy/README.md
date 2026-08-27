# Deployment

The Test Generator runs as a **self-contained two-container stack**: the Django
app under gunicorn, and Caddy in front of it terminating TLS.

```
internet ──443──▶ caddy ──▶ testgen:8000 (gunicorn)
                    │
                    └── caddy_data volume: LE account + certificates
```

Everything it needs is in this repo:

| File | Role |
|---|---|
| `docker-compose.yml` | both services, the network, the cert volume |
| `Dockerfile` | the app image |
| `deploy/entrypoint.sh` | migrate, then exec gunicorn |
| `deploy/Caddyfile` | the one site block, proxying to `testgen:8000` |
| `.env` (server only, gitignored) | secrets and the hostname |

There is **no external network and no shared proxy**. The stack starts and stops
on its own.

## `.env`

Lives at the repo root on the server and is never committed. Required keys:

```
TESTGEN_DOMAIN=testgen.example.com
TESTGEN_SECRET_KEY=<long random string>
TESTGEN_DEBUG=0
TESTGEN_ALLOWED_HOSTS=testgen.example.com
TESTGEN_CSRF_TRUSTED_ORIGINS=https://testgen.example.com
TESTGEN_SSL=1
```

`TESTGEN_DOMAIN` is read by **both** containers — Caddy substitutes it as the
site address, so the hostname is declared once. The three host-related values
must agree, or you get either a cert for the wrong name or a Django 400.

## Routine update

```
cd ~/test-generator
git pull
docker compose up -d --build
docker compose logs -f --tail=50
```

`up -d --build` rebuilds only the app image; Caddy is a stock image and only
restarts if you edited `deploy/Caddyfile`. Migrations run automatically from
`deploy/entrypoint.sh` on every start.

Changed only the Caddyfile? `docker compose restart caddy` is enough.

## History: the UZTGBOT decoupling

This stack used to attach to `uztgbot_default`, an external network owned by a
separate Telegram-bot compose project on the same VPS, and it was proxied by
**that** project's Caddy. UZTGBOT has been retired. Caddy was kept, but it now
belongs to this repo.

Two consequences worth remembering:

- **The `caddy_data` volume holds the certificates.** Do not delete it while
  tidying up. Let's Encrypt rate-limits duplicate certificates to 5 per week.
- **The app service is named `testgen`, not `web`.** It was renamed to avoid a
  DNS alias collision with the bot's own `web` service on the shared network.
  That collision is gone, but `deploy/Caddyfile` proxies to `testgen:8000`, so
  the name and the Caddyfile have to stay in step.
