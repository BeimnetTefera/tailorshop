import calendar
import mimetypes
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    AddStockForm,
    FreeSizeItemForm,
    MaterialForm,
    MessengerCreateForm,
    MessengerEditForm,
    NoteForm,
    OrderForm,
    PaymentForm,
    SaleForm,
    SetPasswordForm,
    StageForm,
    StyleForm,
    TibebeForm,
    TransferForm,
    UseMaterialForm,
    WorkerForm,
)
from .models import (
    WORK_STAGES,
    Activity,
    Category,
    FreeSizeItem,
    Material,
    MaterialUsage,
    Order,
    Payment,
    Sale,
    StaffProfile,
    Stage,
    StageNote,
    Style,
    Tibebe,
    Worker,
    WorkerTask,
    plain_number,
)
from .roles import owner_required
from .templatetags.shop_extras import format_etb

# --------------------------------------------------------------------------- helpers


def _today():
    return timezone.localdate()


def _range_label(start, end):
    if start.year != end.year:
        return f"{start:%b} {start.day}, {start.year} – {end:%b} {end.day}, {end.year}"
    if start.month != end.month:
        return f"{start:%b} {start.day} – {end:%b} {end.day}, {end.year}"
    return f"{start:%b} {start.day}–{end.day}, {end.year}"


def _week(request):
    """Monday–Sunday week chosen with ?week=YYYY-MM-DD (defaults to this week)."""
    today = _today()
    try:
        anchor = date.fromisoformat(request.GET.get("week", ""))
    except ValueError:
        anchor = today
    start = anchor - timedelta(days=anchor.weekday())
    end = start + timedelta(days=6)
    return {
        "start": start,
        "end": end,
        "label": _range_label(start, end),
        "prev": (start - timedelta(days=7)).isoformat(),
        "next": (start + timedelta(days=7)).isoformat(),
        "is_current": start <= today <= end,
    }


def _redirect_back(request, fallback, *args, **kwargs):
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(target)
    return redirect(fallback, *args, **kwargs)


def _author(request):
    return request.user.get_full_name() or request.user.get_username()


def _order_search(q):
    query = (
        Q(customer__name__icontains=q)
        | Q(customer__phone__icontains=q)
        | Q(style__name__icontains=q)
        | Q(style__code__icontains=q)
    )
    digits = q.upper().removeprefix("ORD-").lstrip("0")
    if digits.isdigit():
        query |= Q(pk=int(digits))
    return query


def _income(start, end):
    """Money received between two dates: order payments + paid free-size sales."""
    payments = Payment.objects.filter(paid_on__range=(start, end))
    sales = Sale.objects.filter(status=Sale.Status.PAID, created_at__date__range=(start, end))
    total = (payments.aggregate(t=Sum("amount"))["t"] or Decimal("0")) + (
        sales.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    )
    return total, payments.count() + sales.count()


def _set_stage(order, stage, *, close_tasks=False):
    """Move an order to a stage, closing open worker tasks when it leaves their hands."""
    today = _today()
    if close_tasks or stage in (Stage.READY, Stage.DELIVERED):
        WorkerTask.objects.filter(order=order, finished_on__isnull=True).update(finished_on=today)
    if stage in (Stage.READY, Stage.DELIVERED):
        order.current_worker = None
    order.stage = stage
    order.stage_started_at = timezone.now()
    order.delivered_at = today if stage == Stage.DELIVERED else None
    order.save()


def _simple_form(request, form_class, *, title, back, submit, success, instance=None, initial=None, intro=""):
    if request.method == "POST":
        form = form_class(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f"Saved {obj}.")
            return redirect(success(obj))
    else:
        form = form_class(instance=instance, initial=initial)
    return render(request, "shop/simple_form.html", {
        "form": form, "title": title, "back": back, "submit": submit, "intro": intro,
    })


# --------------------------------------------------------------------------- home


