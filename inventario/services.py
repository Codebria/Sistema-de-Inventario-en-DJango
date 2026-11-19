from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .models import MAX_EXISTENCIAS, Movimiento, Producto


def registrar_movimiento(*, producto, tipo, cantidad, motivo, usuario, operacion):
    """Actualiza el saldo y crea su movimiento en una sola transacción."""
    if tipo not in Movimiento.Tipo.values or not 1 <= cantidad <= MAX_EXISTENCIAS:
        raise ValidationError("Verifica el tipo y la cantidad del movimiento.")

    datos = {
        "producto_id": producto.pk,
        "tipo": tipo,
        "cantidad": cantidad,
        "motivo": motivo,
        "usuario_id": usuario.pk,
    }
    try:
        with transaction.atomic():
            actual = Producto.objects.select_for_update().get(pk=producto.pk)
            existente = Movimiento.objects.filter(operacion=operacion).first()
            if existente:
                return _verificar_reintento(existente, datos)
            if not actual.activo:
                raise ValidationError("El producto está inactivo.")

            variacion = cantidad if tipo == Movimiento.Tipo.ENTRADA else -cantidad
            saldo = actual.stock + variacion
            if saldo < 0:
                raise ValidationError(f"Stock insuficiente. Existencias disponibles: {actual.stock}.")
            if saldo > MAX_EXISTENCIAS:
                raise ValidationError("La entrada supera el límite de existencias permitido.")

            actual.stock = saldo
            actual.save(update_fields=["stock"])
            movimiento = Movimiento.objects.create(operacion=operacion, saldo=saldo, **datos)
    except IntegrityError:
        # El mismo identificador pudo llegar en solicitudes sobre productos distintos.
        existente = Movimiento.objects.filter(operacion=operacion).first()
        if existente is None:
            raise
        return _verificar_reintento(existente, datos)
    return movimiento, True


def _verificar_reintento(movimiento, datos):
    if any(getattr(movimiento, campo) != valor for campo, valor in datos.items()):
        raise ValidationError("El formulario ya se usó para otro movimiento. Abre uno nuevo.")
    return movimiento, False
