"""Data model for a habesha-kemis tailoring shop.

The app covers five areas shown in the mockups:
  * custom orders and their production stages (who holds the garment now),
  * free-size ready-made stock and its sales,
  * the style library, raw materials and tibebe (woven border) designs,
  * money coming in (deposits, balances, sales),
  * money going out to workers for finished tasks.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class Category(models.TextChoices):
    HABESHA = "habesha", "Habesha kemis"
    WEDDING = "wedding", "Wedding"
    MODERN = "modern", "Modern"
    MEN = "men", "Men"
    CHILDREN = "children", "Children"
    FORMAL = "formal", "Formal"
    HOLIDAY = "holiday", "Holiday"


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
    CREATED = "created", "Order created"
    MEASURED = "measured", "Measurements taken"
    FABRIC = "fabric", "Fabric prepared"
    CUTTING = "cutting", "Cutting"
    SEWING = "sewing", "Sewing"
    DECORATION = "decoration", "Decoration"
    REPAIR = "repair", "Repair"
    QUALITY = "quality", "Quality check"
    READY = "ready", "Ready for pickup"
    DELIVERED = "delivered", "Delivered"


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
        OWNER = "owner", "Owner"
        MESSENGER = "messenger", "Messenger"

    class Language(models.TextChoices):
        AMHARIC = "am", "አማርኛ"
        ENGLISH = "en", "English"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MESSENGER)
    phone = models.CharField(max_length=20, blank=True)
    language = models.CharField(max_length=5, choices=Language.choices, default=Language.AMHARIC)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.get_username()} ({self.get_role_display()})"


class Worker(models.Model):
    """Production workers (weaver, cutter, tailor…). They don't log in; messengers bring them the work."""

    class Role(models.TextChoices):
        # Values match Stage values so a transfer moves the order to that stage.
        CUTTING = "cutting", "Cutter"
        SEWING = "sewing", "Sewing"
        DECORATION = "decoration", "Decoration specialist"
        REPAIR = "repair", "Patch repairer"
        QUALITY = "quality", "Quality checker"

    name = models.CharField(max_length=100)
    role = models.CharField(max_length=20, choices=Role.choices)
    phone = models.CharField(max_length=20, blank=True)
    rate_per_task = models.DecimalField(
        "Pay per task (ETB)", max_digits=10, decimal_places=2, default=0,
        help_text="Default amount owed when this worker finishes a garment.",
    )
    is_active = models.BooleanField("Currently working here", default=True)

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
        WOMEN = "women", "Women"
        MEN = "men", "Men"
        CHILDREN = "children", "Children"

    code = models.CharField("Style code", max_length=20, unique=True)
    name = models.CharField("Style name", max_length=120)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.HABESHA)
    gender = models.CharField(max_length=20, choices=Gender.choices, default=Gender.WOMEN)
    fabric = models.CharField(max_length=60, blank=True, help_text="e.g. Cotton, Lace, Chiffon")
    color = models.CharField("Color", max_length=60, blank=True, help_text="e.g. White and gold")
    fit = models.CharField("Fit", max_length=60, blank=True, help_text="e.g. Slim fit, Loose, Flared skirt")
    length = models.CharField("Dress length", max_length=40, blank=True, help_text="e.g. Ankle length, 140 cm")
    sleeve_length = models.CharField("Sleeve length", max_length=40, blank=True, help_text="e.g. Long sleeve, 60 cm")
    photo = models.ImageField("Main photo", upload_to="styles/", blank=True)
    description = models.TextField(blank=True)
    recommended_sizes = models.CharField(
        max_length=100, blank=True, help_text="Comma separated, e.g. Medium, Large"
    )
    is_popular = models.BooleanField("Popular style", default=False)
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


class Material(models.Model):
    class Type(models.TextChoices):
        FABRIC = "fabric", "Fabric"
        THREAD = "thread", "Thread"
        BUTTONS = "buttons", "Buttons"
        EMBROIDERY = "embroidery", "Embroidery"
        LACE = "lace", "Lace"
        OTHER = "other", "Other"

    class Unit(models.TextChoices):
        METERS = "meters", "Meters"
        SPOOLS = "spools", "Spools"
        PIECES = "pieces", "Pieces"

    name = models.CharField("Material name", max_length=120)
    material_type = models.CharField("Material type", max_length=20, choices=Type.choices, default=Type.FABRIC)
    price = models.DecimalField("Price per unit (ETB)", max_digits=10, decimal_places=2)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit = models.CharField(max_length=10, choices=Unit.choices, default=Unit.METERS)
    low_stock_at = models.DecimalField(
        "Warn me when stock is at or below", max_digits=10, decimal_places=2, default=5
    )
    photo = models.ImageField(upload_to="materials/", blank=True)
    description = models.TextField(blank=True)
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
    def availability(self):
        amount = f"{plain_number(self.quantity)} {self.get_unit_display().lower()}"
        if self.status == "out":
            return "Out of stock"
        if self.status == "low":
            return f"Low stock: {amount}"
        return f"{amount} available"


