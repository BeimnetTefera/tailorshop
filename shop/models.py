"""Data model for a habesha-kemis tailoring shop.

The app covers five areas shown in the mockups:
  * custom orders and their production stages (who holds the garment now),
  * free-size ready-made stock and its sales,
  * the design gallery and raw materials (in owner-managed categories),
  * money coming in (deposits, balances, sales),
  * money going out to workers for finished tasks.

Labels are wrapped in gettext so they show in Amharic or English (locale/am).
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext, ngettext
from django.utils.translation import gettext_lazy as _


class Category(models.TextChoices):
    HABESHA = "habesha", _("Habesha kemis")
    WEDDING = "wedding", _("Wedding")
    MODERN = "modern", _("Modern")
    MEN = "men", _("Men")
    CHILDREN = "children", _("Children")
    FORMAL = "formal", _("Formal")
    HOLIDAY = "holiday", _("Holiday")


# Style-code prefixes used in the library legend (HK, WD, MN, CH, MF).
CATEGORY_PREFIX = {
    "habesha": "HK",
    "wedding": "WD",
    "modern": "MF",
    "men": "MN",
    "children": "CH",
    "formal": "HK",
    "holiday": "HK",
}


class Stage(models.TextChoices):
    CREATED = "created", _("Order created")
    MEASURED = "measured", _("Measurements taken")
    FABRIC = "fabric", _("Fabric prepared")
    CUTTING = "cutting", _("Cutting")
    SEWING = "sewing", _("Sewing")
    DECORATION = "decoration", _("Decoration")
    REPAIR = "repair", _("Repair")
    QUALITY = "quality", _("Quality check")
    READY = "ready", _("Ready for pickup")
    DELIVERED = "delivered", _("Delivered")


STAGE_SEQUENCE = list(Stage.values)
WORK_STAGES = [Stage.CUTTING, Stage.SEWING, Stage.DECORATION, Stage.REPAIR, Stage.QUALITY]


def next_code(model, prefix, field="code"):
    """Return the next free code like HK-025 for the given prefix."""
    biggest = 0
    codes = model.objects.filter(**{f"{field}__startswith": f"{prefix}-"}).values_list(field, flat=True)
    for code in codes:
        try:
            biggest = max(biggest, int(code.split("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}-{biggest + 1:03d}"


def plain_number(value):
    """Decimal('12.00') -> '12', Decimal('2.50') -> '2.5'."""
    if value is None:
        return ""
    return f"{Decimal(value).normalize():f}"


# --------------------------------------------------------------------------- people


class StaffProfile(models.Model):
    """App login details. The owner creates messenger accounts and switches them off when they leave."""

    class Role(models.TextChoices):
        OWNER = "owner", _("Owner")
        MESSENGER = "messenger", _("Messenger")

    class Language(models.TextChoices):
        AMHARIC = "am", "አማርኛ"
        ENGLISH = "en", "English"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MESSENGER)
    phone = models.CharField(max_length=20, blank=True)
    language = models.CharField(max_length=5, choices=Language.choices, default=Language.ENGLISH)
    # PIN asked before money, order, account and delete changes (see shop/pin.py).
    pin_hash = models.CharField(max_length=128, blank=True)
    pin_failures = models.PositiveSmallIntegerField(default=0)
    pin_locked_until = models.DateTimeField(null=True, blank=True)
    # Raised by "sign out all other devices"; sessions remember the value they started with.
    session_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.get_username()} ({self.get_role_display()})"


class Worker(models.Model):
    """Production workers (weaver, cutter, tailor…). They don't log in; messengers bring them the work."""

    class Role(models.TextChoices):
        # Values match Stage values so a transfer moves the order to that stage.
        CUTTING = "cutting", _("Cutter")
        SEWING = "sewing", _("Sewing")
        DECORATION = "decoration", _("Decoration specialist")
        REPAIR = "repair", _("Patch repairer")
        QUALITY = "quality", _("Quality checker")

    name = models.CharField(_("Name"), max_length=100)
    role = models.CharField(_("Role"), max_length=20, choices=Role.choices)
    phone = models.CharField(_("Phone"), max_length=20, blank=True)
    rate_per_task = models.DecimalField(
        _("Pay per task (ETB)"), max_digits=10, decimal_places=2, default=0,
        help_text=_("Default amount owed when this worker finishes a garment."),
    )
    is_active = models.BooleanField(_("Currently working here"), default=True)

    class Meta:
        ordering = ["role", "name"]

    def __str__(self):
        return self.name


