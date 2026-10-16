from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "shop"


def _moved(name):
    return RedirectView.as_view(pattern_name=name, permanent=True)


urlpatterns = [
    # Old addresses from earlier versions of the demo, kept so bookmarks still work.
    path("inventory/", _moved("shop:clothing_list")),
    path("inventory/free-size/", _moved("shop:readymade")),
    path("stock/materials/", _moved("shop:material_list")),
    path("finance/", _moved("shop:finance")),
    path("payments/", _moved("shop:worker_payments")),

    path("", views.dashboard, name="dashboard"),
    path("language/", views.set_language, name="set_language"),
    path("account/", views.account, name="account"),
    path("manage/", views.manage, name="manage"),
    path("messengers/", views.messenger_list, name="messenger_list"),
    path("messengers/<int:pk>/", views.messenger_edit, name="messenger_edit"),
    path("team/", views.team, name="team"),
    path("team/<int:pk>/edit/", views.worker_edit, name="worker_edit"),

    path("orders/", views.order_list, name="order_list"),
    path("orders/new/", views.order_create, name="order_create"),
    path("orders/<int:pk>/edit/", views.order_edit, name="order_edit"),
    path("orders/<int:pk>/ready/", views.order_mark_ready, name="order_mark_ready"),
    path("orders/<int:pk>/deliver/", views.order_deliver, name="order_deliver"),

    path("tracker/", views.tracker, name="tracker"),
    path("tracker/<int:pk>/", views.tracker, name="tracker_detail"),
    path("tracker/<int:pk>/transfer/", views.order_transfer, name="order_transfer"),
    path("tracker/<int:pk>/stage/", views.order_update_stage, name="order_update_stage"),
    path("tracker/<int:pk>/note/", views.order_add_note, name="order_add_note"),
    path("tracker/<int:pk>/payment/", views.order_add_payment, name="order_add_payment"),

    # Collection: ready-made pieces and the design gallery.
    path("ready-made/", views.readymade, name="readymade"),
    path("ready-made/new/", views.freesize_create, name="freesize_create"),
    path("ready-made/<int:pk>/", views.readymade_detail, name="readymade_detail"),
    path("ready-made/<int:pk>/edit/", views.freesize_edit, name="freesize_edit"),
    path("gallery/", views.clothing_list, name="clothing_list"),
    path("gallery/new/", views.style_create, name="style_create"),
    path("gallery/<int:pk>/", views.style_detail, name="style_detail"),
    path("gallery/<int:pk>/edit/", views.style_edit, name="style_edit"),
    path("sales/", views.sales_history, name="sales_history"),
    path("sales/new/", views.sale_create, name="sale_create"),
    path("sales/<int:pk>/paid/", views.sale_mark_paid, name="sale_mark_paid"),

    path("money/", views.finance, name="finance"),
    path("money/income/", views.income_detail, name="income_detail"),
    path("money/workers/", views.worker_payments, name="worker_payments"),
    path("money/workers/<int:pk>/paid/", views.task_mark_paid, name="task_mark_paid"),

    # Stock: raw materials.
    path("stock/", views.material_list, name="material_list"),
    path("stock/new/", views.material_create, name="material_create"),
    path("stock/categories/", views.material_categories, name="material_categories"),
    path("stock/<int:pk>/", views.material_detail, name="material_detail"),
    path("stock/<int:pk>/edit/", views.material_edit, name="material_edit"),
    path("stock/<int:pk>/add-stock/", views.material_add_stock, name="material_add_stock"),
    path("stock/<int:pk>/use/", views.material_use, name="material_use"),
]
