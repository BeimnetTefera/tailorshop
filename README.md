# Tailor Shop — Django web app

A mobile-first web app for a habesha-kemis tailoring shop, built from the Figma mockups.
It runs in any browser (phone or desktop) and is backed by Django.

## What it does

| Mockup screen | URL | Notes |
|---|---|---|
| Home | `/` | Today's priority, quick actions, production counts, current work, low stock, activity |
| New order (4 steps) | `/orders/new/` | Customer, clothing, measurements, delivery, payment with live remaining balance |
| Orders (current / past) | `/orders/` | Search, filters, swipe right = ready, swipe left = edit |
| Production tracker + transfer | `/tracker/<id>/` | Timeline, current holder, transfer to a worker, stage notes, record payments |
| Record sale | `/sales/new/` | Free-size sale with live summary; stock goes down automatically |
| Sales history | `/sales/` | Week picker, today's totals, search, sort, mark pending as paid |
| Finance + week detail | `/finance/`, `/finance/income/` | Weekly income bars, change vs last week, money still to collect |
| Worker payments | `/payments/` | Finished tasks per week, filter by worker, mark as paid |
| Inventory: clothing, filter, add style, style detail | `/inventory/` | "Use this style" opens a new order with the style chosen |
| Raw materials, add stock, use material | `/inventory/materials/` | Low / out-of-stock counts, sort sheet |
| Tibebe | `/inventory/tibebe/` | Border designs by width |
| Team (workers) | `/team/` | Add cutters, tailors, menders, etc. |

How the pieces connect: transferring a garment to a worker moves the order to that
worker's stage and opens a **task** for them. When the garment moves on (another
transfer, or "Mark ready"), the task is closed and appears in **Worker payments**.
Deposits and balance payments, plus paid free-size sales, make up **Finance**.

## Run it locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo         # optional demo data
python manage.py runserver
```

Open http://127.0.0.1:8000 and sign in as **selam / selam1234** (demo owner, also an admin).
Without demo data, create your own login with `python manage.py createsuperuser`.
The Django admin is at `/admin/`.

Run the tests with `python manage.py test shop`.

## Project layout

```
config/            settings, root URLs
shop/models.py     Order, Customer, Worker, WorkerTask, Payment, Style, Material,
                   Tibebe, FreeSizeItem, Sale, StageNote, Activity
shop/forms.py      validation (Ethiopian phone numbers, deposit ≤ total, no overselling)
shop/views.py      all screens
shop/templates/    one template per screen; bottom sheets use <dialog>
shop/static/       app.css (design tokens from the mockups), app.js (sheets, swipe, live totals)
shop/management/commands/seed_demo.py
```

## Going to production

Set these environment variables, then run `python manage.py collectstatic`:

```
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<a long random string>
DJANGO_ALLOWED_HOSTS=yourshop.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://yourshop.example.com
```

Serve with gunicorn (`gunicorn config.wsgi`) behind nginx, and let nginx serve
`/static/` (from `staticfiles/`) and `/media/` (uploaded photos). SQLite is fine for
one shop; switch `DATABASES` to PostgreSQL if several branches will use it.

## Ideas for next steps

- Amharic translations (Django i18n is already on) and Ethiopian-calendar dates
- SMS to customers when an order is ready
- Separate logins for workers so they can update their own stage
- Telebirr / CBE Birr payment references on payments
