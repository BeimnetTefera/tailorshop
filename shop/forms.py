import json
import re

from django import forms
from django.utils import timezone

from .models import (
    CATEGORY_PREFIX,
    Customer,
    FreeSizeItem,
    Material,
    Order,
    Payment,
    Sale,
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


class StyledFormMixin:
    """Adds the shared `input` class to text-like widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.RadioSelect, forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.FileInput)):
                continue
            widget.attrs.setdefault("class", "input")


PHOTO = forms.FileInput(attrs={"accept": "image/*"})
DATE = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})


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
    customer_name = forms.CharField(label="Customer name", max_length=120, help_text="Enter full name")
    customer_phone = forms.CharField(label="Phone number", max_length=20, help_text="E.g. 0911013758")
    deposit = forms.DecimalField(
        label="Deposit paid (ETB)", min_value=0, max_digits=10, decimal_places=2, required=False
    )

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
            "due_date": DATE,
            "reference_photo": PHOTO,
        }
        labels = {"style": "Select style", "reference_photo": "Add reference photo"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["style"].queryset = Style.objects.order_by("name")
        self.fields["style"].empty_label = "Choose a style (optional)"
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
            raise forms.ValidationError("Enter a 10-digit phone number starting with 09 or 07.")
        return phone

    def clean_due_date(self):
        due = self.cleaned_data["due_date"]
        if not self.instance.pk and due < timezone.localdate():
            raise forms.ValidationError("The delivery date can't be in the past.")
        return due

    def clean(self):
        cleaned = super().clean()
        total, deposit = cleaned.get("total_price"), cleaned.get("deposit")
        if total is not None and deposit and deposit > total:
            self.add_error("deposit", "The deposit can't be more than the total price.")
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
                Payment.objects.create(order=order, amount=deposit, note="Deposit")
        return order


class StyleForm(StyledFormMixin, forms.ModelForm):
    more_photos = MultiplePhotoField(
        label="More photos", help_text="Back, side and close-up shots. You can pick several at once.",
    )
    remove_photos = forms.ModelMultipleChoiceField(
        StylePhoto.objects.none(), required=False, widget=PhotoChoices,
        label="Remove photos", help_text="Tap the photos you want to delete.",
    )

    class Meta:
        model = Style
        fields = ["name", "category", "code", "gender", "photo", "fabric", "color", "fit", "length",
                  "sleeve_length", "recommended_sizes", "description", "is_popular"]
        widgets = {
            "category": forms.RadioSelect,
            "gender": forms.RadioSelect,
            "photo": PHOTO,
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Describe this design"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["placeholder"] = "e.g. Habesha kemis"
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["placeholder"] = "e.g. White cotton"
        self.fields["used_for"].label = "Used for these styles"


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
        self.fields["material"].empty_label = "Not linked to a material"
        if not self.instance.pk:
            self.fields["code"].initial = next_code(Tibebe, "TB")

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()


class FreeSizeItemForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = FreeSizeItem
        fields = ["code", "name", "price", "quantity", "low_stock_at", "photo"]
        widgets = {"photo": PHOTO}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["code"].initial = next_code(FreeSizeItem, "FS")

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()


class WorkerForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Worker
        fields = ["name", "role", "phone", "rate_per_task", "is_active"]


class SaleForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Sale
        fields = ["item", "quantity", "amount", "status", "customer_name"]
        widgets = {"status": forms.RadioSelect}
        labels = {
            "item": "Clothing",
            "quantity": "Quantity sold",
            "amount": "Sale amount (ETB)",
            "status": "Payment",
            "customer_name": "Customer name (optional)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer_name"].widget.attrs["placeholder"] = "Enter a name if you want to save it"

    def clean(self):
        cleaned = super().clean()
        item, qty = cleaned.get("item"), cleaned.get("quantity")
        if qty is not None and qty < 1:
            self.add_error("quantity", "Sell at least one item.")
        elif item and qty and qty > item.quantity:
            self.add_error("quantity", f"Only {item.quantity} left in stock.")
        return cleaned


class TransferForm(forms.Form):
    worker = forms.ModelChoiceField(queryset=Worker.objects.filter(is_active=True))
    expected_finish = forms.DateField(required=False)
    note = forms.CharField(max_length=300, required=False)


class StageForm(forms.Form):
    stage = forms.ChoiceField(choices=Stage.choices)


class NoteForm(forms.Form):
    text = forms.CharField(max_length=300)


class PaymentForm(forms.Form):
    amount = forms.DecimalField(min_value=1, max_digits=10, decimal_places=2)


class AddStockForm(forms.Form):
    quantity = forms.DecimalField(min_value=0.01, max_digits=10, decimal_places=2)


class UseMaterialForm(forms.Form):
    quantity = forms.DecimalField(min_value=0.01, max_digits=10, decimal_places=2)
    order = forms.ModelChoiceField(queryset=Order.objects.exclude(stage=Stage.DELIVERED), required=False)
