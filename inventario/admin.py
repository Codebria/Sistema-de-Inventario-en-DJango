from django.contrib import admin

from .models import Categoria, Movimiento, Producto


class InventarioConsultaAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Categoria)
class CategoriaAdmin(InventarioConsultaAdmin):
    search_fields = ["nombre"]


@admin.register(Producto)
class ProductoAdmin(InventarioConsultaAdmin):
    list_display = ["sku", "nombre", "categoria", "stock", "activo"]
    search_fields = ["sku", "nombre"]
    list_filter = ["activo", "categoria"]


@admin.register(Movimiento)
class MovimientoAdmin(InventarioConsultaAdmin):
    list_display = ["producto", "tipo", "cantidad", "saldo", "usuario", "fecha"]
    list_filter = ["tipo"]
    search_fields = ["producto__sku", "producto__nombre", "motivo"]
