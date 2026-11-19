from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CategoriaForm, MovimientoForm, ProductoForm
from .models import Categoria, Movimiento, Producto
from .services import registrar_movimiento

STOCK_BAJO = Q(activo=True, stock__lte=F("stock_minimo"))


@login_required
def panel(request):
    if not request.user.has_perm("inventario.view_producto"):
        return render(request, "inventario/sin_acceso.html", status=403)

    activos = Producto.objects.filter(activo=True)
    indicadores = activos.aggregate(
        productos=Count("pk"),
        stock_bajo=Count("pk", filter=Q(stock__lte=F("stock_minimo"))),
        agotados=Count("pk", filter=Q(stock=0)),
    )
    contexto = {
        "indicadores": indicadores,
        "alertas": activos.filter(STOCK_BAJO).select_related("categoria").order_by("stock", "nombre")[:7],
    }
    if request.user.has_perm("inventario.view_categoria"):
        contexto["total_categorias"] = Categoria.objects.count()
    if request.user.has_perm("inventario.view_movimiento"):
        contexto["ultimos_movimientos"] = Movimiento.objects.select_related("producto", "usuario")[:5]
    return render(request, "inventario/panel.html", contexto)


@login_required
@permission_required("inventario.view_producto", raise_exception=True)
def productos(request):
    consulta = request.GET.get("q", "").strip()[:120]
    estado = request.GET.get("estado", "")
    categoria = request.GET.get("categoria", "")
    resultados = Producto.objects.select_related("categoria")
    if consulta:
        resultados = resultados.filter(Q(nombre__icontains=consulta) | Q(sku__icontains=consulta))
    if categoria.isascii() and categoria.isdecimal() and len(categoria) <= 18:
        resultados = resultados.filter(categoria_id=int(categoria))
    if estado == "bajo":
        resultados = resultados.filter(STOCK_BAJO)
    elif estado == "agotado":
        resultados = resultados.filter(activo=True, stock=0)
    elif estado in ("activo", "inactivo"):
        resultados = resultados.filter(activo=estado == "activo")
    return render(request, "inventario/productos.html", {
        "pagina": Paginator(resultados, 15).get_page(request.GET.get("page")),
        "categorias": Categoria.objects.all(),
        "consulta": consulta,
        "estado": estado,
        "categoria_actual": categoria,
    })


@login_required
@permission_required("inventario.add_producto", raise_exception=True)
def crear_producto(request):
    return _formulario_producto(request)


@login_required
@permission_required("inventario.change_producto", raise_exception=True)
def editar_producto(request, pk):
    return _formulario_producto(request, pk)


def _formulario_producto(request, pk=None):
    if request.method == "POST":
        try:
            with transaction.atomic():
                producto = get_object_or_404(Producto.objects.select_for_update(), pk=pk) if pk else None
                formulario = ProductoForm(request.POST, instance=producto)
                if formulario.is_valid():
                    formulario.save()
                    messages.success(request, "Producto guardado.")
                    return redirect("inventario:productos")
        except IntegrityError as error:
            if _restriccion(error) != "producto_sku_ci_unico":
                raise
            formulario.add_error("sku", "Este código SKU ya está registrado.")
    else:
        producto = get_object_or_404(Producto, pk=pk) if pk else None
        formulario = ProductoForm(instance=producto)

    return render(request, "inventario/formulario.html", {
        "form": formulario,
        "titulo": "Editar producto" if pk else "Nuevo producto",
        "seccion": "productos",
        "cancelar": "inventario:productos",
        "ayuda": "Registra una entrada para incorporar las existencias iniciales." if pk is None else "",
        "crear_categoria": request.user.has_perm("inventario.add_categoria") and not Categoria.objects.exists(),
    })


@login_required
@permission_required("inventario.view_categoria", raise_exception=True)
def categorias(request):
    resultados = Categoria.objects.annotate(total_productos=Count("producto")).order_by("nombre", "pk")
    return render(request, "inventario/categorias.html", {
        "pagina": Paginator(resultados, 15).get_page(request.GET.get("page")),
    })


