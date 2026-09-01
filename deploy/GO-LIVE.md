# Going live on the new server

Read this before deploying. It is written to be self-sufficient: a session that
has never seen this project should be able to follow it end to end.

`deploy/README.md` describes the stack and the routine update loop. **This file
covers the current server and the first go-live**, including everything already
done, so you do not repeat it.

---

## Current status — 1 September 2026, 02:40 UTC

**The site is live.** `https://fteacherssupport.uz` serves `main` at `c3ce29d`
(the listening-groups work, Parts 1–7). Both containers are running and healthy,
Let's Encrypt certificates are valid for the apex and `www`, and `TESTGEN_SSL=1`
is in effect — HSTS is being sent.

Verified from outside: `/login/` 200, `/` and `/admin/` 302 to login, `/media/`
and `/static/` 200, `www` 301 to the apex.

**Part 8 is done.** Hussain gave the go-ahead and the 48 live papers were rebuilt
with the new allocator at 07:00 UTC, after a backup to
`~/backups/db-pre-rebuild-2026-09-01-0659.sqlite3`.

```
$ python manage.py build_papers --resample
Built 48 papers (48 sampled, 0 already complete and left unchanged).

$ python manage.py check_papers
All 48 papers pass: complete sections, no component shared beyond its reuse cap
within any grade, and all 24 sittings share one recording pair while sharing no
questions, prompt or passage.
```

An independent audit of the same shape as the original bug report confirms it:
**audio mismatch 0 of 24, shared speaking 0 of 24, shared passage 0 of 24** —
down from 24 audio mismatches and 10 speaking-prompt leaks.

**Do not re-run `build_papers`.** Listening and reading allocation are
deterministic, but writing and speaking are drawn with unseeded `random`, so
every run reshuffles those two sections and issues different papers. Re-run only
if a build has actually failed.

Still outstanding, deliberately: the listening key sign-off is lapsed, awaiting a
human check of the 200 answers (`verify_listening_keys`). `KeyVerification` is a
pure audit record — nothing in the serving or rendering path consults it — so it
blocks nothing.

---

## The server

| | |
|---|---|
| Public hostname | `fteacherssupport.uz` (and `www.`) |
| Public IP | `46.8.195.140` |
| Provider | Airnet (BKM), Ubuntu 24.04 LTS |
| Login | `ubuntu`, key auth |
| Key (on the Windows box) | `~/.ssh/mopse_vps`, aliased `mopse` in `~/.ssh/config` |
| Repo on the server | `/home/ubuntu/test-generator` |
| GitHub | `git@github.com:HussainN91/Test-generator.git`, via the deploy key at `~/.ssh/id_ed25519` on the server |

**The old server, `46.8.195.231`, is gone.** It stopped responding and was not
recoverable. Anything still pointing at it is stale, including older notes that
name it. Its `db.sqlite3` and `media/` died with it — which is why both had to be
re-uploaded by hand, and why "Known gaps" at the bottom matters more than it looks.

The VM's own address is `10.10.31.42`; Airnet NATs it. That is fine — inbound 80
and 443 were tested end to end — but it means a connectivity failure is a provider
ticket, not something fixable from inside the box.

---

## What the stack is

```
internet --80/443--> caddy --> testgen:8000 (gunicorn) --> /app/db.sqlite3
                       |
                       +-- caddy_data volume: Let's Encrypt account + certificates
```

Two containers, one compose project, no external network and no shared proxy.
Caddy belongs to **this** repo now; the old server borrowed UZTGBOT's, and UZTGBOT
is retired.

Both containers read the same `.env`, so the hostname is declared exactly once.

---

## Already done on 46.8.195.140 — verified 1 September 2026

Do not redo these. They are listed so you can *check* rather than assume.

- Ubuntu 24.04, fully upgraded (355 packages), rebooted.
- Docker 29.7.2 and Compose v5.5.0 installed. `ubuntu` is in the `docker` group;
  `docker ps` works without `sudo`.
