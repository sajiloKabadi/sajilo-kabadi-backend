# SajiloKabadi API: development deployment (AWS EC2)

One EC2 instance runs everything. Every push to `develop` tests, builds, and
deploys automatically.

```
git push origin develop
  -> GitHub Actions: tests -> docker build -> push to GHCR
  -> SSH to EC2 -> /opt/sajilokabadi/deploy.sh
       pull image -> migrate (old API still serving) -> swap API container
  -> check https://api.sajilokabadi.com/health/

EC2 (Ubuntu 24.04)
  Nginx :80/:443 (public, Let's Encrypt) -> 127.0.0.1:8000
  Docker network "backend"
    sajilokabadi-api       (gunicorn, port 8000 on localhost only)
    sajilokabadi-postgres  (no published port; volume postgres_data)
```

Everywhere below, replace:

| Placeholder | Example |
|---|---|
| `<EIP>` | the Elastic IP from step 4, e.g. `13.200.10.20` |
| `<github-username>` | your GitHub user, lowercase |
| `<repo>` | your GitHub repository name |

## What is in the repository

| File | Where it ends up | Purpose |
|---|---|---|
| `Dockerfile` | image | Python 3.12 + gunicorn, static files baked in |
| `.dockerignore` | - | keeps `.env`, `venv`, `db.sqlite3` out of the image |
| `deploy/docker-compose.yml` | `/opt/sajilokabadi/` | `api` + `postgres` services |
| `deploy/compose.sh` | `/opt/sajilokabadi/` | `docker compose` pinned to the deployed image |
| `deploy/deploy.sh` | `/opt/sajilokabadi/` | pull, migrate, swap, health check, clean up |
| `deploy/rollback.sh` | `/opt/sajilokabadi/` | redeploy the previous image |
| `deploy/backup.sh` | `/opt/sajilokabadi/` | `pg_dump` with 14-day retention |
| `deploy/nginx/sajilokabadi-api.conf` | `/etc/nginx/sites-available/` | reverse proxy for the API hostname |
| `deploy/nginx/00-default-deny.conf` | `/etc/nginx/sites-available/` | refuses every other hostname, including the bare IP |
| `deploy/env.dev.example` | template for `/opt/sajilokabadi/.env` | server secrets (never committed) |
| `.github/workflows/deploy-dev.yml` | GitHub | the pipeline |

The workflow re-uploads the compose file and scripts on every deploy, so the
repository is the source of truth. Only `.env`, `media/`, `backups/` and the
database volume are server-only.

---

## Choosing the instance

Both the API and PostgreSQL share the machine, so memory is the constraint.

| | t3.micro | **t3.small (recommended)** |
|---|---|---|
| vCPU / RAM | 2 / 1 GiB | 2 / 2 GiB |
| Mumbai on-demand (approx.) | ~$0.0112/h, ~$8/month | ~$0.0224/h, ~$16/month |
| Fits? | Tight. Ubuntu + Docker (~250 MB), PostgreSQL (~100-200 MB), 2 gunicorn workers (~150-250 MB), Nginx, plus `docker pull` spikes leave almost nothing. Works only with swap, and gets slow or OOM-kills PostgreSQL under load. | Comfortable headroom for all of it plus migrations running next to the live API during a deploy. |

**Pick t3.small.** A dev server that falls over while the frontend developer is
integrating costs more in lost time than the ~$8/month difference. You can
resize later (stop, change instance type, start) without losing data.

Region: **Asia Pacific (Mumbai) `ap-south-1`**, the closest AWS region to Nepal.

