# 📅 Attendance Portal (Mohali + multi-office)

Biometric attendance portal: Admin daily biometric report upload karta hai, agents apna
attendance dekhte hain aur regularization request bhejte hain, admin approve karta hai,
aur month-end pe **same 7-sheet Excel report** download hota hai jo September/October
2026 reports jaisa hai.

## Local run (testing ke liye)

```
cd C:\Users\GOODWILL\attendance_portal
python -m pip install -r requirements.txt
python seed.py          # aapki real October files se demo data + users
python app.py           # http://localhost:5000
```

## Logins (seed ke baad)

| Role | Username | Password |
|---|---|---|
| Super Admin | `admin` | (set on deploy — seeded `admin123` sirf fresh DB pe) |
| Admin (Mohali) | `mohali_admin` | (set on deploy) |
| Agent | `<Emp ID>` jaise `GDSM015` | `welcome123` |

⚠️ Production passwords rotate ho chuke hain. Naye deploy pe `ADMIN_PASSWORD` env se set karein, ya first login ke baad 🔑 Password page se badlein.

## Security & backups

- **Login rate limit:** ek username+IP ke liye 15 min me 5 galat try → 6th attempt 429 (block).
- **CSRF:** har POST form me `csrf_token` hidden field hota hai (auto check hota hai). Test client ke liye `app.config["TESTING"] = True` par bypass.
- **Cookies:** `HttpOnly` + `SameSite=Lax`; cloud pe `Secure` bhi (env `SESSION_COOKIE_SECURE=0` se off kar sakte hain).
- **Headers:** HSTS, `X-Frame-Options: DENY`, `X-Content-Type-Options`, CSP, Referrer-Policy.
- **Forced password change:** `users.must_change_pw = true` karne par user agla login pe password change page pe redirect ho jata hai.

### Backups (zaroori — Supabase free me automatic backup nahi)

```powershell
python backup_db.py            # cloud -> backups\portal_cloud_<date>.sql.gz
python backup_db.py --local    # local SQLite
```

- Connection string `backup_config.json` me (gitignored) ya `DATABASE_URL` env me.
- Purane 8 backups rakhe jate hain (`BACKUP_KEEP` env se badal sakte hain).
- Weekly schedule (Task Scheduler):

```powershell
schtasks /create /tn "AttendancePortalBackup" /tr "C:\Users\GOODWILL\attendance_portal\backup_weekly.bat" /sc weekly /d SUN /st 10:00
```

- Restore: `gunzip portal_cloud_*.sql.gz` → Supabase SQL editor me file chalayein (ya `psql -f`).

⚠️ Backup file me password hashes hote hain — safe jagah rakhein, public folder/WhatsApp me na bhejein.

## Free plan — isme kya kya dhyan rakhna hai

Pro plan ki zaroorat nahi. Free tier pe 3 limitations hain, teeno ka jugaad ho chuka hai:

| Limitation | Free plan | Hamara jugaad |
|---|---|---|
| **Automatic backups** nahi | Supabase free me daily backup nahi milta | `backup_db.py` + weekly Task Scheduler (Sunday 10 AM), purane 8 backups |
| **1 hafta inactive → project pause** | DB pause ho jata hai | `/healthz` endpoint + free cron (cron-job.org) daily ping |
| **15 min idle → sleep** | Pehli request 30–50 s | Acceptable; ping se kam hota hai |

### Supabase pause na ho — free cron setup (5 min)

1. **https://cron-job.org** pe free account banao
2. **Create cronjob** → URL: `https://attendance-portal-qgww.onrender.com/healthz`
3. Schedule: **every day, 09:00** (ya har 12 ghante)
4. Save

Ye ping Render ko jagata hai aur DB me `SELECT 1` chalata hai — dono active rehte hain, koi cost nahi.

### Backup ki ek copy bahar rakho

Weekly backup isi PC pe banta hai. Mahine me ek baar `backups\` folder se latest `.sql.gz` **Google Drive** (free 15 GB) ya pen drive me copy kar do — PC kharab hone pe bhi data bachega.

### Health check

```powershell
curl https://attendance-portal-qgww.onrender.com/healthz
# {"ok":true,"db":"ok"}
```

## DB password rotate karna (Supabase)

Agar DB password change karte ho to **3 jagah** update karna hota hai — warna portal 500 deta hai:

1. **Supabase** → Settings → Database → Reset database password
2. **Render** → Environment → `DATABASE_URL` (Save → auto redeploy)
3. **Local** → `backup_config.json` (gitignored)

### ⚠️ Connection string me special characters encode karo

| Character | Encode |
|---|---|
| `@` | `%40` |
| `#` | `%23` |
| `/` | `%2F` |
| `:` | `%3A` |