def dashboard(request):
    today = _today()
    hour = timezone.localtime().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"

    active = Order.objects.exclude(stage=Stage.DELIVERED).select_related("customer", "style", "current_worker")
    due_today = active.filter(due_date=today)
    labels = dict(Category.choices)
    breakdown = [
        f"{row['n']} {labels[row['category']].lower()}"
        for row in due_today.values("category").annotate(n=Count("id")).order_by("-n")
    ]
    stage_counts = {r["stage"]: r["n"] for r in active.values("stage").annotate(n=Count("id")).order_by()}

    return render(request, "shop/dashboard.html", {
        "greeting": greeting,
        "due_today_count": due_today.count(),
        "due_today_text": ", ".join(breakdown),
        "delayed_count": active.filter(due_date__lt=today).exclude(stage=Stage.READY).count(),
        "tracker": [(s.value, s.label, stage_counts.get(s.value, 0)) for s in WORK_STAGES],
        "ready_count": stage_counts.get(Stage.READY, 0),
        "current_work": active.filter(current_worker__isnull=False).order_by("due_date")[:4],
        "stock": FreeSizeItem.objects.order_by("quantity", "code")[:3],
        "activities": Activity.objects.all()[:5],
    })


def media_file(request, path):
    """Uploaded photos, for signed-in users only (from disk or Supabase Storage)."""
    if not default_storage.exists(path):
        raise Http404
    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    response = FileResponse(default_storage.open(path), content_type=content_type)
    response["Cache-Control"] = "private, max-age=86400"
    return response


# --------------------------------------------------------------------------- accounts


def account(request):
    return render(request, "shop/account.html")


def _messengers():
    return (get_user_model().objects.filter(profile__role=StaffProfile.Role.MESSENGER, is_superuser=False)
            .select_related("profile"))


@owner_required
def messenger_list(request):
    if request.method == "POST":
        form = MessengerCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            Activity.log(f"Messenger account added · {user.first_name}")
            messages.success(request, f"{user.first_name} can now sign in as “{user.username}”.")
            return redirect("shop:messenger_list")
    else:
        form = MessengerCreateForm()
    users = _messengers().order_by("-is_active", "first_name")
    return render(request, "shop/messengers.html", {"form": form, "messengers": users})


@owner_required
def messenger_edit(request, pk):
    user = get_object_or_404(_messengers(), pk=pk)
    form = MessengerEditForm(initial={"name": user.first_name, "phone": user.profile.phone, "is_active": user.is_active})
    password_form = SetPasswordForm(user)
    if request.method == "POST" and "password" in request.POST:
        password_form = SetPasswordForm(user, request.POST)
        if password_form.is_valid():
            user.set_password(password_form.cleaned_data["password"])
            user.save(update_fields=["password"])
            messages.success(request, f"New password saved for {user.first_name}. Give it to them in person.")
            return redirect("shop:messenger_list")
    elif request.method == "POST":
        form = MessengerEditForm(request.POST)
        if form.is_valid():
            was_active = user.is_active
            user.first_name = form.cleaned_data["name"].strip()
            user.is_active = form.cleaned_data["is_active"]
            user.save(update_fields=["first_name", "is_active"])
            user.profile.phone = form.cleaned_data["phone"]
            user.profile.save(update_fields=["phone"])
            if was_active and not user.is_active:
                Activity.log(f"Messenger account switched off · {user.first_name}")
                messages.success(request, f"{user.first_name} can no longer sign in.")
            else:
                messages.success(request, f"Saved {user.first_name}.")
            return redirect("shop:messenger_list")
    return render(request, "shop/messenger_edit.html", {"person": user, "form": form, "password_form": password_form})


@owner_required
def team(request):
    if request.method == "POST":
        form = WorkerForm(request.POST)
        if form.is_valid():
            worker = form.save()
            messages.success(request, f"Added {worker.name} to your team.")
            return redirect("shop:team")
    else:
        form = WorkerForm()
    workers = Worker.objects.annotate(
        open_tasks=Count("tasks", filter=Q(tasks__finished_on__isnull=True))
    )
    return render(request, "shop/team.html", {"form": form, "workers": workers})


@owner_required
def worker_edit(request, pk):
    worker = get_object_or_404(Worker, pk=pk)
    return _simple_form(
        request, WorkerForm, instance=worker, title=f"Edit {worker.name}",
        back="shop:team", submit="Save changes", success=lambda w: "shop:team",
    )


# --------------------------------------------------------------------------- orders


