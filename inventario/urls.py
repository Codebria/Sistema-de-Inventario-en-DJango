from django.urls import path

from . import views

app_name = "inventario"

urlpatterns = [
    path("", views.panel, name="panel"),
    path("productos/", views.productos, name="productos"),
    path("productos/nuevo/", views.crear_producto, name="crear_producto"),
    path("productos/<int:pk>/editar/", views.editar_producto, name="editar_producto"),
    path("categorias/", views.categorias, name="categorias"),
    path("categorias/nueva/", views.crear_categoria, name="crear_categoria"),
    path("categorias/<int:pk>/editar/", views.editar_categoria, name="editar_categoria"),
    path("movimientos/", views.movimientos, name="movimientos"),
    path("movimientos/nuevo/", views.crear_movimiento, name="crear_movimiento"),
]
