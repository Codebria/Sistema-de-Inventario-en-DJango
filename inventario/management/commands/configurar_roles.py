from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction


CONSULTA = ("view_producto", "view_categoria", "view_movimiento")
OPERACION = ("add_producto", "change_producto", "add_categoria", "change_categoria", "add_movimiento")


class Command(BaseCommand):
    help = "Crea los grupos de inventario Consulta y Operación con sus permisos."

    @transaction.atomic
    def handle(self, *args, **options):
        for nombre, permisos in (
            ("Inventario · Consulta", CONSULTA),
            ("Inventario · Operación", CONSULTA + OPERACION),
        ):
            grupo, _ = Group.objects.get_or_create(name=nombre)
            grupo.permissions.set(Permission.objects.filter(
                content_type__app_label="inventario",
                codename__in=permisos,
            ))
            self.stdout.write(self.style.SUCCESS(nombre))