Example — password `adminmohaligdsf@247`:

```
postgresql://postgres.isboqwumkgdtkyeulctw:adminmohaligdsf%40247@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
```

Seedha `@` paste karne se URL galat parse hota hai aur login 500 error deta hai.

### Check kaise karein ki DB chal rahi hai

```powershell
python backup_db.py
```
Agar backup ban gaya to connection sahi hai.

## Daily workflow

1. **Admin** → Upload → month select + device `.xls` file → preview check → Confirm Import
2. **Agent** → My Attendance → kisi day pe click → Regularization request (reason ke saath)
3. **Admin** → Requests → device punch evidence dekhkar Approve/Reject
4. **Admin** → Report → month select → 7-sheet Excel download

Rules (Office settings me badle ja sakte hain):
- First IN after **10:15** = L (late)
- First IN **13:30–16:00** = H (half-day)
- Device **WOP** (weekly-off pe kaam) = **O** (comp-off present)
- Holiday pe device A = **HO** (paid off)
- **First 4 lates = Present** (waived); 5th onward = **1/6 day** deduction

## Cloud deploy (FREE — Render + Supabase)

### Step 1 — Supabase (free database)
1. supabase.com pe account banao → **New project**
2. Project Settings → Database → Connection string (URI) copy karo
   (`postgresql://postgres.****:PASSWORD@...`)

### Step 2 — GitHub
1. Is folder ko GitHub pe push karo (private repo bhi chalega):
   ```
   cd C:\Users\GOODWILL\attendance_portal
   git init && git add . && git commit -m "attendance portal"
   git branch -M main
   git remote add origin https://github.com/<aapka-user>/attendance-portal.git
   git push -u origin main
   ```

### Step 3 — Render (free hosting)
1. render.com → Sign in with GitHub → **New → Web Service** → repo select
2. Render `render.yaml` detect kar lega (ya manually):
   - Build: `pip install -r requirements.txt && pip install psycopg2-binary`
   - Start: `gunicorn app:app --bind 0.0.0.0:$PORT`
3. Environment variables:
   - `DATABASE_URL` = Supabase connection string
   - `SECRET_KEY` = koi lamba random text
4. Deploy → aapko URL milega jaise `https://attendance-portal.onrender.com`

### Step 4 — First time setup on cloud
1. Admin login → seed na chalana (cloud pe DB khali hai)
2. Super Admin → Offices → "MOHALI" add karo (rules default sahi hain)
3. Employees ek baar import: local `python seed.py` se ya Employees → Add
   (ya mujhse bolo — main ek "Import employees from Excel" upload page add kar dunga)
4. Users create karo (admin + agents)

## UI / design system (Aurora)
- `static/style.css` hi single source of truth hai — saare pages usi ki classes use karte hain
  (`topbar`, `card`, `stat`, `btn`, `table-wrap`, `tag`, `cal`, `req-card`, `toast`).
- Icons: `templates/base.html` me inline SVG sprite (`<use href="#i-...">`) — koi CDN/font nahi.
- Toast notifications: flash messages automatically top-right (mobile pe bottom) toasts ban jate hain.
- Lite by design: system fonts, no images, CSS-only effects; CSS gzip ke baad ~6.6 KB.
- Naya page banate waqt: `{% extends "base.html" %}`, phir `page-head` + `card` classes use karo —
  inline `style="..."` avoid karo (except one-off widths).
- UI regression check: `python _ui_check.py` — har role ke saare pages render karta hai,
  POST forms me CSRF token, aur Hinglish text detect karta hai (non-zero exit = problem).

## Notes
- Render free tier: 15 min idle ke baad pehli request 30–50 sec leti hai (cold start).
- DB backups: Supabase **free plan me automatic backups nahi hote**. Month-end Excel export + `pg_dump` backup lo (dekho AUDIT report).
- Test: `python test_smoke.py` (sare pages + approve flow + report download check karta hai).