- Repo cloned at `~/test-generator`, on `main` at `589fc3d`, working tree clean.
- The GitHub deploy key authenticates. `ssh -T git@github.com` returns
  "Hi HussainN91/Test-generator!", and `git ls-remote origin` resolves `main`.
- `.env` written at the repo root, `chmod 600`, 7 keys, `TESTGEN_SSL=0`.
- `db.sqlite3` uploaded — 1,822,720 bytes, the working database from the Windows
  machine (928 bank items, 60 units, 48 diagnostic papers, 4 users).
- `media/` uploaded — 136 files, roughly 80 MB of client listening audio.
- DNS: apex and `www` both resolve to `46.8.195.140`, checked from the server.
- **Inbound 80 and 443 reach the VM from the public internet.** Verified with a
  throwaway container listening on each port, curled from outside. This is the
  ACME path, so Let's Encrypt validation will work.
- Base images `python:3.12-slim` and `caddy:2-alpine` are pre-pulled, so the first
  build does not wait on a registry download.
- From inside a container, `deb.debian.org` and `pypi.org` are both reachable —
  the two things the `Dockerfile` needs at build time. (Worth knowing: this box
  briefly could not resolve `download.docker.com` during setup. If a build fails
  on name resolution, that is the symptom, and `/etc/systemd/resolved.conf.d/`
  is where to add public DNS.)

### Deliberately not verified

`ufw status` and `sshd -T` need an interactive `sudo` password, so they could not
be checked non-interactively. **Run this once before announcing the site:**

```bash
sudo sh -c 'ufw status | head -3; sshd -T | grep -i ^passwordauthentication'
```

You want `Status: active` and `passwordauthentication no`. If the firewall is
inactive:

```bash
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw allow 443/udp && sudo ufw --force enable
```

Note that Docker publishes ports through its own iptables chain, which bypasses
ufw's INPUT rules. The site is reachable whether or not ufw is enabled — ufw is
protecting everything *else* on the box, not Caddy.

---

## Deploying

Nothing here runs automatically. Every step is one a person runs and checks.

### 1. Push the code first

The server pulls from GitHub `main`. Code that exists only on the Windows machine
will not deploy. From the local repo:

```bash
git push origin main
```

### 2. Pull it on the server

```bash
ssh mopse
```

```bash
cd ~/test-generator && git pull
```

If `git pull` reports local modifications, **stop and look** rather than forcing.
The server's tree should never carry hand-edits. The only files that belong there
and are not in git are `.env`, `db.sqlite3` and `media/`, all gitignored.

### 3. Build and start

```bash
cd ~/test-generator && docker compose up -d --build
```

This builds the app image and starts both services. `deploy/entrypoint.sh` runs
`manage.py migrate --noinput` on every start, so schema changes apply themselves.
There is no separate migration step.

The uploaded database sits at `step` migration `0008`. The first start carries it
forward to whatever `main` contains, which creates the activity and announcement
tables. Expected, and it happens once.

### 3b. Load content that migrations do not carry

`entrypoint.sh` runs `migrate` and nothing else, so anything delivered by a
management command rather than a data migration will not arrive on its own.
Currently that means the second listening question sets:

> ### Rebuild the image before running a loader, not just `git pull`
>
> The `Dockerfile` does `COPY . .`, so authored payloads like
> `diagnostics/authored/listening_set_2.json` are **baked into the image**. A
> `git pull` updates the host checkout; the running container keeps the old file.
> Only the bind-mounted paths — `db.sqlite3` and `media/` — cross that boundary
> without a rebuild.
>
> **This fails silently.** On 1 September 2026 a corrected payload was pulled and
> the loader run without a rebuild in between. It read the stale file from inside
> the image, rebuilt set 2 from the defective content, and printed its normal
> success line. Nothing downstream contradicts it.
>
> So: `git pull`, then `docker compose up -d --build`, then confirm the payload
> actually changed inside the container, and only then run the loader.
>
> ```bash
> cd ~/test-generator && echo "host:  $(md5sum diagnostics/authored/listening_set_2.json | cut -c1-32)" && echo "image: $(docker compose exec -T testgen md5sum /app/diagnostics/authored/listening_set_2.json | cut -c1-32)"
> ```
>
> The two hashes must match before the loader is worth running.