class Customer(models.Model):
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, unique=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.phone})"


# --------------------------------------------------------------------------- library


class Style(models.Model):
    class Gender(models.TextChoices):
        WOMEN = "women", _("Women")
        MEN = "men", _("Men")
        CHILDREN = "children", _("Children")

    code = models.CharField(_("Style code"), max_length=20, unique=True)
    name = models.CharField(_("Style name"), max_length=120)
    category = models.CharField(_("Category"), max_length=20, choices=Category.choices, default=Category.HABESHA)
    gender = models.CharField(_("Gender"), max_length=20, choices=Gender.choices, default=Gender.WOMEN)
    fabric = models.CharField(_("Fabric"), max_length=60, blank=True, help_text=_("e.g. Cotton, Lace, Chiffon"))
    color = models.CharField(_("Color"), max_length=60, blank=True, help_text=_("e.g. White and gold"))
    fit = models.CharField(_("Fit"), max_length=60, blank=True, help_text=_("e.g. Slim fit, Loose, Flared skirt"))
    length = models.CharField(_("Dress length"), max_length=40, blank=True, help_text=_("e.g. Ankle length, 140 cm"))
    sleeve_length = models.CharField(_("Sleeve length"), max_length=40, blank=True, help_text=_("e.g. Long sleeve, 60 cm"))
    photo = models.ImageField(_("Main photo"), upload_to="styles/", blank=True)
    description = models.TextField(_("Description"), blank=True)
    recommended_sizes = models.CharField(
        _("Recommended sizes"), max_length=100, blank=True, help_text=_("Comma separated, e.g. Medium, Large")
    )
    is_popular = models.BooleanField(_("Popular style"), default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} · {self.name}"

    @property
    def size_list(self):
        return [s.strip() for s in self.recommended_sizes.split(",") if s.strip()]

    @staticmethod
    def suggest_code(category):
        return next_code(Style, CATEGORY_PREFIX.get(category, "HK"))

    def gallery(self):
        """Main photo first, then the extra angles in the order they were added."""
        images = [self.photo] if self.photo else []
        return images + [p.image for p in self.photos.all()]


class StylePhoto(models.Model):
    """Extra photos of a style (back, side, detail shots) shown in the gallery."""

    style = models.ForeignKey(Style, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="styles/more/")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"Photo of {self.style.code}"


