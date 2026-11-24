# Deploy LeadNest on Oracle Cloud (Always Free)

This puts LeadNest on a free Oracle Cloud server with a permanent HTTPS address such as
`https://leadnest.duckdns.org`. The server stays on 24/7, so the Google Sheet is checked every
minute and WhatsApp replies arrive instantly — no tunnel needed.

```
Internet ──► Caddy (HTTPS, free certificate) ──► LeadNest app ──► PostgreSQL
              ports 80/443 only                  API + CRM + workers   private
```

**Time:** about 45 minutes the first time. **Cost:** ₹0 on the Always Free resources
(Oracle asks for a card only to verify identity).

---

## 1. Create the Oracle Cloud account

1. Go to **https://www.oracle.com/cloud/free/** → **Start for free**.
2. Choose your **Home Region** carefully — it cannot be changed later. India West (Mumbai) or
   India South (Hyderabad) are closest; if one often shows "out of capacity", the other may not.
3. Verify email, phone and card. You stay on the free tier unless you choose to upgrade.

## 2. Create the server

**Menu → Compute → Instances → Create instance**

| Setting | Choose |
|---|---|
| Name | `leadnest` |
| Image | **Canonical Ubuntu 24.04** (or 22.04) |
| Shape | **Ampere → VM.Standard.A1.Flex**, 2 OCPU, 12 GB memory (Always Free allows up to 4 OCPU / 24 GB in total) |
| Networking | Create new virtual cloud network, **public subnet**, **Assign a public IPv4 address** ✓ |
| SSH keys | **Generate a key pair for me** → **Save private key** (keep this file safe) |

Click **Create** and copy the **Public IP address** when the instance is running.

> **"Out of capacity"?** Free Ampere servers are popular. Try again later or pick another
> availability domain. As a fallback, **VM.Standard.E2.1.Micro** (also Always Free) works for a
> small team — the setup script adds swap memory for it.

## 3. Open the web ports in Oracle's firewall

**Instance page → Subnet link → Security Lists → Default Security List → Add Ingress Rules**, twice:

| Source CIDR | IP protocol | Destination port |
|---|---|---|
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |

(SSH on port 22 is already open.)

## 4. Get a free web address

1. Go to **https://www.duckdns.org** and sign in (GitHub or Google).
2. Add a sub-domain, e.g. `leadnest` → `leadnest.duckdns.org`.
3. Put the server's **public IP** in the "current ip" box → **update ip**.

## 5. Install LeadNest on the server

From your PC (PowerShell), connect to the server — replace the key path and IP:

```powershell
ssh -i C:\path\to\ssh-key.key ubuntu@<PUBLIC_IP>
```

On the server:

```bash
git clone https://github.com/Amitdas09/LeadNest_realestate_CRM.git leadnest
cd leadnest
sh deploy/oracle-setup.sh      # installs Docker, opens ports 80/443, adds swap
exit                           # log out once so Docker permissions apply
```

> If the repository is **private**, GitHub asks for a username and a password: use a
> **personal access token** (GitHub → Settings → Developer settings → Fine-grained tokens,
> read-only access to this repo) as the password.

## 6. Add your settings and keys

Connect again and create the settings file:

```bash
ssh -i C:\path\to\ssh-key.key ubuntu@<PUBLIC_IP>
cd leadnest
cp deploy/env.production.example .env.production
nano .env.production           # set DOMAIN, POSTGRES_PASSWORD, SECRET_KEY, BUSINESS_NAME, GOOGLE_SHEET_ID, WHATSAPP_VERIFY_TOKEN
mkdir -p secrets
```

Generate the two random values on the server:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # POSTGRES_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # SECRET_KEY
```

Then, **from your PC**, copy the two secret files up (run in the `leadflow-crm` folder):

```powershell
scp -i C:\path\to\ssh-key.key secrets\google-service-account.json secrets\whatsapp.env ubuntu@<PUBLIC_IP>:~/leadnest/secrets/
```

Back on the server, let only the app read them:

```bash
sudo chown -R 10001 ~/leadnest/secrets && sudo chmod 600 ~/leadnest/secrets/*
```

> **WhatsApp token:** the token from "API Setup" expires after ~24 hours. For the live server,
> create a **permanent System User token** (Meta Business settings → Users → System users →
> Generate token, expiry *Never*, permissions `whatsapp_business_messaging` and
> `whatsapp_business_management`) and put it in `secrets/whatsapp.env`.

## 7. Start it

```bash
cd ~/leadnest
docker compose -f deploy/docker-compose.prod.yml --env-file .env.production up -d --build
```

The first build takes a few minutes.

> **Small server (E2.1.Micro, 1 GB)?** Building on the server can run out of memory. Build on your
> PC instead (Docker Desktop running, same `leadflow-crm` folder) and ship the image:
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File deploy\ship-image.ps1 -Server <PUBLIC_IP> -Key C:\path\to\ssh-key.key
> ```
>
> Then on the server start it **without** `--build`:
> `docker compose -f deploy/docker-compose.prod.yml --env-file .env.production up -d`

Then create your admin account and the demo setup:

```bash
alias lnc='docker compose -f deploy/docker-compose.prod.yml --env-file .env.production'
lnc exec -it app python -m app.cli create-admin --email you@example.com --name "Your Name"
lnc exec app python -m app.cli seed-demo          # demo properties, forms and question flows
```

Open **https://leadnest.duckdns.org** (your DOMAIN) and sign in. 🎉

## 8. Point WhatsApp at the server

```bash
lnc exec app python -m app.cli whatsapp-webhook --url https://leadnest.duckdns.org
```

You should see `HTTP 200 {"success":true}` twice. Replies from customers now go straight to the
server.

> ⚠️ **Turn off the local copy.** Once the server is live, stop LeadNest on your PC (and the
> tunnel). Two copies reading the same sheet with separate databases would each message the
> same new leads.

---

## Everyday commands (on the server)

```bash
cd ~/leadnest
alias lnc='docker compose -f deploy/docker-compose.prod.yml --env-file .env.production'

lnc ps                              # status
lnc logs -f app                     # live app logs
git pull && lnc up -d --build       # deploy the latest code from GitHub
lnc exec db pg_dump -U leadnest leadnest | gzip > backup-$(date +%F).sql.gz   # database backup
```

## Good to know

- **Always Free idle rule:** Oracle may reclaim Always Free servers that stay almost completely idle
  for a week. A CRM that checks the sheet every minute is normally not idle, but if it happens you
  can recreate the server from this guide (keep database backups). Upgrading the account to
  *Pay As You Go* removes this rule and still costs nothing while you stay within the free limits.
- **Certificates** are renewed automatically by Caddy.
- **Security:** only ports 80/443 (and SSH) are open; the database is not reachable from the
  internet; secrets live only in `.env.production` and `secrets/` on the server.
