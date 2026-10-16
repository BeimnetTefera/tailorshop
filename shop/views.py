import mimetypes
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_not_required
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop, ngettext
from django.views.decorators.http import require_POST

from . import ethiopian
from .demo import DEMO_PREFIX, demo_photo
from .forms import (
    AddStockForm,
    FreeSizeItemForm,
    MaterialCategoryForm,
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
    MaterialCategory,
    MaterialUsage,
    Order,
    Payment,
    Sale,
    StaffProfile,
    Stage,
    StageNote,
    Style,
    Worker,
    WorkerTask,
    plain_number,
)
from .pin import pin_required, token_ok
from .roles import is_owner, owner_required
from .templatetags.shop_extras import format_etb


def _birr(value):
    return f"{format_etb(value)} {_('ETB')}"


# --------------------------------------------------------------------------- helpers


def _today():
    return timezone.localdate()


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
        "label": ethiopian.format_range(start, end),
        "prev": (start - timedelta(days=7)).isoformat(),
        "next": (start + timedelta(days=7)).isoformat(),
        "is_current": start <= today <= end,
    }


def _safe_next(request):
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return None


def _redirect_back(request, fallback, *args, **kwargs):
    target = _safe_next(request)
    return redirect(target) if target else redirect(fallback, *args, **kwargs)


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
            messages.success(request, _("Saved %(name)s.") % {"name": obj})
            return redirect(success(obj))
    else:
        form = form_class(instance=instance, initial=initial)
    return render(request, "shop/simple_form.html", {
        "form": form, "title": title, "back": back, "submit": submit, "intro": intro,
        # Editing something that exists (prices, pay rates, designs) asks for the PIN; adding new doesn't.
        "protect": instance is not None,
    })


def media_file(request, path):
    """Uploaded photos, for signed-in users only (from disk or Supabase Storage)."""
    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    if path.startswith(DEMO_PREFIX):
        file = demo_photo(path)
        if file is None:
            raise Http404
        response = FileResponse(file.open("rb"), content_type=content_type)
        response["Cache-Control"] = "private, max-age=86400"
        return response
    if not default_storage.exists(path):
        raise Http404
    response = FileResponse(default_storage.open(path), content_type=content_type)
    response["Cache-Control"] = "private, max-age=86400"
    return response


@login_not_required
@require_POST
def set_language(request):
    """The አማ · EN switch. Saved on the profile when signed in, and in a cookie."""
    language = request.POST.get("language")
    if language not in dict(settings.LANGUAGES):
        language = settings.LANGUAGE_CODE
    user = request.user
    if user.is_authenticated:
        role = StaffProfile.Role.OWNER if user.is_superuser else StaffProfile.Role.MESSENGER
        profile, _created = StaffProfile.objects.get_or_create(user=user, defaults={"role": role})
        profile.language = language
        profile.save(update_fields=["language"])
    response = redirect(_safe_next(request) or ("shop:dashboard" if user.is_authenticated else "login"))
    response.set_cookie(settings.LANGUAGE_COOKIE_NAME, language, max_age=settings.LANGUAGE_COOKIE_AGE,
                        samesite="Lax", secure=request.is_secure())
    return response


# --------------------------------------------------------------------------- home