```bash
cd ~/test-generator && docker compose exec -T testgen python manage.py load_listening_set_2
```

Idempotent and all-or-nothing — it validates the whole payload and confirms every
referenced image exists before writing, in one transaction, and re-running deletes
and rebuilds set 2 without touching set 1. It needs all 20 `AudioClip` rows present
and the ten `clip-{01,05,09,13,15}-q{6,7}.jpg` files under
`media/diagnostics/listening/`, and fails loudly rather than partially if either is
missing.

It prints a warning that the listening key sign-off has lapsed. That is expected
and harmless: `KeyVerification` is a pure audit record, read only by the admin
display and the verification command, and nothing in the serving path consults it.

**Take a backup before any command that writes to production data.** There is no
scheduled backup yet (see Known gaps), so do it by hand:

```bash
cd ~/test-generator && docker compose exec -T testgen python -c "import sqlite3; s=sqlite3.connect('/app/db.sqlite3'); d=sqlite3.connect('/tmp/backup.sqlite3'); s.backup(d); d.close(); s.close()" && docker cp test-generator-testgen-1:/tmp/backup.sqlite3 ~/backups/db-$(date +%F-%H%M).sqlite3
```

That uses SQLite's own backup API from inside the container, which is consistent
under WAL — a plain `cp` of the file on the host is not.

### 4. Watch it come up

```bash
cd ~/test-generator && docker compose logs -f --tail=80
```

Expect, in order: migrations applying, `Listening at: http://0.0.0.0:8000` from
gunicorn, and Caddy logging a certificate obtained for both names. `Ctrl-C` stops
following the logs; it does not stop the stack.

### 5. Confirm from outside

```bash
curl -sSI https://fteacherssupport.uz/login/
```

A `200` over real HTTPS means Caddy holds a valid certificate and Django is
answering behind it.

### 6. Turn on the SSL hardening

Only now, not before.

```bash
cd ~/test-generator && sed -i 's/^TESTGEN_SSL=0/TESTGEN_SSL=1/' .env && docker compose up -d
```

This enables the HTTPS redirect, HSTS and proxy scheme detection. Doing it before
a certificate exists produces a redirect loop on a site you then cannot reach in
order to fix it — which is why it is a separate step.

Re-run the check from step 5 afterwards. Still `200`.

### 7. Change the default passwords

> **Deferred for the first go-live, on Hussain's decision (1 September 2026).**
> The passwords stay on their current values so his superiors can log in and
> review without needing new credentials. Do this step **after** that review.
>
> Deferred, not cancelled. Note that the site does not stay unknown: Let's
> Encrypt publishes every certificate it issues to Certificate Transparency
> logs, which are public and scraped by scanners within minutes. The hostname
> becomes discoverable at issuance, not at announcement.

The uploaded database carries the accounts documented in `README.md`:
`admin` / `changeme-admin-2026` and `teacher` / `changeme-teacher-2026`. They are
written down in a repo. On a public site they are an open door.

```bash
cd ~/test-generator && docker compose exec testgen python manage.py changepassword admin
```

```bash
cd ~/test-generator && docker compose exec testgen python manage.py changepassword teacher
```

The database also holds `verify_audio_user` and `maria`, left over from local
work. Decide whether they belong in production:

```bash
cd ~/test-generator && docker compose exec testgen python manage.py shell -c "from django.contrib.auth import get_user_model; print(list(get_user_model().objects.values_list('username','is_superuser','is_active')))"
```

---

## Routine updates after this

```bash
ssh mopse 'cd ~/test-generator && git pull && docker compose up -d --build && docker compose logs -f --tail=50'
```

Changed only `deploy/Caddyfile`? `docker compose restart caddy` is enough.

---

## Verifying the whole thing at once

Read-only, run from the Windows machine.

```bash
ssh mopse 'cd ~/test-generator; echo "head: $(git log --oneline -1)"; echo "db: $(stat -c %s db.sqlite3) bytes"; echo "media: $(find media -type f | wc -l) files"; docker compose ps'
```

