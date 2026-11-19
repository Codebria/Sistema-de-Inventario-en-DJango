from uuid import uuid4

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import MAX_EXISTENCIAS, Categoria, Movimiento, Producto


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "form-check-input"
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = "form-select"
            elif not widget.is_hidden:
                widget.attrs["class"] = "form-control"


class FormularioAcceso(BootstrapFormMixin, AuthenticationForm):
    pass


class ProductoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Producto
        fields = ["sku", "nombre", "categoria", "unidad", "stock_minimo", "activo"]
        help_texts = {"activo": "El producto puede desactivarse cuando sus existencias llegan a cero."}

    def clean_sku(self):
        return self.cleaned_data["sku"].upper()

    def clean_activo(self):
        activo = self.cleaned_data["activo"]
        if not activo and self.instance.stock:
            raise forms.ValidationError("Registra las salidas pendientes antes de desactivar el producto.")
        return activo


class CategoriaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nombre"]


class MovimientoForm(BootstrapFormMixin, forms.Form):
    producto = forms.ModelChoiceField(queryset=Producto.objects.all(), empty_label="Selecciona un producto")
    tipo = forms.ChoiceField(choices=[("", "Selecciona el tipo"), *Movimiento.Tipo.choices])
    cantidad = forms.IntegerField(min_value=1, max_value=MAX_EXISTENCIAS)
    motivo = forms.CharField(max_length=200, widget=forms.Textarea(attrs={"rows": 3}))
    operacion = forms.UUIDField(widget=forms.HiddenInput, initial=uuid4)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["producto"].queryset = Producto.objects.filter(activo=True)
