from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import FreeSizeItem, Material, Order, Payment, Sale, Stage, Style, Worker, WorkerTask


class LoginRequiredTests(TestCase):
    def test_redirects_to_login(self):
        response = self.client.get(reverse("shop:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])


class ShopFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def setUp(self):
        self.client.force_login(get_user_model().objects.get(username="selam"))

    def test_every_page_renders(self):
        order = Order.objects.exclude(stage=Stage.DELIVERED).first()
        style, material = Style.objects.first(), Material.objects.first()
        urls = [
            reverse("shop:dashboard"), reverse("shop:team"),
            reverse("shop:order_list"), reverse("shop:order_list") + "?tab=past",
            reverse("shop:order_list") + "?due=late&stage=sewing&priority=urgent",
            reverse("shop:order_create"), reverse("shop:order_create") + f"?style={style.pk}",
            reverse("shop:order_edit", args=[order.pk]),
            reverse("shop:tracker"), reverse("shop:tracker") + "?q=hana",
            reverse("shop:tracker_detail", args=[order.pk]),
            reverse("shop:sales_history"), reverse("shop:sales_history") + "?sort=amount&status=paid",
            reverse("shop:sale_create"),
            reverse("shop:finance"), reverse("shop:finance") + "?month=2020-01", reverse("shop:finance") + "?month=bad",
            reverse("shop:income_detail"),
            reverse("shop:worker_payments"), reverse("shop:worker_payments") + "?status=unpaid",
            reverse("shop:clothing_list"), reverse("shop:clothing_list") + "?occasion=wedding&fabric=Lace&quick=recent",
            reverse("shop:style_detail", args=[style.pk]), reverse("shop:style_create"),
            reverse("shop:material_list") + "?sort=used", reverse("shop:material_detail", args=[material.pk]),
            reverse("shop:material_create"), reverse("shop:tibebe_list"), reverse("shop:tibebe_create"),
            reverse("shop:freesize_list"), reverse("shop:freesize_create"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_create_order_with_deposit(self):
        style = Style.objects.get(code="HK-024")
        response = self.client.post(reverse("shop:order_create"), {
            "customer_name": "Hana Abebe", "customer_phone": "+251 911 013 759",
            "style": style.pk, "category": "wedding", "people_count": 1,
            "bust": "95", "shoulder": "40", "waist": "72",
            "due_date": (timezone.localdate() + timedelta(days=20)).isoformat(),
            "priority": "standard", "total_price": "8000", "deposit": "3500",
        })
        order = Order.objects.latest("pk")
        self.assertRedirects(response, reverse("shop:tracker_detail", args=[order.pk]))
        self.assertEqual(order.customer.phone, "0911013759")
        self.assertEqual(order.balance, Decimal("4500"))

    def test_deposit_cannot_exceed_total(self):
        response = self.client.post(reverse("shop:order_create"), {
            "customer_name": "X", "customer_phone": "0911000000", "category": "habesha", "people_count": 1,
            "due_date": (timezone.localdate() + timedelta(days=5)).isoformat(),
            "priority": "standard", "total_price": "1000", "deposit": "2000",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "can&#x27;t be more than the total")

    def test_transfer_closes_task_and_opens_new_one(self):
        order = Order.objects.get(customer__name="Sara Kebede", stage=Stage.CUTTING)
        sewer = Worker.objects.get(name="Abebe")
        self.client.post(reverse("shop:order_transfer", args=[order.pk]), {"worker": sewer.pk, "note": "Short sleeves"})
        order.refresh_from_db()
        self.assertEqual(order.stage, Stage.SEWING)
        self.assertEqual(order.current_worker, sewer)
        self.assertTrue(WorkerTask.objects.filter(order=order, worker__name="Kebede", finished_on__isnull=False).exists())
        self.assertTrue(WorkerTask.objects.filter(order=order, worker=sewer, finished_on__isnull=True).exists())
        self.assertEqual(order.notes.first().text, "Short sleeves")

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
        self.client.post(reverse("shop:order_add_payment", args=[order.pk]), {"amount": str(order.balance + 1)})
        self.assertEqual(Payment.objects.count(), count)
        self.client.post(reverse("shop:order_add_payment", args=[order.pk]), {"amount": str(order.balance)})
        self.assertEqual(order.balance, 0)

    def test_use_material_reduces_stock(self):
        material = Material.objects.get(name="White Chiffon")
        self.client.post(reverse("shop:material_use", args=[material.pk]), {"quantity": "3"})
        material.refresh_from_db()
        self.assertEqual(material.quantity, Decimal("15"))

    def test_mark_ready_then_deliver(self):
        order = Order.objects.get(customer__name="Liya Bekele", stage=Stage.DECORATION)
        self.client.post(reverse("shop:order_mark_ready", args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual(order.stage, Stage.READY)
        self.assertIsNone(order.current_worker)
        self.client.post(reverse("shop:order_deliver", args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual(order.stage, Stage.DELIVERED)
        self.assertEqual(order.delivered_at, timezone.localdate())

    def test_redirect_back_rejects_external_urls(self):
        task = WorkerTask.objects.filter(finished_on__isnull=False, paid_on__isnull=True).first()
        response = self.client.post(reverse("shop:task_mark_paid", args=[task.pk]), {"next": "https://evil.example"})
        self.assertEqual(response["Location"], reverse("shop:worker_payments"))


def _png(name="photo.png", color="red"):
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (8, 10), color).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class StyleGalleryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def setUp(self):
        import shutil
        import tempfile

        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = self.settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)
        self.client.force_login(get_user_model().objects.get(username="selam"))

    def _post_edit(self, style, **extra):
        data = {
            "name": style.name, "category": style.category, "code": style.code, "gender": style.gender,
            "fabric": style.fabric, "color": "Ivory", "fit": "Slim fit", "length": "140 cm",
            "sleeve_length": "Long sleeve", "recommended_sizes": style.recommended_sizes,
            "description": style.description,
        }
        data.update(extra)
        return self.client.post(reverse("shop:style_edit", args=[style.pk]), data)

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
