from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import include, path

from inventario.forms import FormularioAcceso

admin.site.site_header = "Administración de Inventario"
admin.site.site_title = "Inventario"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("ingresar/", LoginView.as_view(authentication_form=FormularioAcceso, redirect_authenticated_user=True), name="login"),
    path("salir/", LogoutView.as_view(), name="logout"),
    path("", include("inventario.urls")),
]