```bash
curl -sS -o /dev/null -w 'https: %{http_code}\n' https://fteacherssupport.uz/login/
```

---

## When it goes wrong

**Caddy cannot get a certificate.** Read `docker compose logs caddy`.

- *DNS* — the name no longer resolves to `46.8.195.140`. Check the A record in
  Airnet's billing panel. Note `www` is a CNAME to the apex, which is fine.
- *Timeout reaching port 80* — the NAT mapping. This worked on 1 September 2026;
  if it stops, it is an Airnet support ticket. Prove it independently by stopping
  the stack and running
  `docker run -d --rm -p 80:80 --name t python:3.12-slim python -m http.server 80`,
  then curling `http://fteacherssupport.uz/` from another machine. Clean up with
  `docker rm -f t`.
- *Rate limited* — Let's Encrypt allows 5 duplicate certificates per week for the
  same set of names. **Do not retry into the limit; wait.** The certificates live
  in the `caddy_data` volume, so never delete that volume while tidying up.

**Django returns 400 on every request.** `TESTGEN_ALLOWED_HOSTS` does not contain
the hostname being used. Check `.env`, and check it for stray characters while you
are there — a chat client once rewrote a bare `www.` hostname into a markdown link
on its way into that file. `grep -c '[][()]' .env` should print `0`.

**`db.sqlite3` is a directory rather than a file.** Compose bind-mounts it as a
file; if it did not exist beforehand, Docker created a directory with that name.
Stop the stack, remove it, restore the real file, start again.

**Rolling back is code-only:**

```bash
cd ~/test-generator && git checkout <previous-sha> && docker compose up -d --build
```

Migrations are forward-only. A rollback runs older code against the newer schema,
which works because every migration is additive. Restoring a database copy is not
a rollback — it also destroys everything entered since that copy was made.

---

## Known gaps

Real, currently unaddressed, and worth fixing rather than rediscovering.

**1. There is no backup.** UZTGBOT had `deploy/backup.sh`, a nightly encrypted
off-site push, and `restore-drill.sh`. The Test Generator inherited that project's
Caddy but not its backups. A server's worth of data was just lost to a dead VPS;
this is the same exposure, unchanged. A single-file SQLite database makes the fix
cheap — a nightly `sqlite3 .backup`, an off-site copy, and a restore drill that
proves it works. An untested backup is a belief, not a capability.

**2. The SQLite bind mount is fragile.** `docker-compose.yml` mounts the single
file `./db.sqlite3`, and `settings.py` sets `journal_mode=WAL`. SQLite's `-wal`
and `-shm` sidecar files are therefore created *inside the container*, not on the
host, because only the file is mounted and not its directory. Committed data can
sit in a WAL that vanishes when the container is replaced. The fix is small,
because `TESTGEN_DB_PATH` is already supported: mount a directory
(`./data:/app/data`) and set `TESTGEN_DB_PATH=/app/data/db.sqlite3`.

**3. `media/` and `db.sqlite3` are gitignored.** Rebuilding from the repo alone
reproduces the application and none of the content.

**4. The server database is the source of truth. Never upload the Windows copy
over it.** This one can destroy data while looking like a rescue.

`D:\Test generator\db.sqlite3` on the Windows machine is a **stale development
artifact**. It was uploaded during provisioning and nothing has touched it since:
verified 1 September 2026, it sits at `diagnostics` migration `0012` and has no
`diagnostics_listeningquestionset` table at all. The server is at `0017` and holds
the 100 set-2 questions the loader wrote.

So re-uploading the Windows file — the obvious reflex when something looks broken
and gap 1 means there is no scheduled backup to reach for — would silently revert
the schema and delete the set-2 content, and once the papers are rebuilt it would
destroy those too. **It would look like a restore and behave like a wipe.**

Recover from `~/backups/` on the server, never from the Windows box.

This is sharper than it first appears because the two copies cannot be reconciled
by rebuilding both: `build_papers` samples writing and speaking with unseeded
`random`, so a rebuild on each machine produces different papers. There is exactly
one correct copy of the paper content, and it lives on the server and in its
backups.
