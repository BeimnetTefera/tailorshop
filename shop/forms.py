import json
import re
from datetime import date

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy as _

from . import ethiopian
from .models import (
    CATEGORY_PREFIX,
    Customer,
    FreeSizeItem,
    Material,
    Order,
    Payment,
    ReadyMadePhoto,
    Sale,
    StaffProfile,
    Stage,
    Style,
    StylePhoto,
    Tibebe,
    Worker,
    next_code,
)

# Ethiopian mobile numbers: 09xxxxxxxx / 07xxxxxxxx, optionally written with +251.
PHONE_RE = re.compile(r"^0[79]\d{8}$")
MEASUREMENTS = ["bust", "shoulder", "sleeve_length", "waist", "hip", "dress_length"]


def normalize_phone(raw):
    digits = re.sub(r"[\s\-()]", "", raw or "")
    if digits.startswith("+251"):
        digits = "0" + digits[4:]
    elif digits.startswith("251") and len(digits) == 12:
        digits = "0" + digits[3:]
    return digits


def phone_error():
    return forms.ValidationError(_("Enter a 10-digit phone number starting with 09 or 07."))


class StyledFormMixin:
    """Adds the shared `input` class to text-like widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.RadioSelect, forms.CheckboxInput, forms.CheckboxSelectMultiple,
                                   forms.FileInput, EthiopianDateWidget)):
                continue
            widget.attrs.setdefault("class", "input")


PHOTO = forms.FileInput(attrs={"accept": "image/*"})


class EthiopianDateWidget(forms.MultiWidget):
    """Day, month and year in the Ethiopian calendar; the form gets a normal date.

    Phones show three native pickers, which works the same on iPhone and Android.
    """

    template_name = "shop/widgets/ethiopian_date.html"

    def __init__(self, attrs=None):
        select = {"class": "input"}
        super().__init__([forms.Select(attrs=select), forms.Select(attrs=select), forms.Select(attrs=select)], attrs)

    def decompress(self, value):
        if isinstance(value, str) and value.startswith("eth:"):
            parts = value[4:].split("-")
            return [parts[2], parts[1], parts[0]] if len(parts) == 3 else [None, None, None]
        if isinstance(value, str):
            try:
                value = date.fromisoformat(value)
            except ValueError:
                return [None, None, None]
        if isinstance(value, date):
            e = ethiopian.from_gregorian(value)
            return [e.day, e.month, e.year]
        return [None, None, None]

    def get_context(self, name, value, attrs):
        this_year = ethiopian.today().year
        day, month, year = self.decompress(value)
        years = list(range(this_year - 1, this_year + 3))
        if year and str(year).isdigit() and int(year) not in years:
            years = sorted(set(years) | {int(year)})
        day_widget, month_widget, year_widget = self.widgets
        day_widget.choices = [("", gettext("Day"))] + [(d, d) for d in range(1, 31)]
        month_widget.choices = [("", gettext("Month"))] + [(m, ethiopian.month_name(m)) for m in range(1, 14)]
        year_widget.choices = [("", gettext("Year"))] + [(y, y) for y in years]
        context = super().get_context(name, value, attrs)
        labels = [gettext("Day"), gettext("Month"), gettext("Year")]
        for sub, label in zip(context["widget"]["subwidgets"], labels):
            sub["attrs"]["aria-label"] = label
        return context

    def value_from_datadict(self, data, files, name):
        day, month, year = super().value_from_datadict(data, files, name)
        if not (day or month or year):
            return ""
        try:
            return ethiopian.to_gregorian(int(year), int(month), int(day)).isoformat()
        except (TypeError, ValueError):
            # Keep what was picked so the form can show it again with an error.
            return f"eth:{year}-{month}-{day}"

    def id_for_label(self, id_):
        return f"{id_}_0" if id_ else id_


class EthiopianDateField(forms.DateField):
    widget = EthiopianDateWidget
    default_error_messages = {"invalid": _("That day doesn't exist in that month. Pagume has 5 days (6 in a leap year).")}


class MultiplePhotoInput(forms.FileInput):
    allow_multiple_selected = True


class MultiplePhotoField(forms.ImageField):
    """Accepts several photos from one file picker; cleans to a list."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultiplePhotoInput(attrs={"accept": "image/*"}))
        kwargs.setdefault("required", False)
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else [data] if data else []
        return [super(MultiplePhotoField, self).clean(f, initial) for f in files]


class PhotoChoices(forms.CheckboxSelectMultiple):
    """Checkboxes shown as photo thumbnails (field.html renders them)."""


class OrderForm(StyledFormMixin, forms.ModelForm):
    customer_name = forms.CharField(label=_("Customer name"), max_length=120, help_text=_("Enter full name"))
    customer_phone = forms.CharField(label=_("Phone number"), max_length=20, help_text=_("E.g. 0911013758"))
    deposit = forms.DecimalField(
        label=_("Deposit paid (ETB)"), min_value=0, max_digits=10, decimal_places=2, required=False
    )
    due_date = EthiopianDateField(label=_("Delivery date"))

    class Meta:
        model = Order
        fields = [
            "style", "category", "reference_photo", "people_count",
            *MEASUREMENTS,
            "due_date", "priority", "total_price",
        ]
        widgets = {
            "category": forms.RadioSelect,
            "priority": forms.RadioSelect,
            "reference_photo": PHOTO,
        }
        labels = {"style": _("Select style"), "reference_photo": _("Add reference photo")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["style"].queryset = Style.objects.order_by("name")
        self.fields["style"].empty_label = _("Choose a style (optional)")
        self.fields["customer_phone"].widget.attrs.update(inputmode="tel", placeholder="09…")
        self.fields["total_price"].widget.attrs.update(inputmode="decimal", min="0")
        self.fields["deposit"].widget.attrs.update(inputmode="decimal", min="0")
        for name in MEASUREMENTS:
            self.fields[name].widget.attrs.update(inputmode="decimal", step="0.5", min="0")
        if self.instance.pk:
            self.fields["customer_name"].initial = self.instance.customer.name
            self.fields["customer_phone"].initial = self.instance.customer.phone
            del self.fields["deposit"]

    def clean_customer_phone(self):
        phone = normalize_phone(self.cleaned_data["customer_phone"])
        if not PHONE_RE.match(phone):
            raise phone_error()
        return phone

    def clean_due_date(self):
        due = self.cleaned_data["due_date"]
        if not self.instance.pk and due < timezone.localdate():
            raise forms.ValidationError(_("The delivery date can't be in the past."))
        return due

    def clean(self):
        cleaned = super().clean()
        total, deposit = cleaned.get("total_price"), cleaned.get("deposit")
        if total is not None and deposit and deposit > total:
            self.add_error("deposit", _("The deposit can't be more than the total price."))
        return cleaned

    def save(self, commit=True):
        order = super().save(commit=False)
        name = self.cleaned_data["customer_name"].strip()
        customer, created = Customer.objects.get_or_create(
            phone=self.cleaned_data["customer_phone"], defaults={"name": name}
        )
        if not created and customer.name != name:
            customer.name = name
            customer.save(update_fields=["name"])
        order.customer = customer
        if commit:
            order.save()
            deposit = self.cleaned_data.get("deposit")
            if deposit:
                Payment.objects.create(order=order, amount=deposit, note=Payment.Kind.DEPOSIT)
        return order


class StyleForm(StyledFormMixin, forms.ModelForm):
    more_photos = MultiplePhotoField(
        label=_("More photos"), help_text=_("Back, side and close-up shots. You can pick several at once."),
    )
    remove_photos = forms.ModelMultipleChoiceField(
        StylePhoto.objects.none(), required=False, widget=PhotoChoices,
        label=_("Remove photos"), help_text=_("Tap the photos you want to delete."),
    )

    class Meta:
        model = Style
        fields = ["name", "category", "code", "gender", "photo", "fabric", "color", "fit", "length",
                  "sleeve_length", "recommended_sizes", "description", "is_popular"]
        widgets = {
            "category": forms.RadioSelect,
            "gender": forms.RadioSelect,
            "photo": PHOTO,
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["placeholder"] = _("e.g. Habesha kemis")
        self.fields["description"].widget.attrs["placeholder"] = _("Describe this design")
        self.order_fields(["name", "category", "code", "gender", "photo", "more_photos", "remove_photos"])
        if self.instance.pk and self.instance.photos.exists():
            self.fields["remove_photos"].queryset = self.instance.photos.all()
            self.fields["remove_photos"].label_from_instance = lambda p: p.image.url
        else:
            del self.fields["remove_photos"]
        if not self.instance.pk:
            suggestions = {cat: next_code(Style, prefix) for cat, prefix in CATEGORY_PREFIX.items()}
            category = self.initial.get("category", "habesha")
            self.fields["code"].initial = suggestions.get(category)
            self.fields["code"].widget.attrs["data-suggest"] = json.dumps(suggestions)

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()

    def save(self, commit=True):
        style = super().save(commit=commit)
        if commit:
            for image in self.cleaned_data.get("more_photos", []):
                StylePhoto.objects.create(style=style, image=image)
            for photo in self.cleaned_data.get("remove_photos", []):
                photo.image.delete(save=False)
                photo.delete()
        return style


class MaterialForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Material
        fields = ["name", "material_type", "price", "quantity", "unit", "low_stock_at", "used_for", "photo", "description"]
        widgets = {
            "used_for": forms.CheckboxSelectMultiple,
            "photo": PHOTO,
            "description": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {"used_for": _("Used for these styles")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["placeholder"] = _("e.g. White cotton")


class TibebeForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Tibebe
        fields = ["name", "code", "size", "occasion", "material", "photo", "description"]
        widgets = {
            "size": forms.RadioSelect,
            "photo": PHOTO,
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["material"].empty_label = _("Not linked to a material")
        if not self.instance.pk:
            self.fields["code"].initial = next_code(Tibebe, "TB")

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()


class FreeSizeItemForm(StyledFormMixin, forms.ModelForm):
    more_photos = MultiplePhotoField(
        label=_("More photos"), help_text=_("Back, side and close-up shots. You can pick several at once."),
    )
    remove_photos = forms.ModelMultipleChoiceField(
        ReadyMadePhoto.objects.none(), required=False, widget=PhotoChoices,
        label=_("Remove photos"), help_text=_("Tap the photos you want to delete."),
    )

    class Meta:
        model = FreeSizeItem
        fields = ["category", "name", "code", "price", "quantity", "low_stock_at", "photo",
                  "pattern_type", "sleeve_length", "length", "waist", "fit", "fabric", "color", "made", "description"]
        widgets = {
            "category": forms.RadioSelect,
            "made": forms.RadioSelect,
            "photo": PHOTO,
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["made"].choices = [c for c in self.fields["made"].choices if c[0]]
        self.order_fields(["category", "name", "code", "photo", "more_photos", "remove_photos"])
        if self.instance.pk and self.instance.photos.exists():
            self.fields["remove_photos"].queryset = self.instance.photos.all()
            self.fields["remove_photos"].label_from_instance = lambda p: p.image.url
        else:
            del self.fields["remove_photos"]
        if not self.instance.pk:
            self.fields["code"].initial = next_code(FreeSizeItem, "FS")

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()

    def save(self, commit=True):
        item = super().save(commit=commit)
        if commit:
            for image in self.cleaned_data.get("more_photos", []):
                ReadyMadePhoto.objects.create(item=item, image=image)
            for photo in self.cleaned_data.get("remove_photos", []):
                photo.image.delete(save=False)
                photo.delete()
        return item


class WorkerForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Worker
        fields = ["name", "role", "phone", "rate_per_task", "is_active"]


def _check_password(password, user=None):
    try:
        password_validation.validate_password(password, user)
    except forms.ValidationError as error:
        raise forms.ValidationError(error.messages)
    return password


class MessengerCreateForm(StyledFormMixin, forms.Form):
    name = forms.CharField(label=_("Full name"), max_length=150)
    phone = forms.CharField(label=_("Phone number"), max_length=20, required=False, help_text=_("E.g. 0911013758"))
    username = forms.CharField(
        label=_("Username"), max_length=150,
        help_text=_("What they type to sign in. Letters and numbers, no spaces."),
    )
    password = forms.CharField(
        label=_("Password"), max_length=128,
        help_text=_("At least 8 characters. Write it down and give it to them."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"].widget.attrs.update(inputmode="tel", placeholder="09…")
        self.fields["username"].widget.attrs.update(autocapitalize="none", autocomplete="off")
        self.fields["password"].widget.attrs.update(autocomplete="new-password")

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])
        if phone and not PHONE_RE.match(phone):
            raise phone_error()
        return phone

    def clean_username(self):
        username = self.cleaned_data["username"].strip().lower()
        if not re.fullmatch(r"[\w.@+-]+", username):
            raise forms.ValidationError(_("Use only letters, numbers and . @ + - _ (no spaces)."))
        if get_user_model().objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(_("That username is already taken."))
        return username

    def clean_password(self):
        return _check_password(self.cleaned_data["password"])

    def save(self):
        user = get_user_model().objects.create_user(
            self.cleaned_data["username"], password=self.cleaned_data["password"],
            first_name=self.cleaned_data["name"].strip(),
        )
        StaffProfile.objects.create(user=user, role=StaffProfile.Role.MESSENGER, phone=self.cleaned_data["phone"])
        return user


class MessengerEditForm(StyledFormMixin, forms.Form):
    name = forms.CharField(label=_("Full name"), max_length=150)
    phone = forms.CharField(label=_("Phone number"), max_length=20, required=False)
    is_active = forms.BooleanField(
        label=_("Can sign in"), required=False,
        help_text=_("Untick when they leave. Their past work stays in the records."),
    )
    clean_phone = MessengerCreateForm.clean_phone


class SetPasswordForm(StyledFormMixin, forms.Form):
    password = forms.CharField(label=_("New password"), max_length=128, help_text=_("At least 8 characters."))

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["password"].widget.attrs.update(autocomplete="new-password")

    def clean_password(self):
        return _check_password(self.cleaned_data["password"], self.user)


class SaleForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Sale
        fields = ["item", "quantity", "amount", "status", "customer_name"]
        widgets = {"status": forms.RadioSelect}
        labels = {
            "item": _("Clothing"),
            "quantity": _("Quantity sold"),
            "amount": _("Sale amount (ETB)"),
            "status": _("Payment"),
            "customer_name": _("Customer name (optional)"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer_name"].widget.attrs["placeholder"] = _("Enter a name if you want to save it")

    def clean(self):
        cleaned = super().clean()
        item, qty = cleaned.get("item"), cleaned.get("quantity")
        if qty is not None and qty < 1:
            self.add_error("quantity", _("Sell at least one item."))
        elif item and qty and qty > item.quantity:
            self.add_error("quantity", _("Only %(n)s left in stock.") % {"n": item.quantity})
        return cleaned


class TransferForm(forms.Form):
    worker = forms.ModelChoiceField(queryset=Worker.objects.filter(is_active=True))
    expected_finish = EthiopianDateField(required=False)
    note = forms.CharField(max_length=500, required=False)


class StageForm(forms.Form):
    stage = forms.ChoiceField(choices=Stage.choices)


class NoteForm(forms.Form):
    text = forms.CharField(max_length=500, required=False)
    photo = forms.ImageField(required=False)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("text", "").strip() and not cleaned.get("photo") and not self.errors:
            raise forms.ValidationError(_("Write an update or add a photo."))
        return cleaned


class PaymentForm(forms.Form):
    amount = forms.DecimalField(min_value=1, max_digits=10, decimal_places=2)


class AddStockForm(forms.Form):
    quantity = forms.DecimalField(min_value=0.01, max_digits=10, decimal_places=2)


class UseMaterialForm(forms.Form):
    quantity = forms.DecimalField(min_value=0.01, max_digits=10, decimal_places=2)
    order = forms.ModelChoiceField(queryset=Order.objects.exclude(stage=Stage.DELIVERED), required=False)