def dashboard(request):
    today = _today()
    hour = timezone.localtime().hour
    greeting = _("Good morning") if hour < 12 else _("Good afternoon") if hour < 18 else _("Good evening")

    active = Order.objects.exclude(stage=Stage.DELIVERED).select_related("customer", "style", "current_worker")
    due_today = list(active.filter(due_date=today).exclude(stage=Stage.READY))
    delayed = active.filter(due_date__lt=today).exclude(stage=Stage.READY)
    stage_counts = {r["stage"]: r["n"] for r in active.values("stage").annotate(n=Count("id")).order_by()}

    name = request.user.first_name or request.user.get_username()
    return render(request, "shop/dashboard.html", {
        "greeting": _("%(greeting)s, %(name)s") % {"greeting": greeting, "name": name},
        "date_line": ethiopian.format_date(today, "full"),
        "due_today": due_today,
        "priority_order": due_today[0] if due_today else delayed.first(),
        "delayed_count": delayed.count(),
        "tracker": [(s.value, s.label, stage_counts.get(s.value, 0)) for s in WORK_STAGES],
        "ready_count": stage_counts.get(Stage.READY, 0),
        "current_work": active.filter(current_worker__isnull=False).order_by("due_date")[:4],
        "stock": FreeSizeItem.objects.order_by("quantity", "code")[:3],
        "activities": Activity.objects.all()[:5],
    })


# --------------------------------------------------------------------------- accounts


def account(request):
    """Old address: account settings now live in the avatar menu at the top of every main screen."""
    return redirect("shop:manage" if is_owner(request.user) else "shop:dashboard")


@owner_required
def manage(request):
    """The owner's Team tab: messenger logins, production workers and their own account."""
    messengers = _messengers()
    return render(request, "shop/manage.html", {
        "messenger_count": messengers.filter(is_active=True).count(),
        "messenger_off": messengers.filter(is_active=False).count(),
        "worker_count": Worker.objects.filter(is_active=True).count(),
        "busy_workers": WorkerTask.objects.filter(finished_on__isnull=True).values("worker").distinct().count(),
        "owed": WorkerTask.objects.filter(finished_on__isnull=False, paid_on__isnull=True).aggregate(t=Sum("amount"))["t"] or 0,
    })


def _messengers():
    return (get_user_model().objects.filter(profile__role=StaffProfile.Role.MESSENGER, is_superuser=False)
            .select_related("profile"))


@owner_required
@pin_required
def messenger_list(request):
    if request.method == "POST":
        form = MessengerCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            Activity.log(gettext_noop("Messenger account added · %(name)s"), name=user.first_name)
            messages.success(request, _("%(name)s can now sign in as “%(username)s”.")
                             % {"name": user.first_name, "username": user.username})
            return redirect("shop:messenger_list")
    else:
        form = MessengerCreateForm()
    users = _messengers().order_by("-is_active", "first_name")
    return render(request, "shop/messengers.html", {"form": form, "messengers": users})


@owner_required
@pin_required
def messenger_edit(request, pk):
    user = get_object_or_404(_messengers(), pk=pk)
    form = MessengerEditForm(initial={"name": user.first_name, "phone": user.profile.phone, "is_active": user.is_active})
    password_form = SetPasswordForm(user)
    if request.method == "POST" and "reset_pin" in request.POST:
        user.profile.pin_hash = ""
        user.profile.save(update_fields=["pin_hash"])
        messages.success(request, _("%(name)s's PIN is cleared. They'll create a new one with their password.")
                         % {"name": user.first_name})
        return redirect("shop:messenger_edit", pk=user.pk)
    if request.method == "POST" and "password" in request.POST:
        password_form = SetPasswordForm(user, request.POST)
        if password_form.is_valid():
            user.set_password(password_form.cleaned_data["password"])
            user.save(update_fields=["password"])
            messages.success(request, _("New password saved for %(name)s. Give it to them in person.")
                             % {"name": user.first_name})
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
                Activity.log(gettext_noop("Messenger account switched off · %(name)s"), name=user.first_name)
                messages.success(request, _("%(name)s can no longer sign in.") % {"name": user.first_name})
            else:
                messages.success(request, _("Saved %(name)s.") % {"name": user.first_name})
            return redirect("shop:messenger_list")
    return render(request, "shop/messenger_edit.html", {"person": user, "form": form, "password_form": password_form})


