from django.conf.urls import url
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    url(r'^$', views.dashboard),
    url(r'^directions/multiprint$', views.dir_multiprint),
    url(r'^direction/info$', views.direction_info),
    url(r'^biomaterial/get$', views.researches_control),
    url(r'^create_user$', views.create_user),
    url(r'^from$', views.dashboard_from),
    url(r'^create_podr$', views.create_pod),
    url(r'^ldap_sync$', views.ldap_sync),
    url(r'^directions$', views.directions),
    url(r'^receive/journal_form$', views.receive_journal_form),
    url(r'^view_log$', views.view_log),
    url(r'^confirm_reset$$', views.confirm_reset),
    url(r'^view_logs$', views.load_logs),
    url(r'^users/count$', views.users_count),
    url(r'^users/ldap/dosync$', views.users_dosync),
    url(r'^results_history$', views.results_history), #TemplateView.as_view(template_name="dashboard/results_history.html")),
    url(r'^results_fastprint$', TemplateView.as_view(template_name="dashboard/results_fastprint.html", )),
    url(r'^utils$', TemplateView.as_view(template_name="dashboard/utils.html", )),
    url(r'^results_history/search$', views.results_history_search),
    url(r'^change_password$', views.change_password),
    url(r'^update_pass$', views.update_pass),
    url(r'^discharge$', views.discharge),
    url(r'^discharge/send$', views.discharge_add),
    url(r'^discharge/search$', views.discharge_search),
    url(r'^researches_from_directions$', views.researches_from_directions),
]
