"""Load demo data that mirrors the mockups so every screen has something to show.

    python manage.py seed_demo          # first time
    python manage.py seed_demo --reset  # wipe shop data and load again
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from shop.models import (
    Activity, Customer, FreeSizeItem, Material, MaterialUsage, Order, Payment,
    Sale, StaffProfile, Stage, StageNote, Style, Tibebe, Worker, WorkerTask,
)

D = Decimal

# Color, fit and lengths shown in the style page's details grid.
STYLE_DETAILS = {
    "HK-024": {"color": "White and gold", "fit": "Flowing", "length": "Floor length", "sleeve_length": "Long sleeve"},
    "HK-012": {"color": "White, green and gold", "fit": "Relaxed", "length": "Ankle length", "sleeve_length": "Long sleeve"},
    "WD-015": {"color": "Ivory", "fit": "Fitted bodice", "length": "Floor length", "sleeve_length": "Off-shoulder"},
    "MF-006": {"color": "Cream", "fit": "Loose", "length": "Ankle length", "sleeve_length": "Bell sleeve"},
    "MN-006": {"color": "White and purple", "fit": "Regular fit", "length": "Shirt to hip", "sleeve_length": "Long sleeve"},
    "CH-003": {"color": "White and green", "fit": "Loose", "length": "Knee length", "sleeve_length": "Short sleeve"},
    "MF-011": {"color": "White and gold", "fit": "Fitted bodice, full skirt", "length": "Ankle length", "sleeve_length": "Three-quarter"},
}


class Command(BaseCommand):
    help = "Load demo data for the tailor shop (owner selam / selam1234, messenger dawit / dawit1234)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing shop data first.")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            for model in (Activity, Sale, MaterialUsage, Payment, WorkerTask, StageNote, Order,
                          Customer, Tibebe, Material, FreeSizeItem, Style, Worker):
                model.objects.all().delete()
        elif Style.objects.exists():
            self.stdout.write(self.style.WARNING("Demo data is already loaded. Use --reset to load it again."))
            return

        random.seed(7)
        self.today = timezone.localdate()
        self.now = timezone.now()

        User = get_user_model()
        if not User.objects.filter(username="selam").exists():
            owner = User.objects.create_superuser("selam", "selam@example.com", "selam1234", first_name="Selam")
            StaffProfile.objects.create(user=owner, role=StaffProfile.Role.OWNER)
        if not User.objects.filter(username="dawit").exists():
            messenger = User.objects.create_user("dawit", password="dawit1234", first_name="Dawit")
            StaffProfile.objects.create(user=messenger, role=StaffProfile.Role.MESSENGER, phone="0918223344")

        workers = self._workers()
        styles = self._styles()
        self._materials(styles)
        self._tibebe()
        items = self._free_size()
        self._orders(workers, styles)
        self._sales(items)
        self._activity()
        self.stdout.write(self.style.SUCCESS("Demo data loaded. Sign in as selam / selam1234 (owner) or dawit / dawit1234 (messenger)."))

    # ------------------------------------------------------------------ helpers
    def _ago(self, days, hour=10, minute=0):
        moment = timezone.localtime(self.now) - timedelta(days=days)
        return moment.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def _workers(self):
        data = [
            ("Almaz", "sewing", 600, "0911223344"), ("Abebe", "sewing", 550, "0911556677"),
            ("Kebede", "cutting", 400, "0912334455"), ("Nahom", "repair", 300, "0913445566"),
            ("Mimi", "repair", 300, "0914556677"), ("Bertukan", "repair", 280, "0915667788"),
            ("Tigist", "decoration", 700, "0916778899"), ("Hiwot", "quality", 250, "0917889900"),
        ]
        return {n: Worker.objects.create(name=n, role=r, rate_per_task=D(rate), phone=p) for n, r, rate, p in data}

    def _styles(self):
        data = [
            ("HK-024", "Golden Wedding Kemis", "wedding", "women", "Cotton",
             "Traditional white dress with gold embroidery and long sleeves.", "Medium, Large", True),
            ("HK-012", "Classic Habesha Kemis", "habesha", "women", "Cotton",
             "Hand-woven cotton kemis with a green and gold tibebe down the front.", "Small, Medium, Large", True),
            ("WD-015", "Ivory Lace Gown", "wedding", "women", "Lace",
             "Off-shoulder lace gown with a soft gold border at the hem.", "Small, Medium", False),
            ("MF-006", "Modern Fusion Dress", "modern", "women", "Chiffon",
             "Long chiffon dress with a light shawl and modern sleeves.", "Medium", False),
            ("MN-006", "Men's Habesha Clothes", "men", "men", "Cotton",
             "Men's shirt and trousers with a purple woven chest panel.", "Medium, Large, XL", False),
            ("CH-003", "Children's Festive Kemis", "children", "children", "Cotton",
             "Holiday kemis for girls aged 4–10 with a matching netela.", "Age 4–6, Age 7–10", True),
            ("MF-011", "Two-Tone Modern Kemis", "modern", "women", "Chiffon",
             "Full skirt with three gold bands and a fitted bodice.", "Small, Medium, Large", False),
        ]
        styles = {}
        for i, (code, name, cat, gender, fabric, desc, sizes, popular) in enumerate(data):
            styles[code] = Style.objects.create(
                code=code, name=name, category=cat, gender=gender, fabric=fabric, description=desc,
                recommended_sizes=sizes, is_popular=popular, created_at=self._ago(90 - i * 8),
                **STYLE_DETAILS.get(code, {}),
            )
        return styles

    def _materials(self, styles):
        data = [
            ("White Cotton", "fabric", 500, 12, "meters", 5, ["HK-024", "HK-012"]),
            ("Gold Thread", "thread", 600, 8, "spools", 3, ["HK-024"]),
            ("Gold Buttons", "buttons", 700, 24, "pieces", 10, ["MN-006"]),
            ("Gold Embroidery", "embroidery", 850, 2, "meters", 3, ["HK-024", "MF-011"]),
            ("Cathedral Lace", "lace", 500, 0, "meters", 3, ["WD-015"]),
            ("White Chiffon", "fabric", 500, 18, "meters", 5, ["MF-006", "MF-011"]),
            ("White Thread", "thread", 500, 40, "spools", 5, []),
            ("Pearl Buttons", "buttons", 500, 6, "pieces", 10, ["WD-015"]),
        ]
        for i, (name, kind, price, qty, unit, low, used) in enumerate(data):
            m = Material.objects.create(
                name=name, material_type=kind, price=D(price), quantity=D(qty), unit=unit,
                low_stock_at=D(low), created_at=self._ago(60 - i),
            )
            m.used_for.set([styles[c] for c in used])

    def _tibebe(self):
        cotton = Material.objects.get(name="White Cotton")
        data = [
            ("TB-024", "Soft Cotton Onesie Kemis", "thin", "Everyday"),
            ("TB-007", "Large Cotton Kemis", "large", "Holiday"),
            ("TB-012", "White Embroidered Kemis", "medium", "Wedding"),
            ("TB-013", "Gold Kemis", "large", "Traditional"),
            ("TB-019", "Festive Holiday Kemis", "medium", "Holiday"),
            ("TB-021", "Formal Teen Kemis", "thin", "Formal"),
        ]
        for code, name, size, occasion in data:
            Tibebe.objects.create(code=code, name=name, size=size, occasion=occasion, material=cotton)

    def _free_size(self):
        data = [
            ("FS-024", "White kemis", 2500, 2), ("FS-031", "Gold kemis", 1800, 1),
            ("FS-027", "Gold kemis (short)", 1800, 6), ("FS-035", "Black shawl", 1200, 9),
            ("FS-040", "Children's kemis", 1500, 5),
        ]
        return [FreeSizeItem.objects.create(code=c, name=n, price=D(p), quantity=q) for c, n, p, q in data]

    def _order(self, name, phone, style, *, people=1, created_ago=10, due_in=10, stage=Stage.SEWING,
               worker=None, total=8000, deposit=3000, urgent=False, delivered_ago=None):
        customer, _ = Customer.objects.get_or_create(phone=phone, defaults={"name": name})
        order = Order.objects.create(
            customer=customer, style=style, category=style.category, people_count=people,
            bust=D(random.randint(84, 104)), shoulder=D(random.randint(37, 43)),
            sleeve_length=D(random.randint(55, 62)), waist=D(random.randint(64, 86)),
            hip=D(random.randint(92, 112)), dress_length=D(random.randint(132, 148)),
            due_date=self.today + timedelta(days=due_in), total_price=D(total),
            priority="urgent" if urgent else "standard", stage=stage, current_worker=worker,
            stage_started_at=self._ago(2), expected_finish=self.today + timedelta(days=3) if worker else None,
            delivered_at=self.today - timedelta(days=delivered_ago) if delivered_ago is not None else None,
            created_at=self._ago(created_ago),
        )
        Payment.objects.create(order=order, amount=D(deposit), note="Deposit",
                               paid_on=self.today - timedelta(days=created_ago))
        return order

    def _task(self, order, worker, start_ago, end_ago=None, paid_ago=None):
        WorkerTask.objects.create(
            worker=worker, order=order, stage=worker.role, amount=worker.rate_per_task,
            started_on=self.today - timedelta(days=start_ago),
            finished_on=self.today - timedelta(days=end_ago) if end_ago is not None else None,
            paid_on=self.today - timedelta(days=paid_ago) if paid_ago is not None else None,
        )

    def _orders(self, w, s):
        # Delivered orders spread over the past two months (fills the finance chart).
        past = [
            ("Hana Tesfaye", "0911013758", "HK-024", 58, 47, 9000, 4000, 1),
            ("Hana Tesfaye", "0911013758", "MF-011", 50, 40, 6000, 2500, 1),
            ("Hana Tesfaye", "0911013758", "CH-003", 44, 33, 3500, 1500, 1),
            ("Sara Kebede", "0912345678", "HK-012", 36, 26, 6000, 3000, 2),
            ("Meseret Alemayehu", "0916789012", "WD-015", 30, 19, 12000, 5000, 1),
            ("Liya Bekele", "0917890123", "MF-006", 24, 12, 7000, 2500, 1),
            ("Frehiwot Alemu", "0918901234", "MF-011", 18, 6, 5500, 2000, 1),
            ("Selamawit Girma", "0919012345", "HK-012", 14, 2, 6500, 3000, 1),
        ]
        for name, phone, code, created, delivered, total, dep, people in past:
            o = self._order(name, phone, s[code], people=people, created_ago=created, due_in=-delivered,
                            stage=Stage.DELIVERED, total=total, deposit=dep, delivered_ago=delivered)
            Payment.objects.create(order=o, amount=D(total - dep), note="Balance",
                                   paid_on=self.today - timedelta(days=delivered))
            mid = (created + delivered) // 2
            self._task(o, w["Kebede"], created - 1, mid + 2, paid_ago=max(delivered - 1, 0) if delivered > 4 else None)
            sewer = w["Almaz"] if created % 2 else w["Abebe"]
            self._task(o, sewer, mid + 2, delivered + 1, paid_ago=delivered if delivered > 4 else None)

        # Active orders.
        hana = self._order("Hana Tesfaye", "0911013758", s["HK-024"], people=3, created_ago=12, due_in=15,
                           stage=Stage.SEWING, worker=w["Almaz"], total=8000, deposit=3500)
        self._task(hana, w["Kebede"], 8, 4, paid_ago=3)
        self._task(hana, w["Almaz"], 2)
        for text, who, ago in [("Waiting for repair approval.", "Patch repairer", 9),
                               ("Embroidery pattern chosen.", "Decoration specialist", 7),
                               ("Need sleeve adjustment.", "Almaz · tailor", 1)]:
            StageNote.objects.create(order=hana, text=text, author=who, created_at=self._ago(ago))

        sara = self._order("Sara Kebede", "0912345678", s["HK-012"], created_ago=9, due_in=0,
                           stage=Stage.CUTTING, worker=w["Kebede"], total=6000, deposit=3000)
        self._task(sara, w["Kebede"], 1)

        samri = self._order("Samriwit Getu", "0913456789", s["MF-006"], people=4, created_ago=4, due_in=24,
                            stage=Stage.CUTTING, worker=w["Kebede"], total=9500, deposit=4000)
        self._task(samri, w["Kebede"], 2)

        yordi = self._order("Yordanos Fikre", "0914567890", s["WD-015"], people=2, created_ago=20, due_in=7,
                            stage=Stage.READY, total=12000, deposit=6000)
        self._task(yordi, w["Kebede"], 18, 15, paid_ago=14)
        self._task(yordi, w["Abebe"], 15, 6)
        self._task(yordi, w["Hiwot"], 6, 0)

        beti = self._order("Bethlehem Alemu", "0915678901", s["CH-003"], people=5, created_ago=21, due_in=-2,
                           stage=Stage.REPAIR, worker=w["Mimi"], total=4500, deposit=2000, urgent=True)
        self._task(beti, w["Kebede"], 19, 16, paid_ago=15)
        self._task(beti, w["Almaz"], 16, 5)
        self._task(beti, w["Mimi"], 5)
        StageNote.objects.create(order=beti, text="Hem too long on two dresses.", author="Hiwot · quality check",
                                 created_at=self._ago(5))

        mesi = self._order("Meseret Alemayehu", "0916789012", s["HK-024"], created_ago=15, due_in=0,
                           stage=Stage.QUALITY, worker=w["Hiwot"], total=7000, deposit=2500)
        self._task(mesi, w["Kebede"], 13, 10, paid_ago=9)
        self._task(mesi, w["Abebe"], 10, 0)
        self._task(mesi, w["Hiwot"], 0)

        liya = self._order("Liya Bekele", "0917890123", s["WD-015"], created_ago=16, due_in=0,
                           stage=Stage.DECORATION, worker=w["Tigist"], total=11000, deposit=5000, urgent=True)
        self._task(liya, w["Kebede"], 14, 11, paid_ago=10)
        self._task(liya, w["Almaz"], 11, 4)
        self._task(liya, w["Tigist"], 3)

        self._order("Frehiwot Alemu", "0918901234", s["MF-011"], created_ago=1, due_in=30,
                    stage=Stage.MEASURED, total=5500, deposit=2000)

        cotton = Material.objects.get(name="White Cotton")
        MaterialUsage.objects.create(material=cotton, quantity=D(3), order=hana, created_at=self._ago(4))
        MaterialUsage.objects.create(material=cotton, quantity=D("2.5"), order=sara, created_at=self._ago(1))

    def _sales(self, items):
        names = ["", "", "Hana", "", "Rahel", "", "Tsion", ""]
        for day in range(0, 21):
            for _ in range(random.choice([0, 1, 1, 2])):
                item = random.choice(items)
                qty = random.choice([1, 1, 1, 2])
                Sale.objects.create(
                    item=item, quantity=qty, amount=item.price * qty,
                    status="pending" if random.random() < 0.15 else "paid",
                    customer_name=random.choice(names),
                    created_at=self._ago(day, hour=random.randint(9, 18), minute=random.choice([0, 10, 20, 40])),
                )
        # A couple of sales today, like the mockup.
        Sale.objects.create(item=items[0], quantity=2, amount=D(5000), status="pending", customer_name="Hana",
                            created_at=self._ago(0, 9, 20))
        Sale.objects.create(item=items[3], quantity=1, amount=D(1200), status="paid", created_at=self._ago(0, 9, 10))

    def _activity(self):
        for text, days, hour, minute in [
            ("Payment recorded · Almaz", 1, 17, 30),
            ("Hana Tesfaye's order moved to sewing · Almaz", 0, 8, 20),
            ("Sale recorded · FS-024", 0, 9, 21),
        ]:
            Activity.objects.create(text=text, created_at=self._ago(days, hour, minute))