class MaterialCategory(models.Model):
    """Groups for raw materials (fabric, thread, buttons…). The owner adds, renames and deletes them."""

    name = models.CharField(_("Name (English)"), max_length=60)
    name_am = models.CharField(_("Name (Amharic)"), max_length=60, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "material categories"

    def __str__(self):
        return self.label

    @property
    def label(self):
        """The name in the reader's language (Amharic falls back to English if not filled in)."""
        from django.utils.translation import get_language

        if (get_language() or "").startswith("am") and self.name_am:
            return self.name_am
        return self.name


class Material(models.Model):
    class Unit(models.TextChoices):
        METERS = "meters", _("Meters")
        SPOOLS = "spools", _("Spools")
        PIECES = "pieces", _("Pieces")

    name = models.CharField(_("Material name"), max_length=120)
    category = models.ForeignKey(MaterialCategory, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="materials", verbose_name=_("Category"))
    price = models.DecimalField(_("Price per unit (ETB)"), max_digits=10, decimal_places=2)
    quantity = models.DecimalField(_("Quantity"), max_digits=10, decimal_places=2, default=0)
    unit = models.CharField(_("Unit"), max_length=10, choices=Unit.choices, default=Unit.METERS)
    low_stock_at = models.DecimalField(
        _("Warn me when stock is at or below"), max_digits=10, decimal_places=2, default=5
    )
    photo = models.ImageField(_("Photo"), upload_to="materials/", blank=True)
    description = models.TextField(_("Description"), blank=True)
    used_for = models.ManyToManyField(Style, blank=True, related_name="materials")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def status(self):
        if self.quantity <= 0:
            return "out"
        if self.quantity <= self.low_stock_at:
            return "low"
        return "ok"

    @property
    def amount_label(self):
        return f"{plain_number(self.quantity)} {self.get_unit_display().lower()}"

    @property
    def availability(self):
        if self.status == "out":
            return gettext("Out of stock")
        if self.status == "low":
            return gettext("Low stock: %(amount)s") % {"amount": self.amount_label}
        return gettext("%(amount)s available") % {"amount": self.amount_label}


# --------------------------------------------------------------------------- orders


def _measure(label):
    return models.DecimalField(label, max_digits=5, decimal_places=1, null=True, blank=True)


class Order(models.Model):
    class Priority(models.TextChoices):
        STANDARD = "standard", _("Standard")
        URGENT = "urgent", _("Urgent")

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    style = models.ForeignKey(Style, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders",
                              verbose_name=_("Style"))
    category = models.CharField(_("Category"), max_length=20, choices=Category.choices, default=Category.HABESHA)
    reference_photo = models.ImageField(_("Reference photo"), upload_to="references/", blank=True)
    people_count = models.PositiveSmallIntegerField(
        _("Number of people"), default=1, help_text=_("For group orders, e.g. bride and bridesmaids.")
    )

    bust = _measure(_("Bust"))
    shoulder = _measure(_("Shoulder"))
    sleeve_length = _measure(_("Sleeve length"))
    waist = _measure(_("Waist"))
    hip = _measure(_("Hip"))
    dress_length = _measure(_("Dress length"))

    due_date = models.DateField(_("Delivery date"))
    priority = models.CharField(_("Priority"), max_length=10, choices=Priority.choices, default=Priority.STANDARD)
    total_price = models.DecimalField(_("Total price (ETB)"), max_digits=10, decimal_places=2)

    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.MEASURED)
    current_worker = models.ForeignKey(
        Worker, on_delete=models.SET_NULL, null=True, blank=True, related_name="current_orders"
    )
    stage_started_at = models.DateTimeField(default=timezone.now)
    expected_finish = models.DateField(null=True, blank=True)
    delivered_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["due_date", "pk"]

    def __str__(self):
        return f"{self.code} · {self.customer.name}"

    # ---- labels
    @property
    def code(self):
        return f"ORD-{self.pk:04d}" if self.pk else gettext("New order")

    @property
    def ref(self):
        return self.style.code if self.style_id else self.code

    @property
    def title(self):
        return self.style.name if self.style_id else self.get_category_display()

    # ---- money
    @property
    def paid_amount(self):
        return self.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")

    @property
    def balance(self):
        return self.total_price - self.paid_amount

    # ---- schedule
    @property
    def days_left(self):
        return (self.due_date - timezone.localdate()).days

    @property
    def is_active(self):
        return self.stage != Stage.DELIVERED

    @property
    def is_delayed(self):
        return self.stage not in (Stage.READY, Stage.DELIVERED) and self.days_left < 0

    @property
    def status_label(self):
        return gettext("Delayed") if self.is_delayed else self.get_stage_display()

    @property
    def urgency(self):
        days = self.days_left
        if self.stage == Stage.READY:
            return "ok"
        if days <= 7:
            return "danger"
        if days <= 15:
            return "warn"
        return "ok"

    @property
    def days_left_label(self):
        days = self.days_left
        if days < 0:
            return ngettext("%(n)s day late", "%(n)s days late", -days) % {"n": -days}
        if days == 0:
            return gettext("Due today")
        return ngettext("%(n)s day left", "%(n)s days left", days) % {"n": days}

    @property
    def days_in_stage(self):
        return (timezone.now() - self.stage_started_at).days

    def timeline(self):
        current = STAGE_SEQUENCE.index(self.stage)
        finished = self.stage in (Stage.READY, Stage.DELIVERED)
        steps = []
        for index, (value, label) in enumerate(Stage.choices):
            if value == Stage.DELIVERED:
                continue
            if index < current or (finished and index == current):
                state = "done"
            elif index == current:
                state = "current"
            else:
                state = "todo"
            steps.append({"value": value, "label": label, "state": state})
        return steps

    def step_position(self):
        """(current step number, number of steps) for 'Step 4 of 9'."""
        steps = self.timeline()
        current = next((i for i, s in enumerate(steps, 1) if s["state"] == "current"), len(steps))
        return current, len(steps)

    def next_stage(self):
        index = STAGE_SEQUENCE.index(self.stage)
        return Stage(STAGE_SEQUENCE[index + 1]) if index + 1 < len(STAGE_SEQUENCE) else None

    def measurements(self):
        fields = ["bust", "shoulder", "sleeve_length", "waist", "hip", "dress_length"]
        return [
            (self._meta.get_field(f).verbose_name, plain_number(getattr(self, f)))
            for f in fields
            if getattr(self, f) is not None
        ]


