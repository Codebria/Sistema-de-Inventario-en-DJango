from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

MAX_EXISTENCIAS = 2_147_483_647


class Categoria(models.Model):
    nombre = models.CharField("nombre", max_length=80)

    class Meta:
        ordering = ["nombre", "pk"]
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        constraints = [
            models.UniqueConstraint(Lower("nombre"), name="categoria_nombre_ci_unico"),
        ]

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    sku = models.CharField("código SKU", max_length=32)
    nombre = models.CharField("nombre", max_length=120)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, verbose_name="categoría")
    unidad = models.CharField("unidad de medida", max_length=24, default="unidad")
    stock = models.PositiveIntegerField("existencias", default=0, editable=False)
    stock_minimo = models.PositiveIntegerField("stock mínimo", default=0)
    activo = models.BooleanField("producto activo", default=True)

    class Meta:
        ordering = ["nombre", "pk"]
        constraints = [
            models.UniqueConstraint(Lower("sku"), name="producto_sku_ci_unico"),
            models.CheckConstraint(condition=models.Q(activo=True) | models.Q(stock=0),
                                   name="producto_inactivo_sin_stock"),
        ]

    def __str__(self):
        return f"{self.sku} · {self.nombre}"

    @property
    def stock_bajo(self):
        return self.activo and self.stock <= self.stock_minimo


class Movimiento(models.Model):
    class Tipo(models.TextChoices):
        ENTRADA = "E", "Entrada"
        SALIDA = "S", "Salida"

    operacion = models.UUIDField(unique=True, editable=False)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=1, choices=Tipo)
    cantidad = models.PositiveIntegerField()
    saldo = models.PositiveIntegerField("saldo posterior")
    motivo = models.CharField(max_length=200)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(cantidad__gt=0), name="movimiento_cantidad_positiva"),
            models.CheckConstraint(condition=models.Q(tipo__in=["E", "S"]), name="movimiento_tipo_valido"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.producto} · {self.cantidad}"
