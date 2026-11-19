from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from .models import Categoria, Movimiento, Producto
from .services import registrar_movimiento


class InventarioWebTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser("admin", password="clave-de-prueba")
        cls.categoria = Categoria.objects.create(nombre="Equipos")
        cls.producto = Producto.objects.create(
            sku="TEC-001", nombre="Teclado", categoria=cls.categoria, stock_minimo=5
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_entrada_salida_reintento_y_stock_insuficiente(self):
        ruta = reverse("inventario:crear_movimiento")
        destino = reverse("inventario:movimientos")
        respuesta = self.client.get(ruta, {"producto": self.producto.pk})
        form = respuesta.context["form"]
        self.assertEqual(str(form["producto"].value()), str(self.producto.pk))
        entrada = {
            "producto": self.producto.pk,
            "tipo": "E",
            "cantidad": 10,
            "motivo": "Compra",
            "operacion": form["operacion"].value(),
        }
        self.assertRedirects(self.client.post(ruta, entrada), destino)
        self.assertRedirects(self.client.post(ruta, entrada), destino)
        salida = {**entrada, "tipo": "S", "cantidad": 7, "motivo": "Entrega", "operacion": uuid4()}
        self.assertRedirects(self.client.post(ruta, salida), destino)
        invalida = {**salida, "cantidad": 4, "operacion": uuid4()}
        self.assertContains(self.client.post(ruta, invalida), "Stock insuficiente")
        self.assertContains(self.client.post(ruta, {**entrada, "cantidad": 5}), "formulario ya se usó")
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 3)
        self.assertEqual(list(Movimiento.objects.values_list("saldo", flat=True)), [3, 10])
        self.assertEqual(Movimiento.objects.first().usuario, self.admin)

        movimientos = self.client.get(destino, {"q": "TEC-001", "tipo": "S"})
        self.assertContains(movimientos, "Entrega")
        self.assertNotContains(movimientos, "Compra")

    def test_catalogo_sku_y_alerta_en_stock_minimo(self):
        ruta = reverse("inventario:crear_producto")
        datos = {
            "sku": "tec-001", "nombre": "Otro teclado", "categoria": self.categoria.pk,
            "unidad": "unidad", "stock_minimo": 2, "activo": "on",
        }
        respuesta = self.client.post(ruta, datos)
        self.assertTrue(respuesta.context["form"].errors)
        self.assertRedirects(
            self.client.post(ruta, {**datos, "sku": "tec-002"}),
            reverse("inventario:productos"),
        )
        nuevo = Producto.objects.get(sku="TEC-002")
        self.assertEqual(nuevo.stock, 0)
        registrar_movimiento(
            producto=self.producto, tipo="E", cantidad=5, motivo="Compra",
            usuario=self.admin, operacion=uuid4(),
        )
        panel = self.client.get(reverse("inventario:panel"))
        self.assertEqual(panel.context["indicadores"], {"productos": 2, "stock_bajo": 2, "agotados": 1})
        filtrados = self.client.get(reverse("inventario:productos"), {"estado": "bajo", "q": "TEC-001"})
        self.assertContains(filtrados, "Teclado")
        self.assertNotContains(filtrados, "Otro teclado")

    def test_edicion_preserva_stock_y_rechaza_desactivar_con_existencias(self):
        registrar_movimiento(
            producto=self.producto, tipo="E", cantidad=5, motivo="Compra",
            usuario=self.admin, operacion=uuid4(),
        )
        ruta = reverse("inventario:editar_producto", args=[self.producto.pk])
        datos = {
            "sku": self.producto.sku, "nombre": "Teclado USB", "categoria": self.categoria.pk,
            "unidad": "unidad", "stock_minimo": 1, "stock": 999,
        }
        self.assertContains(self.client.post(ruta, datos), "Registra las salidas pendientes")
        self.assertRedirects(
            self.client.post(ruta, {**datos, "activo": "on"}), reverse("inventario:productos")
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 5)

    def test_usuario_de_consulta_y_sesion(self):
        call_command("configurar_roles", verbosity=0)
        usuario = get_user_model().objects.create_user("consulta")
        usuario.groups.add(Group.objects.get(name="Inventario · Consulta"))
        self.client.logout()
        ruta = reverse("inventario:panel")
        self.assertRedirects(self.client.get(ruta), reverse("login") + "?next=/")
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(ruta).status_code, 200)
        self.assertEqual(self.client.post(reverse("inventario:crear_movimiento"), {}).status_code, 403)
        self.assertRedirects(self.client.post(reverse("logout")), reverse("login"))

    def test_categoria_duplicada_y_fechas_invalidas(self):
        ruta = reverse("inventario:crear_categoria")
        self.assertTrue(self.client.post(ruta, {"nombre": "equipos"}).context["form"].errors)
        self.assertRedirects(
            self.client.post(ruta, {"nombre": "Accesorios"}), reverse("inventario:categorias")
        )
        respuesta = self.client.get(reverse("inventario:movimientos"), {
            "desde": "2026-11-18", "hasta": "2026-11-17",
        })
        self.assertContains(respuesta, "La fecha inicial debe ser anterior o igual a la final.")


class ExistenciasConcurrentesTests(TransactionTestCase):
    def test_solo_una_salida_puede_consumir_el_mismo_stock(self):
        usuario = get_user_model().objects.create_user("almacen")
        categoria = Categoria.objects.create(nombre="Accesorios")
        producto = Producto.objects.create(sku="MIC-001", nombre="Micrófono", categoria=categoria)
        registrar_movimiento(
            producto=producto, tipo="E", cantidad=10, motivo="Ingreso",
            usuario=usuario, operacion=uuid4(),
        )
        iniciar_juntos = Barrier(2)

        def retirar():
            try:
                iniciar_juntos.wait(timeout=5)
                registrar_movimiento(
                    producto=producto, tipo="S", cantidad=6, motivo="Entrega",
                    usuario=usuario, operacion=uuid4(),
                )
            except ValidationError as error:
                self.assertIn("Stock insuficiente", error.messages[0])
                return False
            finally:
                connections.close_all()
            return True

        with ThreadPoolExecutor(max_workers=2) as executor:
            solicitudes = [executor.submit(retirar) for _ in range(2)]
            self.assertCountEqual([solicitud.result(timeout=10) for solicitud in solicitudes], [True, False])
        producto.refresh_from_db()
        self.assertEqual(producto.stock, 4)
        self.assertEqual(Movimiento.objects.filter(tipo="S").count(), 1)