class StageNote(models.Model):
    """An update on an order, like a comment on a ticket: text, a photo, or both."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="notes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="order_notes")
    author = models.CharField(max_length=100)
    text = models.CharField(max_length=500, blank=True)
    photo = models.ImageField(upload_to="updates/", blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.text or "Photo"


class WorkerTask(models.Model):
    """One worker's turn with one garment. Finished tasks are what workers get paid for."""

    worker = models.ForeignKey(Worker, on_delete=models.PROTECT, related_name="tasks")
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="tasks")
    stage = models.CharField(max_length=20, choices=Stage.choices)
    started_on = models.DateField(default=timezone.localdate)
    finished_on = models.DateField(null=True, blank=True)
    amount = models.DecimalField("Pay (ETB)", max_digits=10, decimal_places=2, default=0)
    paid_on = models.DateField(null=True, blank=True)
    # The messenger (or owner) who carried the garment to this worker.
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="handovers")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-started_on", "-pk"]

    def __str__(self):
        return f"{self.worker} · {self.get_stage_display()} · {self.order}"

    @property
    def is_paid(self):
        return self.paid_on is not None


class Payment(models.Model):
    """Money a customer paid towards an order (deposit or balance)."""

    class Kind:
        DEPOSIT = "Deposit"
        BALANCE = "Balance"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_on = models.DateField(default=timezone.localdate)
    note = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-paid_on", "-pk"]

    def __str__(self):
        return f"{self.amount} ETB · {self.order}"

    @property
    def kind_label(self):
        return {"Deposit": gettext("Deposit"), "Balance": gettext("Balance")}.get(self.note, self.note or gettext("Payment"))


class MaterialUsage(models.Model):
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="usages")
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="material_usages")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]


# --------------------------------------------------------------------------- free-size stock