@owner_required
def team(request):
    if request.method == "POST":
        form = WorkerForm(request.POST)
        if form.is_valid():
            worker = form.save()
            messages.success(request, _("Added %(name)s to your team.") % {"name": worker.name})
            return redirect("shop:team")
    else:
        form = WorkerForm()
    workers = Worker.objects.annotate(
        open_tasks=Count("tasks", filter=Q(tasks__finished_on__isnull=True))
    )
    return render(request, "shop/team.html", {"form": form, "workers": workers})


@owner_required
@pin_required
def worker_edit(request, pk):
    worker = get_object_or_404(Worker, pk=pk)
    return _simple_form(
        request, WorkerForm, instance=worker, title=_("Edit %(name)s") % {"name": worker.name},
        back="shop:team", submit=_("Save changes"), success=lambda w: "shop:team",
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
        filters.append(str(Stage(stage).label))
    if due == "today":
        current = current.filter(due_date=today)
        filters.append(_("Due today"))
    elif due == "late":
        current = current.filter(due_date__lt=today).exclude(stage=Stage.READY)
        filters.append(_("Delayed"))
    if priority == "urgent":
        current = current.filter(priority=Order.Priority.URGENT)
        filters.append(_("Urgent"))

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
                Activity.log(gettext_noop("New order · %(name)s (%(title)s)"),
                             name=order.customer.name, title=str(order.title))
            messages.success(request, _("Created order %(code)s for %(name)s.")
                             % {"code": order.code, "name": order.customer.name})
            return redirect("shop:tracker_detail", pk=order.pk)
    else:
        initial = {}
        style_id = request.GET.get("style", "")
        style = Style.objects.filter(pk=style_id).first() if style_id.isdigit() else None
        if style:
            initial = {"style": style, "category": style.category}
        form = OrderForm(initial=initial)
    return _order_form_page(request, form, None)


@pin_required
def order_edit(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    if request.method == "POST":
        form = OrderForm(request.POST, request.FILES, instance=order)
        if form.is_valid():
            form.save()
            messages.success(request, _("Saved changes to %(code)s.") % {"code": order.code})
            return redirect("shop:tracker_detail", pk=order.pk)
    else:
        form = OrderForm(instance=order)
    return _order_form_page(request, form, order)


@pin_required
@require_POST
def order_mark_ready(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    if order.stage != Stage.READY:
        _set_stage(order, Stage.READY)
        Activity.log(gettext_noop("%(name)s's order is ready for pickup"), name=order.customer.name)
        messages.success(request, _("%(name)s's order is marked ready.") % {"name": order.customer.name})
    return _redirect_back(request, "shop:order_list")


@pin_required
@require_POST
def order_deliver(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    _set_stage(order, Stage.DELIVERED)
    Activity.log(gettext_noop("%(name)s's order delivered"), name=order.customer.name)
    msg = _("Delivered %(code)s.") % {"code": order.code}
    if order.balance > 0:
        msg += " " + _("%(amount)s is still unpaid.") % {"amount": _birr(order.balance)}
    messages.success(request, msg)
    return _redirect_back(request, "shop:order_list")


# --------------------------------------------------------------------------- production tracker


def _thread(order):
    """Updates on an order, oldest first: notes and photos plus each hand-over."""
    items = [{"kind": "note", "at": n.created_at, "note": n, "owner": bool(n.user) and is_owner(n.user)}
             for n in order.notes.select_related("user", "user__profile")]
    for t in order.tasks.select_related("worker", "created_by"):
        at = t.created_at
        if timezone.localtime(at).date() != t.started_on:
            at = timezone.make_aware(datetime.combine(t.started_on, time(8)))
        items.append({"kind": "handover", "at": at, "task": t})
    items.sort(key=lambda i: i["at"])
    return items[-40:]


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
    context = {"q": q, "results": results, "order": order, "delayed": delayed, "searching": pk is None}

    if order:
        workers = Worker.objects.filter(is_active=True)
        step, steps = order.step_position()
        next_stage = order.next_stage()
        context.update({
            "timeline": order.timeline(),
            "step": step,
            "steps": steps,
            "next_stage": next_stage.label if next_stage and next_stage != Stage.DELIVERED else None,
            "next_stage_value": next_stage.value if next_stage else "",
            "thread": _thread(order),
            "roles": [
                {"value": v, "label": label, "workers": [w for w in workers if w.role == v]}
                for v, label in Worker.Role.choices
            ],
            "stage_choices": Stage.choices,
            "default_finish": today + timedelta(days=3),
            "transfer_form": TransferForm(initial={"expected_finish": today + timedelta(days=3)}),
        })
    return render(request, "shop/tracker.html", context)


@require_POST
def order_transfer(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    form = TransferForm(request.POST)
    if not form.is_valid():
        if "expected_finish" in form.errors:
            messages.error(request, form.errors["expected_finish"][0])
        else:
            messages.error(request, _("Pick the worker who should receive this garment."))
        return redirect("shop:tracker_detail", pk=pk)
    worker = form.cleaned_data["worker"]
    with transaction.atomic():
        _set_stage(order, worker.role, close_tasks=True)
        order.current_worker = worker
        if form.cleaned_data.get("expected_finish"):
            order.expected_finish = form.cleaned_data["expected_finish"]
        order.save(update_fields=["current_worker", "expected_finish"])
        WorkerTask.objects.create(worker=worker, order=order, stage=worker.role, amount=worker.rate_per_task,
                                  created_by=request.user)
        if form.cleaned_data["note"]:
            StageNote.objects.create(order=order, user=request.user, author=_author(request),
                                     text=form.cleaned_data["note"])
        Activity.log(gettext_noop("%(name)s's order moved to %(stage)s · %(worker)s"),
                     name=order.customer.name, stage=order.stage, worker=worker.name)
    messages.success(request, _("Handed over to %(name)s (%(role)s).")
                     % {"name": worker.name, "role": str(worker.get_role_display()).lower()})
    return redirect("shop:tracker_detail", pk=pk)


@pin_required
@require_POST
def order_update_stage(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    form = StageForm(request.POST)
    if form.is_valid() and form.cleaned_data["stage"] != order.stage:
        _set_stage(order, form.cleaned_data["stage"])
        Activity.log(gettext_noop("%(name)s's order moved to %(stage)s"), name=order.customer.name, stage=order.stage)
        messages.success(request, _("Stage updated to %(stage)s.") % {"stage": str(order.get_stage_display()).lower()})
    return redirect("shop:tracker_detail", pk=pk)


@require_POST
def order_add_note(request, pk):
    order = get_object_or_404(Order, pk=pk)
    form = NoteForm(request.POST, request.FILES)
    if form.is_valid():
        StageNote.objects.create(order=order, user=request.user, author=_author(request),
                                 text=form.cleaned_data["text"].strip(), photo=form.cleaned_data["photo"] or "")
        messages.success(request, _("Update posted."))
    else:
        errors = form.errors.get("photo") or form.non_field_errors() or form.errors.get("text")
        messages.error(request, errors[0] if errors else _("Write an update or add a photo."))
    return redirect(reverse("shop:tracker_detail", args=[pk]) + "#updates")


@pin_required
@require_POST
def order_add_payment(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    form = PaymentForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Enter the amount the customer paid."))
    elif form.cleaned_data["amount"] > order.balance:
        messages.error(request, _("That's more than the remaining balance of %(amount)s.")
                       % {"amount": _birr(order.balance)})
    else:
        Payment.objects.create(order=order, amount=form.cleaned_data["amount"], note=Payment.Kind.BALANCE)
        Activity.log(gettext_noop("Payment recorded · %(name)s"), name=order.customer.name)
        messages.success(request, _("Recorded %(amount)s from %(name)s.")
                         % {"amount": _birr(form.cleaned_data["amount"]), "name": order.customer.name})
    return _redirect_back(request, "shop:tracker_detail", pk=pk)


# --------------------------------------------------------------------------- ready-made clothes and sales


def readymade(request):
    today = _today()
    todays = Sale.objects.filter(created_at__date=today)
    return render(request, "shop/readymade/list.html", {
        "items": FreeSizeItem.objects.order_by("quantity", "code"),
        "today_count": todays.count(),
        "today_items": todays.aggregate(n=Sum("quantity"))["n"] or 0,
        "today_received": todays.filter(status=Sale.Status.PAID).aggregate(t=Sum("amount"))["t"] or 0,
        "pending": Sale.objects.filter(status=Sale.Status.PENDING).count(),
    })


def readymade_detail(request, pk):
    item = get_object_or_404(FreeSizeItem.objects.prefetch_related("photos"), pk=pk)
    # Previous / next follow the rack's order (by code).
    codes = list(FreeSizeItem.objects.values_list("pk", flat=True))
    index = codes.index(item.pk)
    return render(request, "shop/readymade/detail.html", {
        "item": item,
        "gallery": item.gallery(),
        "prev_pk": codes[index - 1] if index > 0 else None,
        "next_pk": codes[index + 1] if index + 1 < len(codes) else None,
        "position": index + 1,
        "total": len(codes),
        "sold": item.sales.aggregate(n=Sum("quantity"))["n"] or 0,
    })


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
                    Activity.log(gettext_noop("Sale recorded · %(code)s"), code=item.code)
                    messages.success(request, _("Recorded sale of %(qty)s × %(name)s. %(left)s left.")
                                     % {"qty": qty, "name": item.name, "left": item.quantity})
                    return redirect("shop:sales_history")
            form.add_error("quantity", _("Only %(n)s left in stock.") % {"n": item.quantity})
    else:
        item_id = request.GET.get("item", "")
        item = items.filter(pk=item_id).first() if item_id.isdigit() else items.filter(quantity__gt=0).first()
        form = SaleForm(initial={"item": item, "quantity": 1, "amount": item.price if item else None})
    return render(request, "shop/sales/form.html", {"form": form, "items": items})


@pin_required
@require_POST
def sale_mark_paid(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    sale.status = Sale.Status.PAID
    sale.save(update_fields=["status"])
    messages.success(request, _("Marked the %(code)s sale as paid.") % {"code": sale.item.code})
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


@owner_required
def freesize_create(request):
    return _simple_form(
        request, FreeSizeItemForm, title=_("Add ready-made item"), back="shop:readymade",
        submit=_("Add item"), success=lambda o: reverse("shop:readymade_detail", args=[o.pk]),
        intro=_("Ready-made clothes you sell off the rack."),
    )


@owner_required
@pin_required
def freesize_edit(request, pk):
    item = get_object_or_404(FreeSizeItem, pk=pk)
    return _simple_form(
        request, FreeSizeItemForm, instance=item, title=_("Edit %(name)s") % {"name": item.code}, back="shop:readymade",
        submit=_("Save changes"), success=lambda o: reverse("shop:readymade_detail", args=[o.pk]),
    )


# --------------------------------------------------------------------------- finance


def _month_from_request(request):
    """Ethiopian month chosen with ?month=YYYY-MM (Ethiopian year and month 1–13)."""
    current = ethiopian.today()
    try:
        year, month = (int(p) for p in request.GET.get("month", "").split("-"))
        ethiopian.to_gregorian(year, month, 1)
    except ValueError:
        year, month = current.year, current.month
    return year, month


def _month_weeks(year, month, today):
    """Weeks of an Ethiopian month: 1–7, 8–14, 15–21, 22–30. Pagume (5 or 6 days) is one week."""
    spans = [(1, ethiopian.month_length(year, month))] if month == 13 else [(1, 7), (8, 14), (15, 21), (22, 30)]
    weeks = []
    for n, (a, b) in enumerate(spans, start=1):
        start, end = ethiopian.to_gregorian(year, month, a), ethiopian.to_gregorian(year, month, b)
        amount, count = _income(start, end)
        weeks.append({"label": _("W%(n)s") % {"n": n}, "start": start, "end": end, "amount": amount,
                      "count": count, "is_future": start > today})
    return weeks


@owner_required
def finance(request):
    today = _today()
    year, month = _month_from_request(request)
    first, last = ethiopian.month_bounds(year, month)
    weeks = _month_weeks(year, month, today)

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
        prev_amount, _count = _income(selected["start"] - timedelta(days=7), selected["start"] - timedelta(days=1))
    change = round((selected["amount"] - prev_amount) / prev_amount * 100) if prev_amount else None

    peak = max((w["amount"] for w in weeks), default=0) or 1
    for w in weeks:
        w["height"] = max(4, int(w["amount"] / peak * 100))

    streak, i = 0, idx
    while i > 0 and weeks[i]["amount"] > weeks[i - 1]["amount"]:
        streak, i = streak + 1, i - 1
    if streak >= 2:
        trend = _("Your income went up each week for the last %(n)s weeks.") % {"n": streak}
    elif streak == 1:
        trend = _("Income is up compared with the week before.")
    elif change is not None and change < 0:
        trend = _("Income is lower than the week before. Check unpaid balances on orders that are ready.")
    else:
        trend = _("Income is steady this month.")

    recent = []
    for p in Payment.objects.select_related("order__customer", "order__style").filter(paid_on__range=(first, last))[:8]:
        recent.append({"name": p.order.customer.name, "detail": f"{p.order.title} · {p.order.ref}",
                       "amount": p.amount, "date": p.paid_on, "kind": p.kind_label})
    for s in Sale.objects.select_related("item").filter(status=Sale.Status.PAID, created_at__date__range=(first, last))[:8]:
        recent.append({"name": s.customer_name or _("Walk-in customer"), "detail": f"{s.item.name} · {s.item.code}",
                       "amount": s.amount, "date": timezone.localtime(s.created_at).date(), "kind": _("Sale")})
    recent.sort(key=lambda r: r["date"], reverse=True)

    open_orders = Order.objects.exclude(stage=Stage.DELIVERED).annotate(paid=Sum("payments__amount"))
    to_collect = sum((o.total_price - (o.paid or 0) for o in open_orders), Decimal("0"))
    owed_workers = WorkerTask.objects.filter(finished_on__isnull=False, paid_on__isnull=True).aggregate(t=Sum("amount"))["t"] or 0
    month_total = sum((w["amount"] for w in weeks), Decimal("0"))

    prev_year, prev_month = ethiopian.add_months(year, month, -1)
    next_year, next_month = ethiopian.add_months(year, month, 1)
    return render(request, "shop/finance/index.html", {
        "month_label": f"{ethiopian.month_name(month)} {year}",
        "is_current_month": first <= today <= last,
        "prev_month": f"{prev_year}-{prev_month}",
        "next_month": f"{next_year}-{next_month}",
        "weeks": weeks,
        "selected": selected,
        "selected_label": ethiopian.format_range(selected["start"], selected["end"]),
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
        entry = people.setdefault(row["customer_name"] or _("Walk-in sales"), {"amount": Decimal("0"), "count": 0})
        entry["amount"] += row["t"]
        entry["count"] += row["n"]
    rows = sorted(people.items(), key=lambda kv: kv[1]["amount"], reverse=True)
    total, count = _income(start, end)
    return render(request, "shop/finance/income.html", {
        "label": ethiopian.format_range(start, end), "rows": rows, "total": total, "count": count,
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
@pin_required
@require_POST
def task_mark_paid(request, pk):
    task = get_object_or_404(WorkerTask.objects.select_related("worker"), pk=pk)
    if task.finished_on is None:
        messages.error(request, _("This task isn't finished yet."))
    else:
        task.paid_on = _today()
        task.save(update_fields=["paid_on"])
        Activity.log(gettext_noop("Payment recorded · %(name)s"), name=task.worker.name)
        messages.success(request, _("Marked %(name)s's task as paid.") % {"name": task.worker.name})
    return _redirect_back(request, "shop:worker_payments")


# --------------------------------------------------------------------------- collection: design gallery

# Stored in English in the style's fabric field; labels are translated.
FABRIC_OPTIONS = ["Cotton", "Lace", "Wool", "Chiffon"]


def _fabric_label(value):
    return {"Cotton": _("Cotton"), "Lace": _("Lace"), "Wool": _("Wool"), "Chiffon": _("Chiffon")}.get(value, value)


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
    return render(request, "shop/gallery/list.html", {
        "styles": styles,
        "q": q,
        "filter_count": len(occasions) + len(genders) + len(fabrics) + len(quick),
        "occasion_options": [(v, label, v in occasions) for v, label in Category.choices],
        "gender_options": [(v, label, v in genders) for v, label in Style.Gender.choices],
        "fabric_options": [(f, _fabric_label(f), f in fabrics) for f in FABRIC_OPTIONS],
        "quick_options": [("popular", _("Popular"), "popular" in quick), ("recent", _("Recently added"), "recent" in quick)],
    })


def style_detail(request, pk):
    style = get_object_or_404(Style.objects.prefetch_related("photos"), pk=pk)
    # Previous / next follow the library's order (by style code).
    codes = list(Style.objects.values_list("pk", flat=True))
    index = codes.index(style.pk)
    details = [
        (_("For"), style.get_gender_display()), (_("Fabric"), style.fabric), (_("Color"), style.color),
        (_("Fit type"), style.fit), (_("Length"), style.length), (_("Sleeve length"), style.sleeve_length),
        (_("Sizes"), ", ".join(style.size_list)),
    ]
    details = [(label, value) for label, value in details if value]
    return render(request, "shop/gallery/detail.html", {
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
        request, StyleForm, title=_("Add design"), back="shop:clothing_list", submit=_("Add design"),
        success=lambda s: reverse("shop:style_detail", args=[s.pk]),
    )


@owner_required
@pin_required
def style_edit(request, pk):
    style = get_object_or_404(Style, pk=pk)
    return _simple_form(
        request, StyleForm, instance=style, title=_("Edit %(name)s") % {"name": style.code}, back="shop:clothing_list",
        submit=_("Save changes"), success=lambda s: reverse("shop:style_detail", args=[s.pk]),
    )


# --------------------------------------------------------------------------- stock: raw materials


def material_list(request):
    materials = Material.objects.select_related("category")
    q = request.GET.get("q", "").strip()
    cat = request.GET.get("cat", "")
    sort = request.GET.get("sort", "recent")
    if q:
        materials = materials.filter(Q(name__icontains=q) | Q(description__icontains=q))
    if cat == "none":
        materials = materials.filter(category__isnull=True)
    elif cat.isdigit():
        materials = materials.filter(category_id=int(cat))
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
        "q": q, "cat": cat, "sort": sort,
        "categories": MaterialCategory.objects.all(),
        "uncategorized": everything.filter(category__isnull=True).exists(),
        "total": everything.count(),
        "low": everything.filter(quantity__gt=0, quantity__lte=F("low_stock_at")).count(),
        "out": everything.filter(quantity__lte=0).count(),
        "sort_options": [("recent", _("Recently added")), ("used", _("Most used")), ("name", _("Name")), ("price", _("Price"))],
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
        request, MaterialForm, title=_("Add material"), back="shop:material_list", submit=_("Add material"),
        success=lambda m: reverse("shop:material_detail", args=[m.pk]),
    )


@owner_required
@pin_required
def material_edit(request, pk):
    material = get_object_or_404(Material, pk=pk)
    return _simple_form(
        request, MaterialForm, instance=material, title=_("Edit %(name)s") % {"name": material.name},
        back="shop:material_list", submit=_("Save changes"),
        success=lambda m: reverse("shop:material_detail", args=[m.pk]),
    )


@require_POST
def material_add_stock(request, pk):
    material = get_object_or_404(Material, pk=pk)
    form = AddStockForm(request.POST)
    if form.is_valid():
        material.quantity += form.cleaned_data["quantity"]
        material.save(update_fields=["quantity"])
        Activity.log(gettext_noop("Stock added · %(name)s"), name=material.name)
        messages.success(request, _("Added %(amount)s %(unit)s. Now %(status)s.") % {
            "amount": plain_number(form.cleaned_data["quantity"]),
            "unit": str(material.get_unit_display()).lower(), "status": material.availability.lower(),
        })
    else:
        messages.error(request, _("Enter how much stock to add."))
    return redirect("shop:material_detail", pk=pk)


@require_POST
def material_use(request, pk):
    form = UseMaterialForm(request.POST)
    with transaction.atomic():
        material = get_object_or_404(Material.objects.select_for_update(), pk=pk)
        unit = str(material.get_unit_display()).lower()
        if not form.is_valid():
            messages.error(request, _("Enter how much you used."))
        elif form.cleaned_data["quantity"] > material.quantity:
            messages.error(request, _("Only %(amount)s %(unit)s in stock.")
                           % {"amount": plain_number(material.quantity), "unit": unit})
        else:
            qty, order = form.cleaned_data["quantity"], form.cleaned_data["order"]
            material.quantity -= qty
            material.save(update_fields=["quantity"])
            MaterialUsage.objects.create(material=material, quantity=qty, order=order)
            if order and order.style_id:
                material.used_for.add(order.style)
            amount = plain_number(qty)
            if order:
                Activity.log(gettext_noop("Used %(amount)s %(unit)s of %(material)s for %(name)s"),
                             amount=amount, unit=material.unit, material=material.name, name=order.customer.name)
                messages.success(request, _("Recorded %(amount)s %(unit)s used for %(name)s.")
                                 % {"amount": amount, "unit": unit, "name": order.customer.name})
            else:
                Activity.log(gettext_noop("Used %(amount)s %(unit)s of %(material)s"),
                             amount=amount, unit=material.unit, material=material.name)
                messages.success(request, _("Recorded %(amount)s %(unit)s used.") % {"amount": amount, "unit": unit})
    return redirect("shop:material_detail", pk=pk)


@owner_required
def material_categories(request):
    """Add, rename and delete the groups raw materials are sorted into."""
    form = MaterialCategoryForm()
    if request.method == "POST":
        action = request.POST.get("action", "add")
        category = None
        if action in ("rename", "delete"):
            category = get_object_or_404(MaterialCategory, pk=request.POST.get("pk"))
        if action == "delete" and not token_ok(request):
            messages.error(request, _("Nothing was changed. Enter your PIN to confirm changes like this."))
            return redirect("shop:material_categories")
        if action == "delete":
            count = category.materials.count()
            name = category.label
            category.delete()
            if count:
                messages.success(request, ngettext(
                    "Deleted “%(name)s”. %(n)s material now has no category.",
                    "Deleted “%(name)s”. %(n)s materials now have no category.", count) % {"name": name, "n": count})
            else:
                messages.success(request, _("Deleted “%(name)s”.") % {"name": name})
            return redirect("shop:material_categories")
        bound = MaterialCategoryForm(request.POST, instance=category)
        if bound.is_valid():
            saved = bound.save()
            messages.success(request, (_("Renamed to “%(name)s”.") if category else _("Added “%(name)s”."))
                             % {"name": saved.label})
            return redirect("shop:material_categories")
        if category:
            messages.error(request, bound.errors.get("name", [_("Enter a name.")])[0])
        else:
            form = bound
    categories = MaterialCategory.objects.annotate(n=Count("materials"))
    return render(request, "shop/inventory/categories.html", {"form": form, "categories": categories})
