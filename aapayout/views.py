"""App Views"""

# Django
from django.contrib.auth.decorators import login_required, permission_required
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse
from django.shortcuts import render


@login_required
@permission_required("aapayout.basic_access")
def index(request: WSGIRequest) -> HttpResponse:
    """
    Dashboard view
    :param request:
    :return:
    """

    context = {"text": "Welcome to AA Payout - Fleet Loot Management System"}

    return render(request, "aapayout/index.html", context)