def order_list(request):
    today = _today()
    tab = "past" if request.GET.get("tab") == "past" else "current"
    q = request.GET.get("q", "").strip()
    stage = request.GET.get("stage", "")
    due = request.GET.get("due", "")
    priority = request.GET.get("priority", "")

    base = Order.objects.select_related("customer", "style", "current_worker")
    if q:
        base = base.filter(_order_search(q))
    current = base.exclude(stage=Stage.DELIVERED)
    past = base.filter(stage=Stage.DELIVERED).order_by("-delivered_at", "-pk")

    filters = []
    if stage in Stage.values and stage != Stage.DELIVERED:
        current = current.filter(stage=stage)
        filters.append(Stage(stage).label)
    if due == "today":
        current = current.filter(due_date=today)
        filters.append("Due today")
    elif due == "late":
        current = current.filter(due_date__lt=today).exclude(stage=Stage.READY)
        filters.append("Delayed")
    if priority == "urgent":
        current = current.filter(priority=Order.Priority.URGENT)
        filters.append("Urgent")

    return render(request, "shop/orders/list.html", {
        "tab": tab,
        "q": q,
        "orders": current if tab == "current" else past,
        "current_count": current.count(),
        "past_count": past.count(),
        "filters": filters,
        "stage": stage,
        "due": due,
        "priority": priority,
        "stage_choices": [(s.value, s.label) for s in Stage if s != Stage.DELIVERED],
    })


def _order_form_page(request, form, order):
    return render(request, "shop/orders/form.html", {
        "form": form,
        "order": order,
        "style_categories": {s.pk: s.category for s in Style.objects.all()},
    })


def order_create(request):
    if request.method == "POST":
        form = OrderForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                order = form.save()
                Activity.log(f"New order · {order.customer.name} ({order.title})")
            messages.success(request, f"Created order {order.code} for {order.customer.name}.")
            return redirect("shop:tracker_detail", pk=order.pk)
    else:
        initial = {}
        style_id = request.GET.get("style", "")
        style = Style.objects.filter(pk=style_id).first() if style_id.isdigit() else None
        if style:
            initial = {"style": style, "category": style.category}
        form = OrderForm(initial=initial)
    return _order_form_page(request, form, None)


