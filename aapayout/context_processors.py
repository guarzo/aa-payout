"""
Context processors for AA-Payout
"""


def fc_character(request):
    """
    Add FC character information to template context

    This makes the FC character available in all templates.
    """
    context = {}

    if request.user.is_authenticated:
        # Initialize FC character from session if not set
        if "fc_character_id" not in request.session:
            # Default to main character if available
            if hasattr(request.user, "profile") and request.user.profile.main_character:
                main_char = request.user.profile.main_character
                request.session["fc_character_id"] = main_char.character_id
                request.session["fc_character_name"] = main_char.character_name

        context["fc_character_id"] = request.session.get("fc_character_id")
        context["fc_character_name"] = request.session.get("fc_character_name")

    return context
