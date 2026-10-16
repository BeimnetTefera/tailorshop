from django.urls import path

from . import views

app_name = "shop"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("account/", views.account, name="account"),
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

    path("sales/", views.sales_history, name="sales_history"),
    path("sales/new/", views.sale_create, name="sale_create"),
    path("sales/<int:pk>/paid/", views.sale_mark_paid, name="sale_mark_paid"),

    path("finance/", views.finance, name="finance"),
    path("finance/income/", views.income_detail, name="income_detail"),

    path("payments/", views.worker_payments, name="worker_payments"),
    path("payments/<int:pk>/paid/", views.task_mark_paid, name="task_mark_paid"),

    path("inventory/", views.clothing_list, name="clothing_list"),
    path("inventory/styles/new/", views.style_create, name="style_create"),
    path("inventory/styles/<int:pk>/", views.style_detail, name="style_detail"),
    path("inventory/styles/<int:pk>/edit/", views.style_edit, name="style_edit"),
    path("inventory/materials/", views.material_list, name="material_list"),
    path("inventory/materials/new/", views.material_create, name="material_create"),
    path("inventory/materials/<int:pk>/", views.material_detail, name="material_detail"),
    path("inventory/materials/<int:pk>/edit/", views.material_edit, name="material_edit"),
    path("inventory/materials/<int:pk>/add-stock/", views.material_add_stock, name="material_add_stock"),
    path("inventory/materials/<int:pk>/use/", views.material_use, name="material_use"),
    path("inventory/tibebe/", views.tibebe_list, name="tibebe_list"),
    path("inventory/tibebe/new/", views.tibebe_create, name="tibebe_create"),
    path("inventory/tibebe/<int:pk>/", views.tibebe_detail, name="tibebe_detail"),
    path("inventory/tibebe/<int:pk>/edit/", views.tibebe_edit, name="tibebe_edit"),
    path("inventory/free-size/", views.freesize_list, name="freesize_list"),
    path("inventory/free-size/new/", views.freesize_create, name="freesize_create"),
    path("inventory/free-size/<int:pk>/edit/", views.freesize_edit, name="freesize_edit"),
]
