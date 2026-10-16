import atexit
import shutil
import tempfile
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

# The demo data saves photos; keep everything the tests upload out of the project's media/.
_TEST_MEDIA = tempfile.mkdtemp(prefix="tailorshop-test-media-")
atexit.register(shutil.rmtree, _TEST_MEDIA, ignore_errors=True)
override_settings(MEDIA_ROOT=_TEST_MEDIA).enable()
# Passwords and PINs are hashed with a deliberately slow hasher; tests don't need that.
override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]).enable()

from . import ethiopian
from .models import (
    Activity, FreeSizeItem, Material, MaterialCategory, Order, Payment, Sale, StaffProfile, Stage, StageNote, Style,
    Worker, WorkerTask,
)


def _english(user):
    """Most tests read English text; Amharic is the default for new profiles."""
    StaffProfile.objects.filter(user=user).update(language="en")
    return user


def _pin(user):
    """What a protected form carries after the PIN sheet said yes."""
    from .pin import _token_for

    return {"pin_token": _token_for(user)}


def _eth_date(name, value):
    """Form data for an Ethiopian date picker (day, month, year selects)."""
    e = ethiopian.from_gregorian(value)
    return {f"{name}_0": e.day, f"{name}_1": e.month, f"{name}_2": e.year}


def _png(name="photo.png", color="red"):
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (8, 10), color).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class TempMediaMixin:
    def use_temp_media(self):
        import shutil
        import tempfile

        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = self.settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)