def order_edit(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    if request.method == "POST":
        form = OrderForm(request.POST, request.FILES, instance=order)
        if form.is_valid():
            form.save()
            messages.success(request, f"Saved changes to {order.code}.")
            return redirect("shop:tracker_detail", pk=order.pk)
    else:
        form = OrderForm(instance=order)
    return _order_form_page(request, form, order)


@require_POST
def order_mark_ready(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    if order.stage != Stage.READY:
        _set_stage(order, Stage.READY)
        Activity.log(f"{order.customer.name}'s order is ready for pickup")
        messages.success(request, f"{order.customer.name}'s order is marked ready.")
    return _redirect_back(request, "shop:order_list")


@require_POST
def order_deliver(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    _set_stage(order, Stage.DELIVERED)
    Activity.log(f"{order.customer.name}'s order delivered")
    msg = f"Delivered {order.code}."
    if order.balance > 0:
        msg += f" {format_etb(order.balance)} ETB is still unpaid."
    messages.success(request, msg)
    return _redirect_back(request, "shop:order_list")


# --------------------------------------------------------------------------- production tracker


def tracker(request, pk=None):
    q = request.GET.get("q", "").strip()
    active = Order.objects.exclude(stage=Stage.DELIVERED).select_related("customer", "style", "current_worker")
    results = list(active.filter(_order_search(q))[:20]) if q else []

    if pk is not None:
        order = get_object_or_404(Order.objects.select_related("customer", "style", "current_worker"), pk=pk)
    elif q:
        order = results[0] if len(results) == 1 else None
    else:
        order = active.filter(current_worker__isnull=False).first() or active.first()

    today = _today()
    delayed = list(active.filter(due_date__lt=today).exclude(stage=Stage.READY))
    context = {"q": q, "results": results, "order": order, "delayed": delayed}

    if order:
        workers = Worker.objects.filter(is_active=True)
        context.update({
            "timeline": order.timeline(),
            "notes": order.notes.all()[:8],
            "tasks": order.tasks.select_related("worker")[:8],
            "roles": [
                {"value": v, "label": label, "workers": [w for w in workers if w.role == v]}
                for v, label in Worker.Role.choices
            ],
            "stage_choices": Stage.choices,
            "default_finish": (today + timedelta(days=3)).isoformat(),
        })
    return render(request, "shop/tracker.html", context)


@require_POST
def order_transfer(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    form = TransferForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Pick the worker who should receive this garment.")
        return redirect("shop:tracker_detail", pk=pk)
    worker = form.cleaned_data["worker"]
    with transaction.atomic():
        _set_stage(order, worker.role, close_tasks=True)
        order.current_worker = worker
        if form.cleaned_data.get("expected_finish"):
            order.expected_finish = form.cleaned_data["expected_finish"]
        order.save(update_fields=["current_worker", "expected_finish"])
        WorkerTask.objects.create(worker=worker, order=order, stage=worker.role, amount=worker.rate_per_task)
        if form.cleaned_data["note"]:
            StageNote.objects.create(order=order, author=f"{_author(request)} → {worker.name}", text=form.cleaned_data["note"])
        Activity.log(f"{order.customer.name}'s order moved to {order.get_stage_display().lower()} · {worker.name}")
    messages.success(request, f"Transferred to {worker.name} ({worker.get_role_display().lower()}).")
    return redirect("shop:tracker_detail", pk=pk)


@require_POST
def order_update_stage(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    form = StageForm(request.POST)
    if form.is_valid() and form.cleaned_data["stage"] != order.stage:
        _set_stage(order, form.cleaned_data["stage"])
        Activity.log(f"{order.customer.name}'s order moved to {order.get_stage_display().lower()}")
        messages.success(request, f"Stage updated to {order.get_stage_display().lower()}.")
    return redirect("shop:tracker_detail", pk=pk)


@require_POST
def order_add_note(request, pk):
    order = get_object_or_404(Order, pk=pk)
    form = NoteForm(request.POST)
    if form.is_valid():
        StageNote.objects.create(order=order, author=_author(request), text=form.cleaned_data["text"])
        messages.success(request, "Note added.")
    else:
        messages.error(request, "Write a note first (up to 300 characters).")
    return redirect("shop:tracker_detail", pk=pk)


@require_POST
def order_add_payment(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    form = PaymentForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter the amount the customer paid.")
    elif form.cleaned_data["amount"] > order.balance:
        messages.error(request, f"That's more than the remaining balance of {format_etb(order.balance)} ETB.")
    else:
        Payment.objects.create(order=order, amount=form.cleaned_data["amount"], note="Balance")
        Activity.log(f"Payment recorded · {order.customer.name}")
        messages.success(request, f"Recorded {format_etb(form.cleaned_data['amount'])} ETB from {order.customer.name}.")
    return _redirect_back(request, "shop:tracker_detail", pk=pk)


# --------------------------------------------------------------------------- free-size sales


def sale_create(request):
    items = FreeSizeItem.objects.order_by("code")
    if request.method == "POST":
        form = SaleForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                item = FreeSizeItem.objects.select_for_update().get(pk=form.cleaned_data["item"].pk)
                qty = form.cleaned_data["quantity"]
                if qty <= item.quantity:
                    sale = form.save(commit=False)
                    sale.item = item
                    sale.save()
                    item.quantity -= qty
                    item.save(update_fields=["quantity"])
                    Activity.log(f"Sale recorded · {item.code}")
                    messages.success(request, f"Recorded sale of {qty} × {item.name}. {item.quantity} left.")
                    return redirect("shop:sales_history")
            form.add_error("quantity", f"Only {item.quantity} left in stock.")
    else:
        item_id = request.GET.get("item", "")
        item = items.filter(pk=item_id).first() if item_id.isdigit() else items.filter(quantity__gt=0).first()
        form = SaleForm(initial={"item": item, "quantity": 1, "amount": item.price if item else None})
    return render(request, "shop/sales/form.html", {"form": form, "items": items})


@require_POST
def sale_mark_paid(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    sale.status = Sale.Status.PAID
    sale.save(update_fields=["status"])
    messages.success(request, f"Marked {sale.item.code} sale as paid.")
    return _redirect_back(request, "shop:sales_history")


def sales_history(request):
    today = _today()
    week = _week(request)
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    sort = request.GET.get("sort", "newest")

    sales = Sale.objects.select_related("item").filter(created_at__date__range=(week["start"], week["end"]))
    if q:
        sales = sales.filter(Q(item__code__icontains=q) | Q(item__name__icontains=q) | Q(customer_name__icontains=q))
    if status in Sale.Status.values:
        sales = sales.filter(status=status)
    sales = sales.order_by({"oldest": "created_at", "amount": "-amount"}.get(sort, "-created_at"))

    days = {}
    for sale in sales:
        days.setdefault(timezone.localtime(sale.created_at).date(), []).append(sale)
    if sort == "amount":
        groups = [(None, list(sales))]
    else:
        groups = list(days.items())

    todays = Sale.objects.filter(created_at__date=today)
    return render(request, "shop/sales/history.html", {
        "week": week,
        "groups": groups,
        "q": q,
        "status": status,
        "sort": sort,
        "today_count": todays.count(),
        "today_items": todays.aggregate(n=Sum("quantity"))["n"] or 0,
        "today_received": todays.filter(status=Sale.Status.PAID).aggregate(t=Sum("amount"))["t"] or 0,
        "week_total": sum((s.amount for s in sales if s.status == Sale.Status.PAID), Decimal("0")),
    })


def freesize_list(request):
    return render(request, "shop/inventory/freesize.html", {"items": FreeSizeItem.objects.order_by("quantity", "code")})


@owner_required
def freesize_create(request):
    return _simple_form(
        request, FreeSizeItemForm, title="Add free-size item", back="shop:freesize_list",
        submit="Add item", success=lambda o: "shop:freesize_list",
        intro="Ready-made clothes you sell off the rack.",
    )


@owner_required
def freesize_edit(request, pk):
    item = get_object_or_404(FreeSizeItem, pk=pk)
    return _simple_form(
        request, FreeSizeItemForm, instance=item, title=f"Edit {item.code}", back="shop:freesize_list",
        submit="Save changes", success=lambda o: "shop:freesize_list",
    )


# --------------------------------------------------------------------------- finance


@owner_required
def finance(request):
    today = _today()
    try:
        year, month = (int(p) for p in request.GET.get("month", "").split("-"))
        first = date(year, month, 1)
    except ValueError:
        first = today.replace(day=1)
    last_day = calendar.monthrange(first.year, first.month)[1]
    last = first.replace(day=last_day)

    # The month is split into 4 weeks (W1 = 1–7, W2 = 8–14, W3 = 15–21, W4 = 22–end of month).
    weeks = []
    for n, day in enumerate((1, 8, 15, 22), start=1):
        start = first.replace(day=day)
        end = first.replace(day=day + 6) if n < 4 else last
        amount, count = _income(start, end)
        weeks.append({"label": f"W{n}", "start": start, "end": end, "amount": amount, "count": count,
                      "is_future": start > today})

    if first <= today <= last:
        idx = next(i for i, w in enumerate(weeks) if w["start"] <= today <= w["end"])
    elif first > today:
        idx = 0
    else:
        idx = len(weeks) - 1
    selected = weeks[idx]
    selected["is_selected"] = True
    if idx > 0:
        prev_amount = weeks[idx - 1]["amount"]
    else:
        prev_amount, _ = _income(selected["start"] - timedelta(days=7), selected["start"] - timedelta(days=1))
    change = round((selected["amount"] - prev_amount) / prev_amount * 100) if prev_amount else None

    peak = max((w["amount"] for w in weeks), default=0) or 1
    for w in weeks:
        w["height"] = max(4, int(w["amount"] / peak * 100))

    streak, i = 0, idx
    while i > 0 and weeks[i]["amount"] > weeks[i - 1]["amount"]:
        streak, i = streak + 1, i - 1
    if streak >= 2:
        trend = f"Your income went up each week for the last {streak} weeks."
    elif streak == 1:
        trend = "Income is up compared with the week before."
    elif change is not None and change < 0:
        trend = "Income is lower than the week before. Check unpaid balances on orders that are ready."
    else:
        trend = "Income is steady this month."

    recent = []
    for p in Payment.objects.select_related("order__customer", "order__style").filter(paid_on__range=(first, last))[:8]:
        recent.append({"name": p.order.customer.name, "detail": f"{p.order.title} · {p.order.ref}",
                       "amount": p.amount, "date": p.paid_on, "kind": p.note or "Payment"})
    for s in Sale.objects.select_related("item").filter(status=Sale.Status.PAID, created_at__date__range=(first, last))[:8]:
        recent.append({"name": s.customer_name or "Walk-in customer", "detail": f"{s.item.name} · {s.item.code}",
                       "amount": s.amount, "date": timezone.localtime(s.created_at).date(), "kind": "Sale"})
    recent.sort(key=lambda r: r["date"], reverse=True)

    open_orders = Order.objects.exclude(stage=Stage.DELIVERED).annotate(paid=Sum("payments__amount"))
    to_collect = sum((o.total_price - (o.paid or 0) for o in open_orders), Decimal("0"))
    owed_workers = WorkerTask.objects.filter(finished_on__isnull=False, paid_on__isnull=True).aggregate(t=Sum("amount"))["t"] or 0
    month_total = sum((w["amount"] for w in weeks), Decimal("0"))

    prev_month = (first - timedelta(days=1)).replace(day=1)
    next_month = last + timedelta(days=1)
    return render(request, "shop/finance/index.html", {
        "month_label": f"{first:%B %Y}",
        "is_current_month": first <= today <= last,
        "prev_month": f"{prev_month:%Y-%m}",
        "next_month": f"{next_month:%Y-%m}",
        "weeks": weeks,
        "selected": selected,
        "selected_label": _range_label(selected["start"], selected["end"]),
        "change": change,
        "change_abs": abs(change) if change is not None else None,
        "trend": trend,
        "recent": recent[:6],
        "month_total": month_total,
        "to_collect": to_collect,
        "owed_workers": owed_workers,
    })


@owner_required
def income_detail(request):
    try:
        start = date.fromisoformat(request.GET.get("start", ""))
        end = date.fromisoformat(request.GET.get("end", ""))
    except ValueError:
        week = _week(request)
        start, end = week["start"], week["end"]
    if end < start:
        start, end = end, start

    people = {}
    for row in (Payment.objects.filter(paid_on__range=(start, end))
                .values("order__customer__name").annotate(t=Sum("amount"), n=Count("id"))):
        entry = people.setdefault(row["order__customer__name"], {"amount": Decimal("0"), "count": 0})
        entry["amount"] += row["t"]
        entry["count"] += row["n"]
    for row in (Sale.objects.filter(status=Sale.Status.PAID, created_at__date__range=(start, end))
                .values("customer_name").annotate(t=Sum("amount"), n=Count("id"))):
        entry = people.setdefault(row["customer_name"] or "Walk-in sales", {"amount": Decimal("0"), "count": 0})
        entry["amount"] += row["t"]
        entry["count"] += row["n"]
    rows = sorted(people.items(), key=lambda kv: kv[1]["amount"], reverse=True)
    total, count = _income(start, end)
    return render(request, "shop/finance/income.html", {
        "label": _range_label(start, end), "rows": rows, "total": total, "count": count,
    })


# --------------------------------------------------------------------------- worker payments


@owner_required
def worker_payments(request):
    week = _week(request)
    tasks = (WorkerTask.objects.select_related("worker", "order__customer", "order__style")
             .filter(finished_on__range=(week["start"], week["end"])).order_by("paid_on", "-finished_on"))
    worker_id = request.GET.get("worker", "")
    if worker_id.isdigit():
        tasks = tasks.filter(worker_id=int(worker_id))
    stats = {
        "completed": tasks.count(),
        "unpaid": tasks.filter(paid_on__isnull=True).count(),
        "paid": tasks.filter(paid_on__isnull=False).count(),
        "owed": tasks.filter(paid_on__isnull=True).aggregate(t=Sum("amount"))["t"] or 0,
    }
    status = request.GET.get("status", "all")
    if status == "unpaid":
        tasks = tasks.filter(paid_on__isnull=True)
    elif status == "paid":
        tasks = tasks.filter(paid_on__isnull=False)
    in_progress = WorkerTask.objects.filter(finished_on__isnull=True).count()
    return render(request, "shop/payments.html", {
        "week": week, "tasks": tasks, "stats": stats, "status": status,
        "workers": Worker.objects.all(), "worker_id": worker_id, "in_progress": in_progress,
    })


@owner_required
@require_POST
def task_mark_paid(request, pk):
    task = get_object_or_404(WorkerTask.objects.select_related("worker"), pk=pk)
    if task.finished_on is None:
        messages.error(request, "This task isn't finished yet.")
    else:
        task.paid_on = _today()
        task.save(update_fields=["paid_on"])
        Activity.log(f"Payment recorded · {task.worker.name}")
        messages.success(request, f"Marked {task.worker.name}'s task as paid.")
    return _redirect_back(request, "shop:worker_payments")


# --------------------------------------------------------------------------- inventory: clothing styles

FABRIC_OPTIONS = ["Cotton", "Lace", "Wool", "Chiffon"]


def clothing_list(request):
    styles = Style.objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        styles = styles.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(description__icontains=q) | Q(fabric__icontains=q))
    occasions = [v for v in request.GET.getlist("occasion") if v in Category.values]
    genders = [v for v in request.GET.getlist("gender") if v in Style.Gender.values]
    fabrics = [v for v in request.GET.getlist("fabric") if v in FABRIC_OPTIONS]
    quick = [v for v in request.GET.getlist("quick") if v in ("popular", "recent")]
    if occasions:
        styles = styles.filter(category__in=occasions)
    if genders:
        styles = styles.filter(gender__in=genders)
    if fabrics:
        fabric_q = Q()
        for f in fabrics:
            fabric_q |= Q(fabric__icontains=f)
        styles = styles.filter(fabric_q)
    if "popular" in quick:
        styles = styles.filter(is_popular=True)
    if "recent" in quick:
        styles = styles.order_by("-created_at")
    return render(request, "shop/inventory/clothing.html", {
        "styles": styles,
        "q": q,
        "filter_count": len(occasions) + len(genders) + len(fabrics) + len(quick),
        "occasion_options": [(v, label, v in occasions) for v, label in Category.choices],
        "gender_options": [(v, label, v in genders) for v, label in Style.Gender.choices],
        "fabric_options": [(f, f, f in fabrics) for f in FABRIC_OPTIONS],
        "quick_options": [("popular", "Popular", "popular" in quick), ("recent", "Recently added", "recent" in quick)],
    })


def style_detail(request, pk):
    style = get_object_or_404(Style.objects.prefetch_related("photos"), pk=pk)
    # Previous / next follow the library's order (by style code).
    codes = list(Style.objects.values_list("pk", flat=True))
    index = codes.index(style.pk)
    details = [
        ("Category", style.get_category_display()), ("For", style.get_gender_display()),
        ("Fabric", style.fabric), ("Color", style.color), ("Fit", style.fit),
        ("Dress length", style.length), ("Sleeve length", style.sleeve_length),
        ("Sizes", ", ".join(style.size_list)),
    ]
    return render(request, "shop/inventory/style_detail.html", {
        "style": style,
        "gallery": style.gallery(),
        "details": details,
        "prev_pk": codes[index - 1] if index > 0 else None,
        "next_pk": codes[index + 1] if index + 1 < len(codes) else None,
        "position": index + 1,
        "total": len(codes),
        "materials": style.materials.all(),
        "order_count": style.orders.count(),
    })


@owner_required
def style_create(request):
    return _simple_form(
        request, StyleForm, title="Add style", back="shop:clothing_list", submit="Add style",
        success=lambda s: reverse("shop:style_detail", args=[s.pk]),
    )


@owner_required
def style_edit(request, pk):
    style = get_object_or_404(Style, pk=pk)
    return _simple_form(
        request, StyleForm, instance=style, title=f"Edit {style.code}", back="shop:clothing_list",
        submit="Save changes", success=lambda s: reverse("shop:style_detail", args=[s.pk]),
    )


# --------------------------------------------------------------------------- inventory: raw materials


def material_list(request):
    materials = Material.objects.all()
    q = request.GET.get("q", "").strip()
    kind = request.GET.get("type", "")
    sort = request.GET.get("sort", "recent")
    if q:
        materials = materials.filter(Q(name__icontains=q) | Q(description__icontains=q))
    if kind in Material.Type.values:
        materials = materials.filter(material_type=kind)
    if sort == "used":
        materials = materials.annotate(n=Count("usages")).order_by("-n", "name")
    elif sort == "name":
        materials = materials.order_by("name")
    elif sort == "price":
        materials = materials.order_by("-price")
    else:
        materials = materials.order_by("-created_at")
    everything = Material.objects.all()
    return render(request, "shop/inventory/materials.html", {
        "materials": materials,
        "q": q, "kind": kind, "sort": sort,
        "types": Material.Type.choices,
        "total": everything.count(),
        "low": everything.filter(quantity__gt=0, quantity__lte=F("low_stock_at")).count(),
        "out": everything.filter(quantity__lte=0).count(),
        "sort_options": [("recent", "Recently added"), ("used", "Most used"), ("name", "Name"), ("price", "Price")],
    })


def material_detail(request, pk):
    material = get_object_or_404(Material, pk=pk)
    return render(request, "shop/inventory/material_detail.html", {
        "material": material,
        "styles": material.used_for.all(),
        "usages": material.usages.select_related("order__customer")[:8],
        "orders": Order.objects.exclude(stage=Stage.DELIVERED).select_related("customer"),
    })


@owner_required
def material_create(request):
    return _simple_form(
        request, MaterialForm, title="Add material", back="shop:material_list", submit="Add material",
        success=lambda m: reverse("shop:material_detail", args=[m.pk]),
    )


@owner_required
def material_edit(request, pk):
    material = get_object_or_404(Material, pk=pk)
    return _simple_form(
        request, MaterialForm, instance=material, title=f"Edit {material.name}", back="shop:material_list",
        submit="Save changes", success=lambda m: reverse("shop:material_detail", args=[m.pk]),
    )


@require_POST
def material_add_stock(request, pk):
    material = get_object_or_404(Material, pk=pk)
    form = AddStockForm(request.POST)
    if form.is_valid():
        material.quantity += form.cleaned_data["quantity"]
        material.save(update_fields=["quantity"])
        Activity.log(f"Stock added · {material.name}")
        messages.success(request, f"Added {plain_number(form.cleaned_data['quantity'])} {material.unit}. Now {material.availability.lower()}.")
    else:
        messages.error(request, "Enter how much stock to add.")
    return redirect("shop:material_detail", pk=pk)


@require_POST
def material_use(request, pk):
    form = UseMaterialForm(request.POST)
    with transaction.atomic():
        material = get_object_or_404(Material.objects.select_for_update(), pk=pk)
        if not form.is_valid():
            messages.error(request, "Enter how much you used.")
        elif form.cleaned_data["quantity"] > material.quantity:
            messages.error(request, f"Only {plain_number(material.quantity)} {material.unit} in stock.")
        else:
            qty, order = form.cleaned_data["quantity"], form.cleaned_data["order"]
            material.quantity -= qty
            material.save(update_fields=["quantity"])
            MaterialUsage.objects.create(material=material, quantity=qty, order=order)
            if order and order.style_id:
                material.used_for.add(order.style)
            who = f" for {order.customer.name}" if order else ""
            Activity.log(f"Used {plain_number(qty)} {material.unit} of {material.name}{who}")
            messages.success(request, f"Recorded {plain_number(qty)} {material.unit} used{who}.")
    return redirect("shop:material_detail", pk=pk)


# --------------------------------------------------------------------------- inventory: tibebe


def tibebe_list(request):
    tibebes = Tibebe.objects.select_related("material")
    q = request.GET.get("q", "").strip()
    size = request.GET.get("size", "")
    sort = request.GET.get("sort", "code")
    if q:
        tibebes = tibebes.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(occasion__icontains=q))
    if size in Tibebe.Size.values:
        tibebes = tibebes.filter(size=size)
    tibebes = tibebes.order_by({"name": "name", "recent": "-created_at"}.get(sort, "code"))
    return render(request, "shop/inventory/tibebe.html", {
        "tibebes": tibebes, "q": q, "size": size, "sort": sort, "sizes": Tibebe.Size.choices,
        "sort_options": [("code", "Code"), ("name", "Name"), ("recent", "Recently added")],
    })


def tibebe_detail(request, pk):
    return render(request, "shop/inventory/tibebe_detail.html", {"tibebe": get_object_or_404(Tibebe, pk=pk)})


@owner_required
def tibebe_create(request):
    return _simple_form(
        request, TibebeForm, title="Add tibebe style", back="shop:tibebe_list", submit="Add tibebe",
        success=lambda t: reverse("shop:tibebe_detail", args=[t.pk]),
    )


@owner_required
def tibebe_edit(request, pk):
    tibebe = get_object_or_404(Tibebe, pk=pk)
    return _simple_form(
        request, TibebeForm, instance=tibebe, title=f"Edit {tibebe.code}", back="shop:tibebe_list",
        submit="Save changes", success=lambda t: reverse("shop:tibebe_detail", args=[t.pk]),
    )
