# SajiloKabadi — Backend (Modular Monolith)

Django backend for SajiloKabadi, a scrap/recyclable collection marketplace:
sellers list scrap (metal, paper & plastic, e-waste, etc.), request pickups,
get paid into an in-app wallet, and track their environmental impact.
Collectors pick up material against live, category-based rates.

## Architecture

Single Django project (`config`), split into independently-owned,
loosely-coupled **apps** under `apps/` — a modular monolith. Each app:

- owns its own models, migrations, serializers, views, urls, admin, tests
- exposes a small `services.py` / `selectors.py` for cross-app calls instead
  of other apps reaching into its models directly
- is wired into the URL root under its own `/api/v1/<app>/` prefix

This keeps clear module boundaries now, and each app can be extracted into
its own service later without a rewrite, if/when that's ever needed.

## App map

| App             | Responsibility                                                        |
|------------------|------------------------------------------------------------------------|
| `accounts`       | Custom User model, phone number + OTP auth, JWT issuing                |
| `sellers`        | Seller profile (the "BS" avatar / seller-mode data)                    |
| `collectors`     | Collector/rider profile (e.g. "Ram Tamang is on the way")              |
| `materials`      | Categories (Metal / Paper & plastic / ...) + materials + live rates    |
| `pickups`        | Pickup requests, scheduling, items, status timeline                    |
| `wallet`         | Wallet balance, transactions, withdrawals                              |
| `dropoff`        | Nearby drop-off point directory                                        |
| `impact`         | Aggregated environmental impact stats ("My impact")                    |
| `notifications`  | Push/SMS notification dispatch                                         |
| `common`         | Shared base models, permissions, pagination, mixins                    |

## Project layout

```
sajilokabadi/
├── manage.py
├── requirements.txt
├── .env.example
├── config/                  # project-level config, not a Django "app"
│   ├── settings/
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── prod.py
│   ├── urls.py
│   ├── celery.py
│   ├── wsgi.py
│   └── asgi.py
└── apps/
    ├── common/
    ├── accounts/
    ├── sellers/
    ├── collectors/
    ├── materials/
    ├── pickups/
    ├── wallet/
    ├── dropoff/
    ├── impact/
    └── notifications/
```

## API (contract v2, 2026-09-24)

Base URL `https://api.sajilokabadi.com/api/v1`; Swagger at `/api/docs/`. Every
response uses the `{success, message, data}` envelope (errors add `error_code`
and `errors`, with `data` null unless documented), `message` follows
`Accept-Language` (`en`/`ne`), and lists use `{items, page, page_size, total,
has_next}`.

| Area | Endpoints | Module |
|---|---|---|
| Sign-in | `/auth/otp/request/`, `/auth/otp/resend/`, `/auth/otp/verify/`, `/auth/token/refresh/`, `/auth/logout/` | `accounts` |
| Profile | `/me/`, `/me/avatar/`, `/me/device/`, `/me/notification-settings/` | `accounts`, `notifications` |
| Seller | `/seller/dashboard/`, `/me/addresses/` | `sellers` |
| Rates | `/rates/` | `materials` |
| Selling | `/pickups/availability/`, `/pickups/quote/`, `/pickups/`, `/pickups/{id}/`, `.../cancel/`, `.../rating/` | `pickups` |
| Weigh-in | `/pickups/{id}/weigh-sheet/`, `.../flags/`, `.../accept/` | `pickups` |
| Drop-off | `/dropoff-centers/` | `dropoff` |
| Wallet | `/wallet/`, `/wallet/transactions/`, `/wallet/withdrawals/`, `/wallet/statement/`, `/me/payout-methods/` | `wallet` |
| Collector | `/collector/dashboard/`, `/collector/status/`, `/collector/jobs/`, `/collector/location/`, `/collector/pickups/{id}/...` | `collectors` |
| Disputes | `/disputes/` | `pickups` |

Money only moves through `apps/wallet/services.py` (ledger rows, locked
wallet, cached balance). Pickup state changes live in
`apps/pickups/services.py`, each under a row lock. `Idempotency-Key` is
honoured on booking, accepting a sheet, accepting a job and withdrawing.

Support work happens in the Django admin: approve collectors, verify bank
accounts, set material rates (add a rate row), close disputes, and mark
withdrawals transferred or failed.

`python manage.py housekeeping` expires unaccepted pickups, sets silent
collectors offline and prunes old rows; run it every minute from cron.

### Sign-in flow

1. `POST /api/v1/auth/otp/request/` — `{country_code, phone, role, language}`
   → sends a 6-digit code over Aakash SMS, returns `otp_request_id`.
2. `POST /api/v1/auth/otp/resend/` — `{otp_request_id}` → sends a fresh code
   (the old one stops working) and returns a new `otp_request_id`.
3. `POST /api/v1/auth/otp/verify/` — `{otp_request_id, phone, otp, role, device}`
   → creates the user on first sign-in, returns `tokens`, `user`, `is_new_user`.
4. `POST /api/v1/auth/token/refresh/` — `{refresh}` → rotates the token pair.
5. Authenticated requests use `Authorization: Bearer <access_token>`.

`phone` is the 10-digit national number (`9841234471`); the country code is
stored separately. There is no password field on the User model — phone + OTP
is the only credential.

SMS goes out after the request's transaction commits, via Celery
(`SMS_DISPATCH=celery`, run `celery -A config worker`) or a background thread
(`SMS_DISPATCH=thread`). In dev, codes are printed to the console unless
`SMS_BACKEND` points at `apps.notifications.backends.aakash.AakashSMSBackend`.

## Getting started

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser --phone_number 9800000001
python manage.py loaddata apps/materials/fixtures/initial_rates.json
python manage.py runserver
```

## Code style

[Ruff](https://docs.astral.sh/ruff/) lints and formats the code; settings are in
`pyproject.toml` (120-char lines, sorted imports, bug and Django checks).
`pre-commit install` runs it on every `git commit`, together with checks for
whitespace, line endings, YAML/TOML syntax, private keys and `.env` files.
The same Ruff checks run in CI before a deploy.

```bash
ruff check --fix .            # lint and auto-fix
ruff format .                 # format
pre-commit run --all-files    # every hook on every tracked file
```

If a commit is stopped because a hook changed files, `git add` them and commit again.

## Adding a new module

1. `python manage.py startapp <name> apps/<name>` then move it under `apps/`.
2. Add `"apps.<name>"` to `LOCAL_APPS` in `config/settings/base.py`.
3. Add `path("api/v1/<name>/", include("apps.<name>.urls"))` in `config/urls.py`.
4. Keep cross-app reads/writes behind that app's `services.py`, not direct
   model imports, so app boundaries stay real.