class LoginRequiredTests(TestCase):
    def test_redirects_to_login(self):
        response = self.client.get(reverse("shop:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])


class EthiopianCalendarTests(TestCase):
    KNOWN = {
        date(2026, 9, 11): (2019, 1, 1),   # Enkutatash
        date(2023, 9, 12): (2016, 1, 1),   # new year after a leap year
        date(2023, 9, 11): (2015, 13, 6),  # Pagume 6 in leap year 2015
        date(2025, 1, 7): (2017, 4, 29),   # Genna
        date(2024, 1, 20): (2016, 5, 11),  # Timket
    }

    def test_known_dates_both_ways(self):
        for greg, eth in self.KNOWN.items():
            with self.subTest(greg=greg):
                self.assertEqual(tuple(ethiopian.from_gregorian(greg)), eth)
                self.assertEqual(ethiopian.to_gregorian(*eth), greg)

    def test_every_day_round_trips(self):
        day = date(2000, 1, 1)
        while day < date(2040, 1, 1):
            self.assertEqual(ethiopian.to_gregorian(*ethiopian.from_gregorian(day)), day)
            day += timedelta(days=1)

    def test_pagume_has_six_days_only_in_leap_years(self):
        self.assertEqual(ethiopian.month_length(2015, 13), 6)
        self.assertEqual(ethiopian.month_length(2016, 13), 5)
        with self.assertRaises(ValueError):
            ethiopian.to_gregorian(2016, 13, 6)

    def test_formats_follow_the_language(self):
        day = date(2026, 10, 16)
        with translation.override("am"):
            self.assertEqual(ethiopian.format_date(day, "full"), "ዓርብ፣ ጥቅምት 6 ቀን 2019 ዓ.ም.")
            self.assertEqual(ethiopian.format_range(day, day + timedelta(days=6)), "ጥቅምት 6–12, 2019")
        with translation.override("en"):
            self.assertEqual(ethiopian.format_date(day), "Tikimt 6, 2019")
            self.assertEqual(ethiopian.format_range(date(2026, 11, 7), date(2026, 11, 13)), "Tikimt 28 – Hidar 4, 2019")


class ShopFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def setUp(self):
        self.owner = _english(get_user_model().objects.get(username="selam"))
        self.client.force_login(self.owner)

    def test_every_page_renders(self):
        order = Order.objects.exclude(stage=Stage.DELIVERED).first()
        style, material = Style.objects.first(), Material.objects.first()
        urls = [
            reverse("shop:dashboard"), reverse("shop:team"), reverse("shop:manage"), reverse("shop:messenger_list"),
            reverse("shop:order_list"), reverse("shop:order_list") + "?tab=past",
            reverse("shop:order_list") + "?due=late&stage=sewing&priority=urgent",
            reverse("shop:order_create"), reverse("shop:order_create") + f"?style={style.pk}",
            reverse("shop:order_edit", args=[order.pk]),
            reverse("shop:tracker"), reverse("shop:tracker") + "?q=hana",
            reverse("shop:tracker_detail", args=[order.pk]),
            reverse("shop:readymade"), reverse("shop:sales_history"),
            reverse("shop:sales_history") + "?sort=amount&status=paid", reverse("shop:sale_create"),
            reverse("shop:finance"), reverse("shop:finance") + "?month=2019-13", reverse("shop:finance") + "?month=bad",
            reverse("shop:income_detail"),
            reverse("shop:worker_payments"), reverse("shop:worker_payments") + "?status=unpaid",
            reverse("shop:clothing_list"), reverse("shop:clothing_list") + "?occasion=wedding&fabric=Lace&quick=recent",
            reverse("shop:style_detail", args=[style.pk]), reverse("shop:style_create"),
            reverse("shop:material_list") + "?sort=used", reverse("shop:material_list") + "?cat=none",
            reverse("shop:material_detail", args=[material.pk]), reverse("shop:material_create"),
            reverse("shop:material_categories"), reverse("shop:freesize_create"),
        ]
        for language in ("en", "am"):
            StaffProfile.objects.filter(user__username="selam").update(language=language)
            for url in urls:
                with self.subTest(url=url, language=language):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_create_order_with_deposit(self):
        style = Style.objects.get(code="HK-024")
        due = timezone.localdate() + timedelta(days=20)
        response = self.client.post(reverse("shop:order_create"), {
            "customer_name": "Hana Abebe", "customer_phone": "+251 911 013 759",
            "style": style.pk, "category": "wedding", "people_count": 1,
            "bust": "95", "shoulder": "40", "waist": "72",
            **_eth_date("due_date", due),
            "priority": "standard", "total_price": "8000", "deposit": "3500",
        })
        order = Order.objects.latest("pk")
        self.assertRedirects(response, reverse("shop:tracker_detail", args=[order.pk]))
        self.assertEqual(order.customer.phone, "0911013759")
        self.assertEqual(order.balance, Decimal("4500"))
        self.assertEqual(order.due_date, due)

    def test_impossible_ethiopian_date_is_rejected(self):
        count = Order.objects.count()
        # 2020 E.C. is not a leap year, so its Pagume has only 5 days.
        response = self.client.post(reverse("shop:order_create"), {
            "customer_name": "X", "customer_phone": "0911000000", "category": "habesha", "people_count": 1,
            "due_date_0": "6", "due_date_1": "13", "due_date_2": "2020",
            "priority": "standard", "total_price": "1000",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pagume has 5 days")
        self.assertEqual(Order.objects.count(), count)

    def test_deposit_cannot_exceed_total(self):
        response = self.client.post(reverse("shop:order_create"), {
            "customer_name": "X", "customer_phone": "0911000000", "category": "habesha", "people_count": 1,
            **_eth_date("due_date", timezone.localdate() + timedelta(days=5)),
            "priority": "standard", "total_price": "1000", "deposit": "2000",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "can&#x27;t be more than the total")

    def test_transfer_closes_task_and_opens_new_one(self):
        order = Order.objects.get(customer__name="Sara Kebede", stage=Stage.CUTTING)
        sewer = Worker.objects.get(name="Abebe")
        back = timezone.localdate() + timedelta(days=4)
        self.client.post(reverse("shop:order_transfer", args=[order.pk]),
                         {"worker": sewer.pk, "note": "Short sleeves", **_eth_date("expected_finish", back)})
        order.refresh_from_db()
        self.assertEqual(order.stage, Stage.SEWING)
        self.assertEqual(order.current_worker, sewer)
        self.assertEqual(order.expected_finish, back)
        self.assertTrue(WorkerTask.objects.filter(order=order, worker__name="Kebede", finished_on__isnull=False).exists())
        task = WorkerTask.objects.get(order=order, worker=sewer, finished_on__isnull=True)
        self.assertEqual(task.created_by.username, "selam")
        self.assertEqual(order.notes.first().text, "Short sleeves")
        page = self.client.get(reverse("shop:tracker_detail", args=[order.pk]))
        self.assertContains(page, "Selam handed it to Abebe for sewing")

    def test_sale_reduces_stock_and_blocks_overselling(self):
        item = FreeSizeItem.objects.get(code="FS-035")
        start = item.quantity
        self.client.post(reverse("shop:sale_create"), {"item": item.pk, "quantity": 2, "amount": "2400", "status": "paid"})
        item.refresh_from_db()
        self.assertEqual(item.quantity, start - 2)
        before = Sale.objects.count()
        response = self.client.post(reverse("shop:sale_create"), {"item": item.pk, "quantity": 99, "amount": "1", "status": "paid"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Sale.objects.count(), before)

    def test_payment_cannot_exceed_balance(self):
        order = Order.objects.exclude(stage=Stage.DELIVERED).first()
        count = Payment.objects.count()
        self.client.post(reverse("shop:order_add_payment", args=[order.pk]), {"amount": str(order.balance + 1), **_pin(self.owner)})
        self.assertEqual(Payment.objects.count(), count)
        self.client.post(reverse("shop:order_add_payment", args=[order.pk]), {"amount": str(order.balance), **_pin(self.owner)})
        self.assertEqual(order.balance, 0)

    def test_use_material_reduces_stock(self):
        material = Material.objects.get(name="White Chiffon")
        self.client.post(reverse("shop:material_use", args=[material.pk]), {"quantity": "3"})
        material.refresh_from_db()
        self.assertEqual(material.quantity, Decimal("15"))

    def test_mark_ready_then_deliver(self):
        order = Order.objects.get(customer__name="Liya Bekele", stage=Stage.DECORATION)
        self.client.post(reverse("shop:order_mark_ready", args=[order.pk]), _pin(self.owner))
        order.refresh_from_db()
        self.assertEqual(order.stage, Stage.READY)
        self.assertIsNone(order.current_worker)
        self.client.post(reverse("shop:order_deliver", args=[order.pk]), _pin(self.owner))
        order.refresh_from_db()
        self.assertEqual(order.stage, Stage.DELIVERED)
        self.assertEqual(order.delivered_at, timezone.localdate())

    def test_redirect_back_rejects_external_urls(self):
        task = WorkerTask.objects.filter(finished_on__isnull=False, paid_on__isnull=True).first()
        response = self.client.post(reverse("shop:task_mark_paid", args=[task.pk]), {"next": "https://evil.example", **_pin(self.owner)})
        self.assertEqual(response["Location"], reverse("shop:worker_payments"))

    def test_urgent_orders_stand_out_in_the_list(self):
        page = self.client.get(reverse("shop:order_list"))
        html = page.content.decode()
        urgent = Order.objects.filter(priority=Order.Priority.URGENT).exclude(stage=Stage.DELIVERED)
        self.assertTrue(urgent.exists())
        self.assertEqual(html.count("order-card swipe-card urgent"), urgent.count())
        self.assertEqual(html.count("pill pill-urgent"), urgent.count())
        normal = Order.objects.filter(priority=Order.Priority.STANDARD).exclude(stage=Stage.DELIVERED).first()
        self.assertRegex(html, rf'order-card swipe-card"[^>]*data-left="{reverse("shop:order_edit", args=[normal.pk])}"')

    def test_finance_follows_ethiopian_months(self):
        response = self.client.get(reverse("shop:finance") + "?month=2019-2")
        self.assertContains(response, "Tikimt 2019")
        self.assertEqual([w["label"] for w in response.context["weeks"]], ["W1", "W2", "W3", "W4"])
        self.assertEqual(response.context["weeks"][0]["start"], date(2026, 10, 11))
        pagume = self.client.get(reverse("shop:finance") + "?month=2019-13")
        self.assertEqual(len(pagume.context["weeks"]), 1)
        self.assertContains(pagume, 'href="?month=2020-1"')


class UpdateThreadTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def setUp(self):
        self.use_temp_media()
        self.messenger = _english(get_user_model().objects.get(username="dawit"))
        self.client.force_login(self.messenger)
        self.order = Order.objects.get(customer__name="Sara Kebede", stage=Stage.CUTTING)

    def test_post_an_update_with_a_photo(self):
        url = reverse("shop:order_add_note", args=[self.order.pk])
        self.client.post(url, {"text": "Fabric arrived from the weaver.", "photo": _png("fabric.png")})
        note = StageNote.objects.get(order=self.order, text="Fabric arrived from the weaver.")
        self.assertEqual(note.user, self.messenger)
        self.assertTrue(note.photo.name.startswith("updates/"))
        page = self.client.get(reverse("shop:tracker_detail", args=[self.order.pk]))
        self.assertContains(page, "Fabric arrived from the weaver.")
        self.assertContains(page, note.photo.url)
        self.assertEqual(self.client.get(note.photo.url).status_code, 200)

    def test_photo_only_update_is_fine_but_empty_is_not(self):
        url = reverse("shop:order_add_note", args=[self.order.pk])
        self.client.post(url, {"photo": _png()})
        self.assertEqual(self.order.notes.filter(text="").count(), 1)
        before = StageNote.objects.count()
        self.client.post(url, {"text": "   "})
        self.assertEqual(StageNote.objects.count(), before)

    def test_owner_messages_stand_out(self):
        hana = Order.objects.get(customer__name="Hana Tesfaye", stage=Stage.SEWING)
        page = self.client.get(reverse("shop:tracker_detail", args=[hana.pk]))
        self.assertContains(page, 'class="bubble owner"', count=1)
        self.assertContains(page, "Take 2 spools of Gold Thread")


class ReadyMadePageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def setUp(self):
        self.owner = _english(get_user_model().objects.get(username="selam"))
        self.client.force_login(self.owner)

    def test_title_is_the_type_of_clothing(self):
        item = FreeSizeItem.objects.get(code="FS-031")
        page = self.client.get(reverse("shop:readymade_detail", args=[item.pk]))
        self.assertContains(page, '<h1 class="product-title">Wedding</h1>', html=False)
        self.assertContains(page, "Gold tibeb bands")
        self.assertContains(page, "Handmade")
        self.assertContains(page, item.photo.url)
        self.assertEqual(self.client.get(item.photo.url).status_code, 200)
        StaffProfile.objects.filter(user=self.owner).update(language="am")
        page = self.client.get(reverse("shop:readymade_detail", args=[item.pk]))
        self.assertContains(page, '<h1 class="product-title">ሰርግ</h1>', html=False)
        self.assertContains(page, "በእጅ የተሠራ")

    def test_every_demo_piece_has_its_photo(self):
        self.assertEqual(FreeSizeItem.objects.count(), 10)
        self.assertFalse(FreeSizeItem.objects.filter(photo="").exists())
        for code, category in [("FS-042", "wedding"), ("FS-044", "children"), ("FS-046", "men")]:
            self.assertEqual(FreeSizeItem.objects.get(code=code).category, category)

    def test_previous_and_next_walk_the_rack(self):
        items = list(FreeSizeItem.objects.all())
        page = self.client.get(reverse("shop:readymade_detail", args=[items[1].pk]))
        self.assertContains(page, reverse("shop:readymade_detail", args=[items[0].pk]))
        self.assertContains(page, reverse("shop:readymade_detail", args=[items[2].pk]))
        first = self.client.get(reverse("shop:readymade_detail", args=[items[0].pk]))
        self.assertNotContains(first, 'data-pager="prev"')
        rack = self.client.get(reverse("shop:readymade"))
        for item in items:
            self.assertContains(rack, reverse("shop:readymade_detail", args=[item.pk]))

    def test_owner_adds_photos_and_details(self):
        response = self.client.post(reverse("shop:freesize_create"), {
            "category": "habesha", "name": "Green tibeb kemis", "code": "FS-050", "price": "3200",
            "quantity": "3", "low_stock_at": "1", "pattern_type": "K1R, P1R", "length": "100 cm",
            "made": "handmade", "photo": _png("front.png"),
            "more_photos": [_png("side.png", "blue"), _png("back.png", "green")],
        })
        item = FreeSizeItem.objects.get(code="FS-050")
        self.assertRedirects(response, reverse("shop:readymade_detail", args=[item.pk]))
        self.assertEqual(len(item.gallery()), 3)
        page = self.client.get(reverse("shop:readymade_detail", args=[item.pk]))
        self.assertContains(page, "data-gallery-thumb", count=3)
        self.assertContains(page, "K1R, P1R")
        self.assertNotContains(page, "Waist")  # empty details are left out

    def test_messenger_can_sell_but_not_edit(self):
        self.client.force_login(_english(get_user_model().objects.get(username="dawit")))
        item = FreeSizeItem.objects.get(code="FS-024")
        page = self.client.get(reverse("shop:readymade_detail", args=[item.pk]))
        self.assertContains(page, f"{reverse('shop:sale_create')}?item={item.pk}")
        self.assertNotContains(page, reverse("shop:freesize_edit", args=[item.pk]))


class CollectionAndStockTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def setUp(self):
        self.owner = _english(get_user_model().objects.get(username="selam"))
        self.client.force_login(self.owner)

    def test_collection_has_ready_made_and_gallery_tabs(self):
        for url in (reverse("shop:readymade"), reverse("shop:clothing_list")):
            page = self.client.get(url)
            self.assertContains(page, "Collection")
            self.assertContains(page, f'href="{reverse("shop:readymade")}"')
            self.assertContains(page, f'href="{reverse("shop:clothing_list")}"')
        style = Style.objects.get(code="CH-003")
        page = self.client.get(reverse("shop:style_detail", args=[style.pk]))
        self.assertContains(page, '<h1 class="product-title">Children</h1>', html=False)
        self.assertContains(page, f"{reverse('shop:order_create')}?style={style.pk}")
        self.assertEqual(self.client.get(style.photo.url).status_code, 200)

    def test_stock_is_raw_materials_only(self):
        page = self.client.get(reverse("shop:material_list"))
        self.assertNotContains(page, "Clothing styles")
        self.assertNotContains(page, "Tibebe")
        self.assertContains(page, "Fabric")
        fabric = MaterialCategory.objects.get(name="Fabric")
        filtered = self.client.get(reverse("shop:material_list") + f"?cat={fabric.pk}")
        self.assertEqual({m.name for m in filtered.context["materials"]}, {"White Cotton", "White Chiffon"})

    def test_owner_adds_renames_and_deletes_categories(self):
        url = reverse("shop:material_categories")
        self.client.post(url, {"action": "add", "name": "Beads", "name_am": "ዶቃ"})
        beads = MaterialCategory.objects.get(name="Beads")
        before = MaterialCategory.objects.count()
        self.client.post(url, {"action": "add", "name": "beads"})
        self.assertEqual(MaterialCategory.objects.count(), before)  # names must be unique
        self.client.post(url, {"action": "rename", "pk": beads.pk, "name": "Glass beads", "name_am": "የመስታወት ዶቃ"})
        beads.refresh_from_db()
        self.assertEqual(beads.name, "Glass beads")
        with translation.override("am"):
            self.assertEqual(beads.label, "የመስታወት ዶቃ")

        lace = MaterialCategory.objects.get(name="Lace")
        material = lace.materials.get()
        self.client.post(url, {"action": "delete", "pk": lace.pk, **_pin(self.owner)})
        self.assertFalse(MaterialCategory.objects.filter(pk=lace.pk).exists())
        material.refresh_from_db()
        self.assertIsNone(material.category)  # the material is kept
        self.assertContains(self.client.get(reverse("shop:material_list")), "No category")

    def test_messenger_cannot_manage_categories(self):
        self.client.force_login(_english(get_user_model().objects.get(username="dawit")))
        url = reverse("shop:material_categories")
        self.assertRedirects(self.client.get(url), reverse("shop:dashboard"))
        self.client.post(url, {"action": "add", "name": "Sneaky"})
        self.assertFalse(MaterialCategory.objects.filter(name="Sneaky").exists())
        self.assertNotContains(self.client.get(reverse("shop:material_list")), url)


class LanguageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def test_login_page_is_english_first_and_switches(self):
        self.assertContains(self.client.get(reverse("login")), "Welcome back")
        response = self.client.post(reverse("shop:set_language"), {"language": "am", "next": reverse("login")})
        self.assertRedirects(response, reverse("login"))
        self.assertEqual(response.cookies["language"].value, "am")
        self.assertContains(self.client.get(reverse("login")), "እንኳን በደህና ተመለሱ")

    def test_choice_is_saved_on_the_profile(self):
        user = get_user_model().objects.get(username="dawit")
        self.assertEqual(user.profile.language, "en")
        self.client.force_login(user)
        home = self.client.get(reverse("shop:dashboard"))
        self.assertContains(home, "Collection")
        self.assertContains(home, ethiopian.MONTHS_EN[ethiopian.today().month - 1])
        self.client.post(reverse("shop:set_language"), {"language": "am"})
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.language, "am")
        self.client.cookies.clear()
        self.client.force_login(user)
        home = self.client.get(reverse("shop:dashboard"))
        self.assertContains(home, "መነሻ")
        self.assertContains(home, ethiopian.MONTHS_AM[ethiopian.today().month - 1])

    def test_activity_feed_is_translated_when_shown(self):
        entry = Activity.objects.get(text__startswith="Sale recorded")
        with translation.override("am"):
            self.assertEqual(entry.display, "ሽያጭ ተመዝግቧል · FS-024")
        with translation.override("en"):
            self.assertEqual(entry.display, "Sale recorded · FS-024")
        moved = Activity.objects.get(text__contains="moved to")
        with translation.override("am"):
            self.assertIn("ስፌት", moved.display)

    def test_unknown_language_falls_back_to_english(self):
        self.client.cookies["language"] = "fr"
        self.assertContains(self.client.get(reverse("login")), 'lang="en"')


class RoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def setUp(self):
        self.owner = _english(get_user_model().objects.get(username="selam"))
        self.messenger = _english(get_user_model().objects.get(username="dawit"))

    def test_messenger_cannot_open_owner_pages(self):
        self.client.force_login(self.messenger)
        task = WorkerTask.objects.filter(finished_on__isnull=False, paid_on__isnull=True).first()
        for url in [reverse("shop:finance"), reverse("shop:income_detail"), reverse("shop:worker_payments"),
                    reverse("shop:team"), reverse("shop:messenger_list"), reverse("shop:style_create"),
                    reverse("shop:material_create"), reverse("shop:freesize_create")]:
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), reverse("shop:dashboard"))
        self.client.post(reverse("shop:task_mark_paid", args=[task.pk]))
        task.refresh_from_db()
        self.assertIsNone(task.paid_on)

    def test_messenger_does_the_daily_work(self):
        self.client.force_login(self.messenger)
        for url in [reverse("shop:dashboard"), reverse("shop:order_list"), reverse("shop:order_create"),
                    reverse("shop:readymade"), reverse("shop:sale_create"), reverse("shop:sales_history"),
                    reverse("shop:material_list"), reverse("shop:account")]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        home = self.client.get(reverse("shop:dashboard"))
        self.assertNotContains(home, reverse("shop:finance"))
        self.assertContains(home, reverse("shop:readymade"))
        self.assertNotContains(self.client.get(reverse("shop:sales_history")), "ETB received")
        self.assertNotContains(self.client.get(reverse("shop:readymade")), "ETB received")
        material = Material.objects.get(name="White Thread")
        self.client.post(reverse("shop:material_add_stock", args=[material.pk]), {"quantity": "5"})
        material.refresh_from_db()
        self.assertEqual(material.quantity, Decimal("45"))

    def test_owner_creates_then_switches_off_a_messenger(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("shop:messenger_list"), {
            "name": "Meron Haile", "phone": "0912 000 111", "username": "Meron", "password": "kemis-2019-ok", **_pin(self.owner),
        })
        self.assertRedirects(response, reverse("shop:messenger_list"))
        meron = get_user_model().objects.get(username="meron")
        self.assertEqual(meron.profile.phone, "0912000111")
        self.assertEqual(meron.profile.language, "en")
        self.assertFalse(meron.is_staff)

        other = self.client_class()
        self.assertTrue(other.login(username="meron", password="kemis-2019-ok"))
        self.assertEqual(other.get(reverse("shop:dashboard")).status_code, 200)

        self.client.post(reverse("shop:messenger_edit", args=[meron.pk]), {"name": "Meron Haile", "phone": "", **_pin(self.owner)})
        meron.refresh_from_db()
        self.assertFalse(meron.is_active)
        # Already signed in on a phone? The next page sends them back to the login screen.
        self.assertIn(reverse("login"), other.get(reverse("shop:dashboard"))["Location"])
        self.assertFalse(self.client_class().login(username="meron", password="kemis-2019-ok"))

    def test_owner_resets_a_password(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("shop:messenger_edit", args=[self.messenger.pk]), {"password": "new-pass-2019", **_pin(self.owner)})
        self.assertTrue(self.client_class().login(username="dawit", password="new-pass-2019"))

    def test_weak_password_and_taken_username_are_rejected(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("shop:messenger_list"), {
            "name": "X", "username": "dawit", "password": "123", **_pin(self.owner),
        })
        self.assertContains(response, "already taken")
        self.assertContains(response, "too short")
        StaffProfile.objects.filter(user=self.owner).update(language="am")
        response = self.client.post(reverse("shop:messenger_list"), {"name": "X", "username": "dawit", "password": "123", **_pin(self.owner)})
        self.assertContains(response, "ይህ የተጠቃሚ ስም ተይዟል።")
        self.assertContains(response, "በጣም አጭር ነው")

    def test_owner_has_a_team_tab_for_accounts(self):
        self.client.force_login(self.owner)
        home = self.client.get(reverse("shop:dashboard"))
        self.assertContains(home, f'href="{reverse("shop:manage")}"')
        self.assertRedirects(self.client.get(reverse("shop:account")), reverse("shop:manage"))
        page = self.client.get(reverse("shop:manage"))
        self.assertContains(page, reverse("shop:messenger_list"))
        self.assertContains(page, reverse("shop:team"))
        self.assertContains(page, "1 can sign in")
        self.assertContains(page, "Sign out")
        self.assertContains(self.client.get(reverse("shop:messenger_list")), f'href="{reverse("shop:manage")}"')

    def test_messenger_has_no_team_tab(self):
        self.client.force_login(self.messenger)
        home = self.client.get(reverse("shop:dashboard"))
        self.assertNotContains(home, reverse("shop:manage"))
        self.assertContains(home, reverse("shop:account"))
        self.assertRedirects(self.client.get(reverse("shop:manage")), reverse("shop:dashboard"))
        self.assertEqual(self.client.get(reverse("shop:account")).status_code, 200)

    def test_money_chart_offers_bars_and_line(self):
        self.client.force_login(self.owner)
        page = self.client.get(reverse("shop:finance"))
        self.assertContains(page, 'data-chart="bar"')
        self.assertContains(page, 'data-chart="line"')
        self.assertContains(page, 'data-chart-type="line"')
        line = page.context["line"]
        # The line covers last month and this month, so it shows a trend even in week 1.
        self.assertEqual([m["name"] for m in line["months"]],
                         [ethiopian.month_name(ethiopian.add_months(*ethiopian.today()[:2], -1)[1]),
                          ethiopian.month_name(ethiopian.today().month)])
        self.assertGreater(len(line["weeks"]), len(page.context["weeks"]))
        shown = [w for w in line["weeks"] if not w["is_future"]]
        self.assertGreaterEqual(len(shown), 5)
        self.assertEqual(len(line["points"].split()), len(shown))
        for w in shown:  # every plotted week sits inside the chart, the biggest one at the top
            self.assertTrue(line["top"] <= w["y"] <= line["base"])
        self.assertEqual(min(w["y"] for w in shown), line["top"])
        self.assertContains(page, "<caption>")  # table view for screen readers

    def test_owner_cannot_be_edited_as_a_messenger(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("shop:messenger_edit", args=[self.owner.pk])).status_code, 404)


class PinTests(TestCase):
    """Changes to money, orders and accounts, and deletions, need the PIN."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def setUp(self):
        self.owner = _english(get_user_model().objects.get(username="selam"))
        self.messenger = _english(get_user_model().objects.get(username="dawit"))
        self.client.force_login(self.messenger)
        self.order = Order.objects.get(customer__name="Liya Bekele", stage=Stage.DECORATION)

    def test_protected_change_without_pin_changes_nothing(self):
        response = self.client.post(reverse("shop:order_mark_ready", args=[self.order.pk]), follow=True)
        self.order.refresh_from_db()
        self.assertEqual(self.order.stage, Stage.DECORATION)
        self.assertEqual(response.redirect_chain[-1][0], reverse("shop:dashboard"))
        self.assertContains(response, "Nothing was changed")

    def test_correct_pin_gives_a_token_that_saves_the_change(self):
        reply = self.client.post(reverse("shop:pin_verify"), {"pin": "1234"}).json()
        self.assertTrue(reply["ok"])
        self.client.post(reverse("shop:order_mark_ready", args=[self.order.pk]), {"pin_token": reply["token"]})
        self.order.refresh_from_db()
        self.assertEqual(self.order.stage, Stage.READY)

    def test_someone_elses_or_old_token_is_refused(self):
        self.client.post(reverse("shop:order_mark_ready", args=[self.order.pk]), _pin(self.owner))
        self.order.refresh_from_db()
        self.assertEqual(self.order.stage, Stage.DECORATION)
        from django.core import signing

        from . import pin
        from unittest import mock

        old = signing.TimestampSigner(salt="shop.pin").sign(str(self.messenger.pk))
        with mock.patch.object(pin, "TOKEN_SECONDS", -1):  # as if the two minutes had passed
            self.client.post(reverse("shop:order_mark_ready", args=[self.order.pk]), {"pin_token": old})
        self.order.refresh_from_db()
        self.assertEqual(self.order.stage, Stage.DECORATION)

    def test_wrong_pins_lock_for_a_while(self):
        for left in (4, 3, 2, 1):
            reply = self.client.post(reverse("shop:pin_verify"), {"pin": "9999"}).json()
            self.assertFalse(reply["ok"])
            self.assertIn(f"{left} tr", reply["error"])
        reply = self.client.post(reverse("shop:pin_verify"), {"pin": "9999"})
        self.assertEqual(reply.status_code, 429)
        # Even the right PIN waits until the lock ends.
        self.assertEqual(self.client.post(reverse("shop:pin_verify"), {"pin": "1234"}).status_code, 429)

    def test_setting_a_pin_needs_the_sign_in_password(self):
        url = reverse("shop:pin_set")
        self.assertFalse(self.client.post(url, {"password": "wrong", "pin": "4321", "pin2": "4321"}).json()["ok"])
        self.assertFalse(self.client.post(url, {"password": "dawit1234", "pin": "12", "pin2": "12"}).json()["ok"])
        self.assertFalse(self.client.post(url, {"password": "dawit1234", "pin": "4321", "pin2": "4322"}).json()["ok"])
        reply = self.client.post(url, {"password": "dawit1234", "pin": "4321", "pin2": "4321"}).json()
        self.assertTrue(reply["ok"])
        self.assertFalse(self.client.post(reverse("shop:pin_verify"), {"pin": "1234"}).json()["ok"])
        self.assertTrue(self.client.post(reverse("shop:pin_verify"), {"pin": "4321"}).json()["ok"])

    def test_no_pin_yet_asks_to_create_one(self):
        StaffProfile.objects.filter(user=self.messenger).update(pin_hash="")
        reply = self.client.post(reverse("shop:pin_verify"), {"pin": "1234"}).json()
        self.assertTrue(reply["needs_pin"])

    def test_protected_forms_are_marked_and_everyday_ones_are_not(self):
        page = self.client.get(reverse("shop:tracker_detail", args=[self.order.pk]))
        html = page.content.decode()
        for action in ("order_mark_ready", "order_update_stage", "order_add_payment"):
            url = reverse(f"shop:{action}", args=[self.order.pk])
            self.assertRegex(html, rf'action="{url}"[^>]*data-protect')
        transfer = reverse("shop:order_transfer", args=[self.order.pk])
        self.assertNotRegex(html, rf'action="{transfer}"[^>]*data-protect')
        self.assertContains(page, 'id="pin-sheet"')

    def test_owner_clears_a_messengers_pin(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("shop:messenger_edit", args=[self.messenger.pk]), {"reset_pin": "1", **_pin(self.owner)})
        self.messenger.profile.refresh_from_db()
        self.assertEqual(self.messenger.profile.pin_hash, "")

    def test_sign_out_all_other_devices(self):
        lost_phone = self.client_class()
        lost_phone.force_login(self.messenger)
        self.assertEqual(lost_phone.get(reverse("shop:dashboard")).status_code, 200)
        self.client.get(reverse("shop:dashboard"))
        self.client.post(reverse("shop:sign_out_everywhere"), _pin(self.messenger))
        self.assertIn(reverse("login"), lost_phone.get(reverse("shop:dashboard"))["Location"])
        self.assertEqual(self.client.get(reverse("shop:dashboard")).status_code, 200)  # this device stays in
        # Signing in again on the found phone works as normal.
        self.assertTrue(lost_phone.login(username="dawit", password="dawit1234"))
        self.assertEqual(lost_phone.get(reverse("shop:dashboard")).status_code, 200)


class DemoInstanceTests(TestCase):
    """On Vercel each server instance builds its own demo; they must agree with each other."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def test_password_hash_is_the_same_on_every_instance(self):
        from django.contrib.auth.hashers import get_hasher

        from .demo import demo_password

        selam = get_user_model().objects.get(username="selam")
        self.assertEqual(selam.password, demo_password("selam1234"))
        self.assertFalse(get_hasher().must_update(selam.password))  # not re-hashed (re-salted) on login
        self.assertTrue(self.client.login(username="selam", password="selam1234"))
        selam.refresh_from_db()
        self.assertEqual(selam.password, demo_password("selam1234"))

    def test_signed_in_session_survives_another_instance(self):
        from .demo import demo_password

        self.client.login(username="dawit", password="dawit1234")
        # Another instance builds the account again from scratch: the hash comes out identical.
        get_user_model().objects.filter(username="dawit").update(password=demo_password("dawit1234"))
        self.assertEqual(self.client.get(reverse("shop:dashboard")).status_code, 200)

    def test_demo_photos_come_from_the_app_not_storage(self):
        from .demo import demo_photo

        item = FreeSizeItem.objects.get(code="FS-024")
        self.assertEqual(item.photo.name, "demo/white-cotton-kemis.jpg")
        self.client.login(username="dawit", password="dawit1234")
        response = self.client.get(item.photo.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertIsNone(demo_photo("demo/../settings.py"))
        self.assertEqual(self.client.get(reverse("media_file", args=["demo/missing.jpg"])).status_code, 404)


class MediaTests(TempMediaMixin, TestCase):
    def setUp(self):
        self.use_temp_media()
        from django.core.files.storage import default_storage
        self.name = default_storage.save("styles/test.png", _png())

    def test_photos_need_a_login(self):
        url = reverse("media_file", args=[self.name])
        self.assertIn(reverse("login"), self.client.get(url)["Location"])
        self.client.force_login(get_user_model().objects.create_user("m", password="x"))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(self.client.get(reverse("media_file", args=["styles/missing.png"])).status_code, 404)


class StyleGalleryTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def setUp(self):
        self.use_temp_media()
        self.owner = _english(get_user_model().objects.get(username="selam"))
        self.client.force_login(self.owner)

    def _post_edit(self, style, **extra):
        data = {
            "name": style.name, "category": style.category, "code": style.code, "gender": style.gender,
            "fabric": style.fabric, "color": "Ivory", "fit": "Slim fit", "length": "140 cm",
            "sleeve_length": "Long sleeve", "recommended_sizes": style.recommended_sizes,
            "description": style.description,
        }
        data.update(extra)
        return self.client.post(reverse("shop:style_edit", args=[style.pk]), {**data, **_pin(self.owner)})

    def test_upload_several_photos_then_remove_one(self):
        style = Style.objects.get(code="WD-015")
        response = self._post_edit(style, photo=_png("main.png"),
                                   more_photos=[_png("back.png", "blue"), _png("side.png", "green")])
        self.assertRedirects(response, reverse("shop:style_detail", args=[style.pk]))
        style.refresh_from_db()
        self.assertEqual(style.color, "Ivory")
        self.assertEqual(style.photos.count(), 2)
        self.assertEqual(len(style.gallery()), 3)
        page = self.client.get(reverse("shop:style_detail", args=[style.pk]))
        self.assertContains(page, "data-gallery-thumb", count=3)
        self.assertContains(page, "140 cm")

        doomed = style.photos.first()
        self._post_edit(style, remove_photos=[doomed.pk])
        self.assertEqual(list(style.photos.all()), list(style.photos.exclude(pk=doomed.pk)))
        self.assertEqual(style.photos.count(), 1)

    def test_previous_and_next_follow_code_order(self):
        styles = list(Style.objects.all())
        middle = styles[1]
        page = self.client.get(reverse("shop:style_detail", args=[middle.pk]))
        self.assertContains(page, reverse("shop:style_detail", args=[styles[0].pk]))
        self.assertContains(page, reverse("shop:style_detail", args=[styles[2].pk]))
        self.assertContains(page, f"2 of {len(styles)}")
        first = self.client.get(reverse("shop:style_detail", args=[styles[0].pk]))
        self.assertNotContains(first, 'data-pager="prev"')