class FreeSizeItem(models.Model):
    """A ready-made piece sold off the rack. Its page is titled with the type of clothing."""

    class Made(models.TextChoices):
        HANDMADE = "handmade", _("Handmade")
        MACHINE = "machine", _("Machine-made")
        BOTH = "both", _("Hand and machine")

    code = models.CharField(_("Code"), max_length=20, unique=True)
    category = models.CharField(_("Clothing type"), max_length=20, choices=Category.choices, default=Category.HABESHA)
    name = models.CharField(_("Name"), max_length=120, help_text=_("A short name to tell pieces apart, e.g. White kemis"))
    price = models.DecimalField(_("Price (ETB)"), max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(_("In stock"), default=0)
    low_stock_at = models.PositiveIntegerField(_("Warn me at or below"), default=3)
    photo = models.ImageField(_("Main photo"), upload_to="free-size/", blank=True)
    pattern_type = models.CharField(_("Pattern type"), max_length=60, blank=True,
                                    help_text=_("e.g. Tibeb border, Plain weave, K1R P1R"))
    sleeve_length = models.CharField(_("Sleeve length"), max_length=40, blank=True, help_text=_("e.g. 18 cm"))
    length = models.CharField(_("Length"), max_length=40, blank=True, help_text=_("e.g. 100 cm"))
    waist = models.CharField(_("Waist"), max_length=40, blank=True, help_text=_("e.g. 66 cm"))
    fit = models.CharField(_("Fit type"), max_length=60, blank=True, help_text=_("e.g. Slim fit, Loose"))
    fabric = models.CharField(_("Fabric"), max_length=60, blank=True, help_text=_("e.g. Cotton, Highly stretchy"))
    color = models.CharField(_("Color"), max_length=60, blank=True, help_text=_("e.g. White and gold"))
    made = models.CharField(_("Made"), max_length=10, choices=Made.choices, blank=True)
    description = models.TextField(_("Description"), blank=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "free-size item"

    def __str__(self):
        return f"{self.code} · {self.name}"

    @property
    def is_low(self):
        return self.quantity <= self.low_stock_at

    def gallery(self):
        """Main photo first, then the extra angles in the order they were added."""
        images = [self.photo] if self.photo else []
        return images + [p.image for p in self.photos.all()]

    def details(self):
        """The filled-in specs, in the order the product page shows them."""
        rows = [
            (_("Pattern type"), self.pattern_type), (_("Sleeve length"), self.sleeve_length),
            (_("Length"), self.length), (_("Waist"), self.waist),
            (_("Fit type"), self.fit), (_("Fabric"), self.fabric),
            (_("Color"), self.color), (_("Made"), self.get_made_display() if self.made else ""),
        ]
        return [(label, value) for label, value in rows if value]


class ReadyMadePhoto(models.Model):
    """Extra photos of a ready-made piece (back, side, worn, detail)."""

    item = models.ForeignKey(FreeSizeItem, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="free-size/more/")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"Photo of {self.item.code}"


class Sale(models.Model):
    class Status(models.TextChoices):
        PAID = "paid", _("Paid")
        PENDING = "pending", _("Pending")

    item = models.ForeignKey(FreeSizeItem, on_delete=models.PROTECT, related_name="sales")
    quantity = models.PositiveIntegerField(default=1)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PAID)
    customer_name = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.item.code} × {self.quantity}"


class Activity(models.Model):
    """The home page feed. `text` is an English message template; it is translated
    when shown, so each person reads it in their own language."""

    text = models.CharField(max_length=200)
    params = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "activities"

    def __str__(self):
        return self.display

    @classmethod
    def log(cls, text, **params):
        """Activity.log(gettext_noop("Sale recorded · %(code)s"), code=item.code)"""
        return cls.objects.create(text=text[:200], params=params)

    @property
    def display(self):
        params = dict(self.params or {})
        if "stage" in params and params["stage"] in Stage.values:
            params["stage"] = str(Stage(params["stage"]).label).lower()
        if "unit" in params and params["unit"] in Material.Unit.values:
            params["unit"] = str(Material.Unit(params["unit"]).label).lower()
        try:
            return gettext(self.text) % params if params else gettext(self.text)
        except (KeyError, TypeError, ValueError):
            return self.text