class Tibebe(models.Model):
    class Size(models.TextChoices):
        LARGE = "large", "Large"
        MEDIUM = "medium", "Medium"
        THIN = "thin", "Thin"

    code = models.CharField("Style code", max_length=20, unique=True)
    name = models.CharField("Style name", max_length=120)
    size = models.CharField("Border width", max_length=10, choices=Size.choices, default=Size.MEDIUM)
    occasion = models.CharField(max_length=60, blank=True, help_text="e.g. Wedding, Holiday, Everyday")
    material = models.ForeignKey(Material, on_delete=models.SET_NULL, null=True, blank=True, related_name="tibebes")
    photo = models.ImageField(upload_to="tibebe/", blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["code"]
        verbose_name = "tibebe design"

    def __str__(self):
        return f"{self.code} · {self.name}"


# --------------------------------------------------------------------------- orders


def _measure(label):
    return models.DecimalField(label, max_digits=5, decimal_places=1, null=True, blank=True)


class Order(models.Model):
    class Priority(models.TextChoices):
        STANDARD = "standard", "Standard"
        URGENT = "urgent", "Urgent"

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    style = models.ForeignKey(Style, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.HABESHA)
    reference_photo = models.ImageField(upload_to="references/", blank=True)
    people_count = models.PositiveSmallIntegerField(
        "Number of people", default=1, help_text="For group orders, e.g. bride and bridesmaids."
    )

    bust = _measure("Bust")
    shoulder = _measure("Shoulder")
    sleeve_length = _measure("Sleeve length")
    waist = _measure("Waist")
    hip = _measure("Hip")
    dress_length = _measure("Dress length")

    due_date = models.DateField("Delivery date")
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.STANDARD)
    total_price = models.DecimalField("Total price (ETB)", max_digits=10, decimal_places=2)

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
        return f"ORD-{self.pk:04d}" if self.pk else "New order"

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
        return "Delayed" if self.is_delayed else self.get_stage_display()

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
            return f"{-days} day{'s' if days != -1 else ''} late"
        if days == 0:
            return "Due today"
        return f"{days} day{'s' if days != 1 else ''} left"

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

    def measurements(self):
        fields = ["bust", "shoulder", "sleeve_length", "waist", "hip", "dress_length"]
        return [
            (self._meta.get_field(f).verbose_name, plain_number(getattr(self, f)))
            for f in fields
            if getattr(self, f) is not None
        ]


class StageNote(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="notes")
    author = models.CharField(max_length=100)
    text = models.CharField(max_length=300)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.text


class WorkerTask(models.Model):
    """One worker's turn with one garment. Finished tasks are what workers get paid for."""

    worker = models.ForeignKey(Worker, on_delete=models.PROTECT, related_name="tasks")
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="tasks")
    stage = models.CharField(max_length=20, choices=Stage.choices)
    started_on = models.DateField(default=timezone.localdate)
    finished_on = models.DateField(null=True, blank=True)
    amount = models.DecimalField("Pay (ETB)", max_digits=10, decimal_places=2, default=0)
    paid_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-started_on", "-pk"]

    def __str__(self):
        return f"{self.worker} · {self.get_stage_display()} · {self.order}"

    @property
    def is_paid(self):
        return self.paid_on is not None


class Payment(models.Model):
    """Money a customer paid towards an order (deposit or balance)."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_on = models.DateField(default=timezone.localdate)
    note = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-paid_on", "-pk"]

    def __str__(self):
        return f"{self.amount} ETB · {self.order}"


class MaterialUsage(models.Model):
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="usages")
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="material_usages")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]


# --------------------------------------------------------------------------- free-size stock


class FreeSizeItem(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    price = models.DecimalField("Price (ETB)", max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField("In stock", default=0)
    low_stock_at = models.PositiveIntegerField("Warn me at or below", default=3)
    photo = models.ImageField(upload_to="free-size/", blank=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "free-size item"

    def __str__(self):
        return f"{self.code} · {self.name}"

    @property
    def is_low(self):
        return self.quantity <= self.low_stock_at


class Sale(models.Model):
    class Status(models.TextChoices):
        PAID = "paid", "Paid"
        PENDING = "pending", "Pending"

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
    text = models.CharField(max_length=200)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "activities"

    def __str__(self):
        return self.text

    @classmethod
    def log(cls, text):
        return cls.objects.create(text=text[:200])
