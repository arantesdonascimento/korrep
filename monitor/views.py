from django.views.generic import TemplateView

from .services import get_public_stats


class HomeView(TemplateView):
    """The existing home page; only adds the public, aggregate subscriber numbers."""

    template_name = 'index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        stats = get_public_stats()
        context['public_stats'] = stats
        context['subscriber_count'] = stats.total
        return context
