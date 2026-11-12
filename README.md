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
| Super Admin | `admin` | `admin123` |
| Admin (Mohali) | `mohali_admin` | `admin123` |
| Agent | `<Emp ID>` jaise `GDSM015` | `welcome123` |

⚠️ Deploy se pehle sab passwords change karein (Super Admin → Users → Edit).

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

## Notes
- Render free tier: 15 min idle ke baad pehli request 30–50 sec leti hai (cold start).
- DB backups: Supabase automatic + month-end Excel export = double safety.
- Test: `python test_smoke.py` (sare pages + approve flow + report download check karta hai).
