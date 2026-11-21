from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from two_factor.urls import urlpatterns as two_factor_urls

from atlas.cms_integration import CMSBackupTokensView, CMSSetupView, configure_admin

configure_admin()
two_factor_urls = ([path("account/two_factor/setup/", CMSSetupView.as_view(), name="setup"),
                   path("account/two_factor/backup/tokens/", CMSBackupTokensView.as_view(), name="backup_tokens")]
                  + [p for p in two_factor_urls[0] if p.name not in {"setup", "backup_tokens"}], two_factor_urls[1])

urlpatterns = [
    path("", RedirectView.as_view(url=settings.FRONTEND_URL, permanent=False), name="frontend-home"),
    path("admin/", admin.site.urls),
    path("", include(two_factor_urls)),
    path("api/admin/", include("atlas.cms_urls")),
    path("api/", include("atlas.urls")),
]