Prices here are approximate and change; confirm in the
[AWS Pricing Calculator](https://calculator.aws/). The full cost breakdown is
in step 30.

---

## 1. AWS IAM setup

Use root only for account-level tasks (billing, closing the account).

1. Sign in as root: <https://console.aws.amazon.com/>.
2. **Protect root with MFA**: top-right account name, **Security credentials**,
   **Multi-factor authentication (MFA)**, **Assign MFA device**, then an
   authenticator app (Google Authenticator, Authy, 1Password...).
3. **Let IAM users see billing**: account name, **Account**, **IAM user and
   role access to Billing information**, **Edit**, tick **Activate IAM
   Access**, **Update**.
4. **Create your everyday user**: open **IAM**, **Users**, **Create user**.
   - User name: e.g. `yourname-admin`
   - Tick **Provide user access to the AWS Management Console**, **I want to
     create an IAM user**, set a password, untick "must create a new password".
   - **Next**, **Attach policies directly**, tick **AdministratorAccess**,
     **Next**, **Create user**.
   - Save the **Console sign-in URL** (`https://<account-id>.signin.aws.amazon.com/console`).
5. Sign out, sign in with that URL as `yourname-admin`.
6. Add MFA to this user as well: **IAM**, **Users**, `yourname-admin`,
   **Security credentials**, **Assign MFA device**.
7. **Budget alert** (strongly recommended): **Billing and Cost Management**,
   **Budgets**, **Create budget**, **Use a template**, **Monthly cost budget**,
   amount `30` USD, your email. You get an email before the bill surprises you.

Use `yourname-admin` for everything below.

## 2. Create the EC2 instance

1. Top-right region selector: **Asia Pacific (Mumbai) ap-south-1**.
2. **EC2**, **Instances**, **Launch instances**.
3. **Name**: `sajilokabadi-dev`.
4. **Application and OS Images**: **Ubuntu**, **Ubuntu Server 24.04 LTS (HVM),
   SSD Volume Type**, architecture **64-bit (x86)**.
5. **Instance type**: `t3.small`.
6. **Key pair**: **Create new key pair**, name `sajilokabadi-dev`, type
   **ED25519**, format **.pem**, **Create**. The `.pem` downloads once; keep it
   safe (e.g. `C:\Users\<you>\.ssh\sajilokabadi-dev.pem`). This is **your**
   admin key; GitHub gets a separate key in step 21.
7. **Network settings**, **Edit**:
   - VPC: default. Subnet: no preference. **Auto-assign public IP: Enable**
     (only used until the Elastic IP is attached).
   - **Create security group**, name `sajilokabadi-dev-sg`. Rules are set in step 3.
8. **Configure storage**: `25` GiB, **gp3**.
9. **Advanced details**:
   - **Termination protection**: **Enable** (stops an accidental "Terminate"
     from deleting the database disk).
   - **Credit specification**: **Standard**. T3 defaults to "Unlimited", which
     bills extra if CPU stays high; Standard caps it at the free baseline.
10. **Launch instance**.

## 3. Configure the security group

**EC2**, **Security Groups**, `sajilokabadi-dev-sg`, **Inbound rules**, **Edit inbound rules**:

| Type | Port | Source | Why |
|---|---|---|---|
| SSH | 22 | see below | admin + GitHub Actions deploys |
| HTTP | 80 | `0.0.0.0/0` | Let's Encrypt validation and redirect to HTTPS |
| HTTPS | 443 | `0.0.0.0/0` | the API |

**Do not add 8000 or 5432.** 8000 is gunicorn, which should only be reached
through Nginx (TLS, request limits, real client IP). 5432 is the database;
the API reaches it over the internal Docker network, and nothing else should.
Both are also bound so they could not be reached even if you added the rules
(8000 on `127.0.0.1` only, 5432 not published at all), but the security group
is the first line of defence.

**About SSH and "my IP only".** GitHub Actions deploys over SSH from GitHub's
runners, whose IP addresses change on every run and cannot be listed in a
security group. So you have to choose:

- **Recommended for this dev setup:** source `0.0.0.0/0`, protected by
  key-only login (Ubuntu on EC2 has password login disabled by default). Bots
  will knock on port 22; without a key they cannot get in.
- **Stricter, more setup:** source **My IP** only, and let the workflow add
  the runner's IP to the security group at the start of each deploy and
  remove it at the end. That needs AWS credentials in GitHub (an OIDC role).
  Worth doing before this server holds anything important; not needed to start.

Outbound rules: leave the default (all traffic).

## 4. Allocate and attach an Elastic IP

A normal public IP changes whenever the instance stops. DNS needs a fixed one.

1. **EC2**, **Elastic IPs**, **Allocate Elastic IP address**, **Allocate**.
2. Select it, **Actions**, **Associate Elastic IP address**, **Instance**
   `sajilokabadi-dev`, **Associate**.
3. Note the address; this is `<EIP>`.

## 5. SSH into the instance

From PowerShell on Windows (fix the key's permissions once, or SSH refuses it):

```powershell
icacls C:\Users\<you>\.ssh\sajilokabadi-dev.pem /inheritance:r
icacls C:\Users\<you>\.ssh\sajilokabadi-dev.pem /grant:r "$($env:USERNAME):(R)"
ssh -i C:\Users\<you>\.ssh\sajilokabadi-dev.pem ubuntu@<EIP>
```

On the server, update and add 2 GB of swap (a safety net for memory spikes):

```bash
sudo apt-get update && sudo apt-get -y upgrade
sudo timedatectl set-timezone Asia/Kathmandu

sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

If `upgrade` mentions a new kernel, `sudo reboot` and SSH in again.

## 6. Install Docker

Docker's official repository (Ubuntu's own `docker.io` package lags behind):

```bash
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Cap container log size so logs cannot fill the disk:

```bash
echo '{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "3" } }' \
  | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker
sudo systemctl enable docker containerd
```

Let `ubuntu` run Docker without sudo, then log out and back in:

```bash
sudo usermod -aG docker ubuntu
exit
```

```powershell
ssh -i C:\Users\<you>\.ssh\sajilokabadi-dev.pem ubuntu@<EIP>
```

```bash
docker run --rm hello-world
```

Note: being in the `docker` group is equivalent to root on this machine. That
is fine for a single-purpose dev server; it is also why the GitHub deploy key
must be treated like a root key.

## 7. Install Docker Compose

Already installed as the `docker-compose-plugin` in step 6. Check:

```bash
docker compose version   # v2.x; the scripts need 2.17 or newer
```

Use `docker compose` (with a space). The old `docker-compose` Python tool is
not used.

## 8. Create the deployment directory

```bash
sudo mkdir -p /opt/sajilokabadi
sudo chown ubuntu:ubuntu /opt/sajilokabadi
mkdir -p /opt/sajilokabadi/media /opt/sajilokabadi/backups
chmod 700 /opt/sajilokabadi/backups
```

## 9. PostgreSQL Docker configuration

The compose file is `deploy/docker-compose.yml`. Copy the deploy files from
your PC (PowerShell, from the project folder):

```powershell
cd C:\Users\HP\OneDrive\Desktop\sajilokabadi
scp -i C:\Users\<you>\.ssh\sajilokabadi-dev.pem deploy/docker-compose.yml deploy/compose.sh deploy/deploy.sh deploy/rollback.sh deploy/backup.sh deploy/env.dev.example ubuntu@<EIP>:/opt/sajilokabadi/
scp -i C:\Users\<you>\.ssh\sajilokabadi-dev.pem deploy/nginx/sajilokabadi-api.conf deploy/nginx/00-default-deny.conf ubuntu@<EIP>:/tmp/
```

On the server:

```bash
cd /opt/sajilokabadi
chmod +x *.sh
sed -i 's/\r$//' *.sh docker-compose.yml   # only matters if the files picked up Windows line endings
```

What the `postgres` service does:

- `image: postgres:16-alpine`, container `sajilokabadi-postgres`,
  `restart: unless-stopped`.
- Gets only `POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD`,
  interpolated from `.env`.
- **No `ports:` section**, so nothing outside Docker can reach it.
- Data in the named volume `sajilokabadi_postgres_data`, mounted at
  `/var/lib/postgresql/data`. Volumes live under `/var/lib/docker/volumes/` on
  the EBS disk and survive container removal, image changes, redeploys,
  `docker compose down`, stop/start and reboots. The only things that delete
  it are `docker compose down -v`, `docker volume rm`/`prune`, or terminating
  the instance. None of the scripts ever do that.
- A `pg_isready` healthcheck; the API waits for it before starting.

**How Docker Compose networking works here.** Compose creates a private
network (`sajilokabadi_backend`) and attaches both containers. On that
network each service is reachable **by its service name**: inside the API
container, `postgres` resolves to the database container's private IP. That
is why `DATABASE_URL` uses `@postgres:5432`, not `localhost` (which inside a
container means the container itself). A published port (`ports:`) is a
separate thing: it opens a port on the **host**. PostgreSQL has none; the API
publishes 8000 on the host's `127.0.0.1` only, so Nginx on the host can reach
it and the internet cannot.

## 10. API Docker configuration

The `api` service in the same compose file:

- `image: ${API_IMAGE}`: an exact tag such as
  `ghcr.io/<github-username>/sajilokabadi-api:develop-a1b2c3d`. `deploy.sh`
  sets it and records it in `.current_image`. Use `./compose.sh` (not bare
  `docker compose`) for manual commands so this is filled in.
- `env_file: .env`, `restart: unless-stopped`,
  `depends_on: postgres (service_healthy)`.
- `ports: "127.0.0.1:8000:8000"`: loopback only.
- `./media:/app/media`: uploaded avatars, served by Nginx directly.
- Healthcheck: `GET http://127.0.0.1:8000/health/` inside the container.
  `/health/` returns `200 {"status": "ok"}` only when the database answers.

The image itself (`Dockerfile`): Python 3.12 slim, runs as a non-root user
with uid 1000 (same as `ubuntu`, so `media/` permissions just work), gunicorn
with 2 workers x 4 threads, `DJANGO_SETTINGS_MODULE=config.settings.prod`
(DEBUG off, HTTPS redirect, trusts Nginx's `X-Forwarded-Proto`).

## 11. Create `.env`

```bash
cd /opt/sajilokabadi
cp env.dev.example .env
PG_PASS=$(openssl rand -hex 24)
SECRET=$(openssl rand -base64 48 | tr -d '\n=/+')
sed -i "s|<generated-password>|$PG_PASS|g; s|<generated-secret-key>|$SECRET|" .env
unset PG_PASS SECRET
chmod 600 .env
nano .env
```

In `nano`: put your Aakash token in `AAKASH_SMS_AUTH_TOKEN`, and set
`OTP_TEST_PHONES` to the numbers the frontend developer will test with (they
sign in with `202610`; every other number gets a real SMS). Save with
`Ctrl+O`, `Enter`, `Ctrl+X`.

Rules:

- `.env` exists **only** here. It is in `.gitignore` and `.dockerignore`.
- The PostgreSQL password is **not** stored in GitHub; GitHub never needs it.
- `POSTGRES_PASSWORD` only takes effect the first time the volume is created.
  Changing it later needs `ALTER USER` too (see Troubleshooting).

## 12. Test PostgreSQL

No API image exists yet, so give compose a placeholder value:

```bash
cd /opt/sajilokabadi
API_IMAGE=none ./compose.sh up -d --wait postgres
API_IMAGE=none ./compose.sh ps
docker exec -it sajilokabadi-postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select version();"'
docker volume inspect sajilokabadi_postgres_data --format '{{ .Mountpoint }}'
```

Prove it is not reachable from outside Docker:

```bash
sudo ss -ltnp | grep 5432 || echo "5432 not listening on the host - correct"
```

## 13. Test the API path (placeholder)

The real image arrives with the first automatic deploy (step 22). Until then,
a tiny placeholder web server stands in on `127.0.0.1:8000` so Nginx and HTTPS
can be set up and tested now:

```bash
docker run -d --name placeholder -p 127.0.0.1:8000:80 nginxdemos/hello:plain-text
curl -i http://127.0.0.1:8000/health/     # 200 from the placeholder
```

From your PC, `http://<EIP>:8000` must **not** load (times out), confirming 8000 is closed.

## 14. Install Nginx

```bash
sudo apt-get install -y nginx
sudo systemctl enable --now nginx
```

## 15. Configure the Nginx reverse proxy

```bash
HOST=api.sajilokabadi.com
sudo cp /tmp/sajilokabadi-api.conf /etc/nginx/sites-available/sajilokabadi-api
sudo ln -sf /etc/nginx/sites-available/sajilokabadi-api /etc/nginx/sites-enabled/sajilokabadi-api

# Refuse everything that is not for $HOST (bare IP, other names, scanners)
sudo cp /tmp/00-default-deny.conf /etc/nginx/sites-available/00-default-deny
sudo ln -sf /etc/nginx/sites-available/00-default-deny /etc/nginx/sites-enabled/00-default-deny
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t && sudo systemctl reload nginx
curl -i -H "Host: $HOST" http://127.0.0.1/health/     # placeholder answers through Nginx
curl -i http://127.0.0.1/health/                      # "Empty reply from server": refused
```

**Only the hostname works.** `00-default-deny` is Nginx's default server: any
request whose hostname is not `api.sajilokabadi.com`, including
`http://<EIP>` and `https://<EIP>`, has its connection closed with no
response. Django adds a second layer: `ALLOWED_HOSTS` rejects unknown
hostnames with a 400 even if a request got through.

What the config does: proxies everything to `http://127.0.0.1:8000`, passes
`Host`, `X-Forwarded-Proto` (so Django knows the request was HTTPS) and the
real client IP (overwritten, not appended, because OTP rate limits are per
IP), serves `/media/` from `/opt/sajilokabadi/media/`, limits uploads to 10 MB.

## 16. Configure DNS

At whoever hosts DNS for `sajilokabadi.com` (your registrar, Cloudflare, Route 53...),
add **one record**:

| Type | Name / Host | Value | TTL |
|---|---|---|---|
| `A` | `api` | `<EIP>` | 300 (5 min) |

- Most providers want only the part before the domain in **Name**
  (`api`); some want the full `api.sajilokabadi.com`.
- Nothing else in the `sajilokabadi.com` zone changes; the website and email
  records stay as they are.
- **Cloudflare**: set the proxy status to **DNS only** (grey cloud) so
  Let's Encrypt and your Nginx see the real traffic.
- **Route 53**: **Hosted zones**, `sajilokabadi.com`, **Create record**, name
  `api`, type `A`, value `<EIP>`, **Create records**.
- No new domain is needed; this is a subdomain of the one you own.

Check from your PC (can take a few minutes):

```powershell
nslookup api.sajilokabadi.com
```

It must print `<EIP>`. Then `http://api.sajilokabadi.com/health/` in a
browser shows the placeholder.

## 17. HTTPS with Let's Encrypt

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.sajilokabadi.com --redirect \
  -m <your-email> --agree-tos --no-eff-email
```

Certbot gets the certificate, adds `listen 443 ssl` and the certificate paths
to the site, and adds a port-80 block that redirects to HTTPS. Certificates
last 90 days; the package installs a systemd timer that renews them
automatically and reloads Nginx. Verify:

```bash
systemctl list-timers | grep certbot
sudo certbot renew --dry-run
curl -I http://api.sajilokabadi.com/health/    # 301 to https
curl -i https://api.sajilokabadi.com/health/   # 200 (placeholder)
curl -ik https://<EIP>/health/                         # handshake refused: the IP does not work
```

Let's Encrypt is free.

## 18. GitHub repository and GHCR

There is nothing to create in GHCR by hand and no separate account: the
package `ghcr.io/<github-username>/sajilokabadi-api` appears on the first
push from the workflow, using your GitHub account and the workflow's built-in
`GITHUB_TOKEN`.

Create the repository and push the code (the `develop` branch comes in step
22, so nothing deploys before the secrets exist):

1. <https://github.com/new>, name `<repo>`, **Private**, no README, **Create repository**.
2. On your PC:

```powershell
cd C:\Users\HP\OneDrive\Desktop\sajilokabadi
git status                  # .env, db.sqlite3 and venv must NOT be listed
git add -A
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<github-username>/<repo>.git
git push -u origin main
```

3. Repository **Settings**, **Actions**, **General**, **Workflow permissions**:
   **Read and write permissions**, **Save**. (The workflow also asks for
   `packages: write` explicitly.)

After the first deploy the package shows under your profile, **Packages**. It
is private by default and linked to the repository, which is what lets
`GITHUB_TOKEN` push and pull it.

## 19. GitHub Actions secrets and variables

Repository **Settings**, **Secrets and variables**, **Actions**.

**Secrets** tab, **New repository secret**:

| Secret | Value |
|---|---|
| `EC2_HOST` | `<EIP>` |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | the **private** deploy key from step 21, whole file including the `-----BEGIN/END-----` lines |

No variables are needed: the workflow checks `https://api.sajilokabadi.com/health/`
by default. (Only if the hostname ever changes, add a repository variable
`API_DOMAIN` under the **Variables** tab to override it.)

That is all. Not needed: a GHCR token (the workflow uses `GITHUB_TOKEN`),
database credentials, `SECRET_KEY`, or the Aakash token (all stay in the
server's `.env`).

## 20. The workflow `.github/workflows/deploy-dev.yml`

Already in the repository. Triggers on push to `develop` (plus a manual
**Run workflow** button). Three jobs:

1. **Test**: checkout, Python 3.12, `pip install -r requirements.txt`,
   `manage.py check`, `manage.py test` (SQLite).
2. **Build and push**: logs in to GHCR with `GITHUB_TOKEN`, builds the image,
   pushes `ghcr.io/<owner>/sajilokabadi-api:develop-<7-char-sha>` (immutable)
   and moves `:develop` to it.
3. **Deploy**: SSH to EC2, upload `docker-compose.yml` and the scripts, log
   the server in to GHCR with the short-lived `GITHUB_TOKEN` (sent over stdin,
   never on a command line), run `deploy.sh <image>`, log out again, then
   `curl https://<API_DOMAIN>/health/` from GitHub with retries. Any failure
   marks the run red and the summary says what happened.

Secrets are only passed through environment variables and stdin; GitHub
masks them in logs, and no step echoes them.

What `deploy.sh` does, in an order that keeps the API up as long as possible:

1. `docker pull` the new tag. The old API keeps serving.
2. Make sure PostgreSQL is up.
3. **Run migrations in a one-off container from the new image**
   (`compose run --rm api python manage.py migrate`). The old API is still
   serving; if migrations fail, nothing has been switched and the deploy stops.
4. Replace the API container and wait (up to 120 s) for its healthcheck.
   Downtime is the few seconds gunicorn takes to start.
5. If it never becomes healthy: print its logs, **put the previous image
   back**, fail the deploy.
6. Local `/health/` check, record `.current_image`, `.previous_image` and
   `deploy-history.log`.
7. Delete old images of this repository, keeping the newest 3 plus the
   current and previous (so rollbacks need no download), and prune dangling
   layers.

It never runs `docker compose down`, let alone `down -v`.

Migration rule this relies on: the old code keeps running for a moment after
the new migrations are applied, so migrations should be **additive** (new
tables, new nullable columns). Renames and drops go in two deploys: first
stop using the column, then remove it.

## 21. SSH access for GitHub Actions

Create a **separate** key for GitHub, so you can revoke it without touching
your own `.pem`. On your PC (PowerShell):

```powershell
ssh-keygen -t ed25519 -f $HOME\.ssh\sajilokabadi_deploy -N '""' -C "github-actions-deploy"
Get-Content $HOME\.ssh\sajilokabadi_deploy.pub
```

On the server, add the **public** key:

```bash
echo 'ssh-ed25519 AAAA...paste... github-actions-deploy' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Test it from your PC:

```powershell
ssh -i $HOME\.ssh\sajilokabadi_deploy ubuntu@<EIP> "docker ps"
```

Then copy the **private** key into the `EC2_SSH_KEY` secret (step 19):

```powershell
Get-Content $HOME\.ssh\sajilokabadi_deploy -Raw | Set-Clipboard
```

The workflow trusts the server's host key on first contact
(`ssh-keyscan`). To pin it instead, store the output of
`ssh-keyscan <EIP>` as a secret and write that to `known_hosts` in the workflow.

## 22. First automatic deployment

Free port 8000 for the real API:

```bash
docker rm -f placeholder
```

Create `develop` and push it (PowerShell):

```powershell
git checkout -b develop
git push -u origin develop
```

Watch it: repository **Actions** tab, **Deploy (dev)**. A first run takes a
few minutes (no build cache yet); later runs are faster.

## 23. Migrations

They ran automatically in step 3 of `deploy.sh`. Check, and create an admin user:

```bash
cd /opt/sajilokabadi
./compose.sh ps
./compose.sh exec api python manage.py showmigrations accounts token_blacklist
./compose.sh exec api python manage.py createsuperuser --phone_number 98XXXXXXXX
```

Admin: `https://api.sajilokabadi.com/admin/`.

To run migrations by hand (rarely needed):

```bash
./compose.sh run --rm api python manage.py migrate
```

## 24. Test `/health/`

```bash
curl -i https://api.sajilokabadi.com/health/
# HTTP/2 200 ... {"status": "ok"}
```

The workflow does the same check on every deploy and fails the run if it does not return 200.

## 25. Test from the frontend

Give the frontend developer:

- **Base URL**: `https://api.sajilokabadi.com/api/v1`
- **Swagger**: `https://api.sajilokabadi.com/api/docs/`
- **Test sign-in**: any number in `OTP_TEST_PHONES`, code `202610`.

Quick end-to-end check from any terminal:

```bash
curl -s https://api.sajilokabadi.com/api/v1/auth/otp/request/ \
  -H 'Content-Type: application/json' \
  -d '{"country_code":"+977","phone":"9800000001","role":"seller"}'
```

**CORS** matters only for code running **in a browser** (a web frontend on
`localhost:3000` / `localhost:5173`). The Flutter mobile app is not subject to
CORS. Check the browser case:

```bash
curl -si -X OPTIONS https://api.sajilokabadi.com/api/v1/auth/otp/request/ \
  -H 'Origin: http://localhost:5173' -H 'Access-Control-Request-Method: POST' \
  | grep -i access-control-allow-origin
```

To allow a real frontend URL later, edit `CORS_ALLOWED_ORIGINS` in
`/opt/sajilokabadi/.env` (comma-separated, scheme included, no trailing slash,
e.g. `http://localhost:5173,https://app-dev.sajilokabadi.com`) and restart the API:

```bash
./compose.sh up -d --no-deps --force-recreate api
```

## 26. Test a second deployment

```powershell
git commit --allow-empty -m "Test second deploy"
git push origin develop
```

After the run is green:

```bash
cat /opt/sajilokabadi/.current_image /opt/sajilokabadi/.previous_image
tail -n 5 /opt/sajilokabadi/deploy-history.log
docker volume ls | grep postgres_data          # same volume, data kept
```

## 27. Test rollback

```bash
cd /opt/sajilokabadi
./rollback.sh                     # back to .previous_image
./rollback.sh develop-a1b2c3d     # or any specific commit's tag
curl -s http://127.0.0.1:8000/health/
```

`rollback.sh` redeploys the older image **without** running migrations and
swaps `.current_image`/`.previous_image`, so running it twice goes back and
forth. The newest 3 images stay on the server; an older tag has to be
downloaded, which needs a login first:

```bash
# GitHub, Settings, Developer settings, Personal access tokens (classic), scope read:packages
echo '<token>' | docker login ghcr.io -u <github-username> --password-stdin
./rollback.sh develop-<old-sha>
docker logout ghcr.io
```

No SSH at all: in **Actions**, open an older successful **Deploy (dev)** run
and click **Re-run all jobs**; it deploys that commit again.

Rolling code back does **not** undo migrations. With additive migrations
(step 20) old code simply ignores the new tables and columns. To really undo
one: `./compose.sh exec api python manage.py migrate <app> <previous_migration>`
**before** rolling back.

The next push to `develop` deploys the new commit as usual.

## 28. Database backups

Even on dev, a lost database means lost test data and setup time.

**Nightly dump on the server** (`backup.sh`, keeps 14 days):

```bash
cd /opt/sajilokabadi
./backup.sh                  # test once
ls -lh backups/
crontab -e                   # choose nano, then add:
30 2 * * * /opt/sajilokabadi/backup.sh >> /opt/sajilokabadi/backups/backup.log 2>&1
```

That is 02:30 every night, Nepal time (step 5 set the server's timezone).

**Copy one off the server now and then** (dumps on the same disk do not
survive losing the instance):

```powershell
scp -i C:\Users\<you>\.ssh\sajilokabadi-dev.pem "ubuntu@<EIP>:/opt/sajilokabadi/backups/*.dump" C:\Users\<you>\Backups\sajilokabadi\
```

**Optional, whole-disk snapshots**: **EC2**, **Lifecycle Manager**, **Create
lifecycle policy**, target instances tagged `Name = sajilokabadi-dev`, daily,
retain 7. Snapshots are incremental and cost about $0.05/GB-month of changed
data.

**Restore** a dump:

```bash
cd /opt/sajilokabadi
./compose.sh stop api
./compose.sh exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < backups/<file>.dump
./compose.sh start api
```

## 29. Troubleshooting

Start with:

```bash
cd /opt/sajilokabadi
./compose.sh ps
./compose.sh logs --tail 100 api
./compose.sh logs --tail 50 postgres
sudo tail -n 50 /var/log/nginx/error.log
tail -n 5 deploy-history.log
df -h /  &&  free -h
```

| Symptom | Likely cause | Fix |
|---|---|---|
| Workflow fails at **Set up SSH** / `Permission denied (publickey)` | wrong `EC2_SSH_KEY`, or public key not in `authorized_keys` | redo step 21; secret must include the BEGIN/END lines |
| SSH `Connection timed out` | instance stopped, or port 22 not open to GitHub | start it; check step 3 |
| `docker: permission denied` over SSH | `ubuntu` not in the `docker` group | step 6 `usermod`, then reconnect |
| `denied` / `unauthorized` pulling from GHCR | Workflow permissions still read-only | step 18.3 |
| `API_IMAGE is not set` | bare `docker compose` used | use `./compose.sh` |
| Deploy stops at **Running migrations** | a migration failed; the old API is still running | read the log, fix, push again |
| Container never becomes healthy | usually a `.env` problem: `ImproperlyConfigured`, bad `DATABASE_URL`, `DisallowedHost` | `./compose.sh logs api`; `ALLOWED_HOSTS` must contain the domain **and** `127.0.0.1` |
| `ImproperlyConfigured: OTP_TEST_CODE in production requires OTP_TEST_PHONES` | test code without a phone list | set `OTP_TEST_PHONES` or blank `OTP_TEST_CODE` |
| `password authentication failed for user` | `POSTGRES_PASSWORD` changed after the volume was created | put the old password back, or `docker exec -it sajilokabadi-postgres psql -U sajilokabadi -c "ALTER USER sajilokabadi PASSWORD '<new>';"` and update `DATABASE_URL` |
| 502 Bad Gateway | API container down or restarting | `./compose.sh ps`, logs |
| "Empty reply" / TLS handshake error | request did not use `api.sajilokabadi.com` (e.g. the IP), so `00-default-deny` refused it | use the hostname; check `server_name` in `/etc/nginx/sites-available/sajilokabadi-api` |
| Redirect loop / too many redirects | `X-Forwarded-Proto` not reaching Django (e.g. Cloudflare proxy on "Flexible") | Nginx config as in step 15; Cloudflare "DNS only" |
| Public health check fails, local one OK | DNS or certificate | `nslookup`, `sudo certbot certificates`, `sudo nginx -t` |
| `certbot` challenge fails | DNS not pointing at `<EIP>` yet, or port 80 closed | steps 3 and 16 |
| Browser shows a CORS error | origin not in `CORS_ALLOWED_ORIGINS` | step 25 |
| OTP SMS never arrives | Aakash token/balance, or number is in `OTP_TEST_PHONES` | `./compose.sh logs api | grep -i sms` |
| Disk full | old images/logs | `docker system df`; `docker image prune -a` (never `docker volume prune`) |

Do **not** use `docker compose down -v`, `docker volume rm`,
`docker volume prune` or `docker system prune --volumes`. They delete the database.

Note on the unused apps (sellers, pickups, ...): their code is empty but
their `0001_initial` migrations still exist, so `migrate` creates their
(empty) tables on a fresh database. Harmless; tidy up when those apps are
rebuilt.

## 30. Costs and saving money

Approximate Mumbai (`ap-south-1`) prices, USD; check the
[Pricing Calculator](https://calculator.aws/) for current numbers.

| Resource | Charged for | Approx. per month |
|---|---|---|
| EC2 t3.small | running hours ($0.0224/h) | ~$16.4 if 24/7 |
| EBS gp3 25 GB | provisioned size, running or stopped | ~$2.3 |
| Public IPv4 / Elastic IP | every hour it exists, attached or not ($0.005/h) | ~$3.7 |
| Data transfer out | beyond 100 GB/month free (all of AWS) | ~$0 for dev |
| Data transfer in (image pulls) | free | $0 |
| EBS snapshots (optional) | changed data stored | cents |
| **Total, 24/7** | | **~$22-23** |
| Stopped all month | EBS + IPv4 only | ~$6 |
| Weekday office hours only (~220 h) | | ~$11 |

Outside AWS:

- **Domain/DNS**: you already own the domain. A record at your existing DNS
  provider is free. (Route 53 hosted zone, only if you use it: $0.50/month.)
- **Let's Encrypt**: free.
- **GHCR**: storage and transfer for container images are currently free,
  also for private packages; GitHub has said it will give notice before
  that changes. Each image is roughly 150-250 MB. Old versions can be
  deleted under **Packages**, `sajilokabadi-api`, **Package settings**, or
  with the `actions/delete-package-versions` action.
- **GitHub Actions**: private repositories on the Free plan get 2,000
  minutes/month; one deploy uses about 3-5.

Free tier: accounts created after 15 July 2025 get sign-up credits instead of
the old "750 hours of t2/t3.micro"; older accounts may still have the
12-month free tier. Check **Billing**, **Free Tier**. t3.small is not covered
either way.

### Stop the instance when nobody is developing?

Yes, it roughly halves the bill. What happens:

- **Stop**: the EBS disk is kept, so **the Docker volume and all database data
  survive**, as do `.env`, images, certificates and backups. The Elastic IP
  stays attached, so DNS keeps working when it starts again. You keep paying
  for EBS and the IPv4 address.
- **Start**: Docker starts at boot and both containers come back by
  themselves (`restart: unless-stopped`); Nginx starts too. Give it a minute,
  then check `/health/`.
- **Terminate**: deletes the disk and **the database with it**. Termination
  protection (step 2) guards against doing this by accident.
- While stopped, pushes to `develop` fail at the SSH step. Start the instance
  and use **Re-run jobs**.

Stop/start: **EC2**, **Instances**, select `sajilokabadi-dev`,
**Instance state**, **Stop instance** / **Start instance**.

Other savings:

- Keep **Credit specification: Standard** (step 2) so a runaway process
  cannot run up "Unlimited" CPU charges.
- Do not leave extra Elastic IPs allocated; each costs ~$3.7/month even unused.
- If the server is idle most of the day, the AWS **Instance Scheduler** or a
  simple **EventBridge Scheduler** rule can stop it at night; that is optional.
- Resize to t3.micro later only if memory graphs in CloudWatch show lots of headroom.