@login_required
@permission_required("inventario.add_categoria", raise_exception=True)
def crear_categoria(request):
    return _formulario_categoria(request)


@login_required
@permission_required("inventario.change_categoria", raise_exception=True)
def editar_categoria(request, pk):
    return _formulario_categoria(request, get_object_or_404(Categoria, pk=pk))


def _formulario_categoria(request, categoria=None):
    formulario = CategoriaForm(request.POST if request.method == "POST" else None, instance=categoria)
    if request.method == "POST" and formulario.is_valid():
        try:
            with transaction.atomic():
                formulario.save()
        except IntegrityError as error:
            if _restriccion(error) != "categoria_nombre_ci_unico":
                raise
            formulario.add_error("nombre", "Ya existe una categoría con este nombre.")
        else:
            messages.success(request, "Categoría guardada.")
            return redirect("inventario:categorias")
    return render(request, "inventario/formulario.html", {
        "form": formulario,
        "titulo": "Editar categoría" if categoria else "Nueva categoría",
        "seccion": "categorias",
        "cancelar": "inventario:categorias",
    })


@login_required
@permission_required("inventario.view_movimiento", raise_exception=True)
def movimientos(request):
    consulta = request.GET.get("q", "").strip()[:120]
    tipo = request.GET.get("tipo", "")
    desde = request.GET.get("desde", "")
    hasta = request.GET.get("hasta", "")
    resultados = Movimiento.objects.select_related("producto", "usuario")
    if consulta:
        resultados = resultados.filter(
            Q(producto__nombre__icontains=consulta) | Q(producto__sku__icontains=consulta)
        )
    if tipo in Movimiento.Tipo.values:
        resultados = resultados.filter(tipo=tipo)
    errores = []
    try:
        inicio = date.fromisoformat(desde) if desde else None
        fin = date.fromisoformat(hasta) if hasta else None
        if inicio and fin and inicio > fin:
            errores.append("La fecha inicial debe ser anterior o igual a la final.")
        else:
            if inicio:
                resultados = resultados.filter(fecha__date__gte=inicio)
            if fin:
                resultados = resultados.filter(fecha__date__lte=fin)
    except ValueError:
        errores.append("Usa fechas válidas para filtrar los movimientos.")
    if errores:
        resultados = resultados.none()
    return render(request, "inventario/movimientos.html", {
        "pagina": Paginator(resultados, 15).get_page(request.GET.get("page")),
        "consulta": consulta,
        "tipo": tipo,
        "desde": desde,
        "hasta": hasta,
        "errores": errores,
    })


@login_required
@permission_required("inventario.add_movimiento", raise_exception=True)
def crear_movimiento(request):
    inicial = request.GET.get("producto", "")
    if not (inicial.isascii() and inicial.isdecimal() and len(inicial) <= 18):
        inicial = None
    formulario = MovimientoForm(
        request.POST if request.method == "POST" else None,
        initial={"producto": inicial},
    )
    if request.method == "POST" and formulario.is_valid():
        try:
            movimiento, creado = registrar_movimiento(usuario=request.user, **formulario.cleaned_data)
        except ValidationError as error:
            formulario.add_error(None, error)
        else:
            mensaje = "Movimiento registrado." if creado else "Este movimiento ya estaba registrado."
            messages.success(request, f"{mensaje} Saldo posterior: {movimiento.saldo}.")
            destino = "inventario:movimientos" if request.user.has_perm("inventario.view_movimiento") else "inventario:panel"
            return redirect(destino)
    return render(request, "inventario/formulario.html", {
        "form": formulario,
        "titulo": "Registrar movimiento",
        "seccion": "movimientos",
        "cancelar": "inventario:movimientos" if request.user.has_perm("inventario.view_movimiento") else "inventario:panel",
        "ayuda": "Indica el producto, la cantidad y el motivo de la entrada o salida.",
    })


def _restriccion(error):
    return getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)
