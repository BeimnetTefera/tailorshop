# Tailor Shop — Django web app

A mobile-first web app for a habesha-kemis tailoring shop. It runs in any phone or desktop
browser (iPhone and Android alike) and is backed by Django.

- **English by default, Amharic on a switch.** Each person picks their language with the
  አማ · EN button; it is saved on their profile (and in a cookie on the login page).
- **Ethiopian calendar everywhere.** Dates show as e.g. *ጥቅምት 6, 2019* and are picked
  with Ethiopian day / month / year menus; money reports follow Ethiopian months,
  including Pagume.
- **Two roles.** The owner sees everything and manages logins; messengers take orders,
  record money and stock, and carry garments between production steps.
- **"Velvet" look:** night plum and gold, Playfair Display / Jost with Noto Ethiopic.

## What it does

| Screen | URL | Notes |
|---|---|---|
| Home | `/` | Today's priority, quick actions, production counts, work in progress, activity |
| New order | `/orders/new/` | Customer, clothing, measurements, delivery date (Ethiopian), payment |
| Orders | `/orders/` | Search, filters, swipe right = ready, swipe left = edit |
| Order page | `/tracker/<id>/` | Steps, who has it now, hand over, payment, and an **updates thread** with photos |
| Collection: Ready-made | `/ready-made/` | Off-the-rack pieces with product pages, today's sales, record a sale (`/sales/new/`), sales history (`/sales/`) |
| Collection: Gallery | `/gallery/` | Designs customers choose for made-to-order; "Use this design" starts an order |
| Stock | `/stock/` | Raw materials by category (add / use stock); the owner manages categories at `/stock/categories/` |
| Money *(owner)* | `/money/` | Weekly income bars for an Ethiopian month, money to collect, worker pay (`/money/workers/`) |
| Team *(owner)* | `/manage/` | Messenger logins, production workers, worker payments, the owner's language and sign out |
| Account *(messenger)* | `/account/` | Language and sign out |

How the pieces connect: handing a garment to a production worker (weaver, cutter, tailor…)
moves the order to that worker's stage and opens a **task** for them. When it moves on
(another hand-over, or "Mark ready"), the task closes and shows up in **Worker payments**.
Messengers and the owner post updates on the order page, like comments on a ticket: text,
a photo, or both. Hand-overs appear in the same thread.

### Who can do what

| | Owner | Messenger |
|---|---|---|
| Orders, hand-overs, updates, customer payments | ✓ | ✓ |
| Record sales, add / use stock | ✓ | ✓ |
| Money reports, sales totals, worker pay | ✓ | – |
| Prices, gallery designs, materials and their categories, ready-made items, production workers | ✓ | – |
| Messenger logins (create, reset password, switch off) | ✓ | – |

Production workers don't log in. A messenger who leaves is switched off (untick
"Can sign in"); their past work stays in the records.

### Protected changes (PIN)

Each person has a 4–6 digit PIN (demo: **1234**). It is asked every time before:
money changes (recording a payment, marking a sale or worker pay as paid, editing
prices and pay rates), order changes (editing an order, changing its stage, mark ready,
mark delivered), account changes (adding, editing or switching off messengers,
resetting passwords or PINs) and deleting (categories, photos). Handing over a garment,
new orders, sales, stock and updates don't ask.

Setting or changing a PIN needs the sign-in password, so a phone left signed in can't
be used to make one. Five wrong PINs lock it for five minutes. The owner can clear a
messenger's PIN. If a phone is lost, **Sign out others** (Team or Account page) signs
out every other device; the data itself lives on the server, never on the phone.

## Run it locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo         # optional demo data
python manage.py runserver
```

Open http://127.0.0.1:8000 and sign in as **selam / selam1234** (owner) or
**dawit / dawit1234** (messenger). Without demo data, create the owner with
`python manage.py createsuperuser`. The Django admin is at `/admin/`.

Run the tests with `python manage.py test shop`.

## Translations

Amharic text lives in `locale/am/LC_MESSAGES/django.po`. To change a translation, edit
its `msgstr` (by hand or in [Poedit](https://poedit.net/)), then rebuild the compiled file
and commit both:

```bash
pip install polib
python scripts/compile_translations.py
```

(Django's `compilemessages` needs GNU gettext, which Windows doesn't include; the script
does the same job with polib.)

## Hosting

On Vercel the app runs from `api/index.py`. With no database configured it is a **demo**:
SQLite in `/tmp`, reloaded with demo data whenever an instance starts.

For real use, add these environment variables in Vercel (Project → Settings →
Environment Variables) and redeploy; migrations run on start-up:

```
DJANGO_SECRET_KEY=<a long random string>
DATABASE_URL=<Supabase → Connect → Transaction pooler connection string>
STORAGE_BUCKET=photos                 # a private Supabase Storage bucket
STORAGE_ENDPOINT_URL=<Supabase → Storage → Settings → S3 endpoint>
STORAGE_REGION=<the region shown there>
STORAGE_ACCESS_KEY_ID=<S3 access key>
STORAGE_SECRET_ACCESS_KEY=<S3 secret key>
```

Photos are always served through the app (`/media/…`), so only signed-in people can see them.

## Project layout

```
config/            settings, root URLs, WSGI start-up (migrate / demo data on Vercel)
shop/ethiopian.py  Ethiopian calendar: conversion, month names, formatting
shop/models.py     Order, Customer, Worker, WorkerTask, Payment, Style, Material, Tibebe,
                   FreeSizeItem, Sale, StageNote (updates), Activity, StaffProfile (roles)
shop/forms.py      validation, Ethiopian date picker, messenger accounts
shop/views.py      all screens; shop/roles.py decides what is owner-only
shop/middleware.py picks each person's language
shop/templates/    one template per screen; bottom sheets use <dialog>
shop/static/       app.css (Velvet design tokens), app.js (sheets, swipe, live totals)
locale/am/         Amharic translations
```

## Ideas for next steps

- Owner-editable production steps (add weaving, rename, reorder)
- Install to the home screen as an app (PWA) with notifications for new updates
- SMS to customers when an order is ready
- Telebirr / CBE Birr payment references on payments
