"""
Forms for AA-Payout
"""

# Django
from django import forms
from django.core.exceptions import ValidationError

# AA Payout
from aapayout import constants
from aapayout.models import Fleet, FleetParticipant, LootPool


class FleetCreateForm(forms.ModelForm):
    """Form for creating a new fleet"""

    class Meta:
        model = Fleet
        fields = ["name", "battle_report", "notes"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., Wormhole Gank Payout",
                }
            ),
            "battle_report": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://br.evetools.org/... (optional)",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Additional notes about the payout (optional)",
                }
            ),
        }
        help_texts = {
            "battle_report": "Link to zkillboard, evetools, or other battle report",
        }


class FleetEditForm(forms.ModelForm):
    """Form for editing an existing fleet"""

    class Meta:
        model = Fleet
        fields = ["name", "fleet_time", "battle_report", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "fleet_time": forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                }
            ),
            "battle_report": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://br.evetools.org/... (optional)",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                }
            ),
        }


class ParticipantAddForm(forms.ModelForm):
    """Form for adding a participant to a fleet"""

    character_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(
            attrs={
                "class": "form-control character-autocomplete",
                "placeholder": "Start typing character name...",
                "autocomplete": "off",
            }
        ),
        help_text="Type to search for characters in the database",
    )

    is_scout = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_is_scout"}),
        label="Mark as Scout",
        help_text="Scouts receive extra shares (configured per loot pool)",
    )

    class Meta:
        model = FleetParticipant
        fields = ["role", "is_scout"]
        widgets = {
            "role": forms.Select(attrs={"class": "form-select"}),
        }


class ParticipantEditForm(forms.ModelForm):
    """Form for editing a fleet participant"""

    is_scout = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="Mark as Scout",
        help_text="Scouts receive extra shares (configured per loot pool)",
    )

    class Meta:
        model = FleetParticipant
        fields = ["role", "is_scout", "joined_at", "left_at", "notes"]
        widgets = {
            "role": forms.Select(attrs={"class": "form-select"}),
            "joined_at": forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                }
            ),
            "left_at": forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                }
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        joined_at = cleaned_data.get("joined_at")
        left_at = cleaned_data.get("left_at")

        if joined_at and left_at and left_at <= joined_at:
            raise ValidationError("Left time must be after joined time")

        return cleaned_data


class LootPoolCreateForm(forms.ModelForm):
    """Form for creating a loot pool and pasting loot"""

    class Meta:
        model = LootPool
        fields = ["raw_loot_text", "pricing_method", "scout_shares"]
        widgets = {
            "raw_loot_text": forms.Textarea(
                attrs={
                    "class": "form-control font-monospace",
                    "rows": 10,
                    "placeholder": (
                        "Paste loot from EVE client here...\n\n"
                        "Example:\nCompressed Arkonor\t1000\nCompressed Bistot\t500"
                    ),
                }
            ),
            "pricing_method": forms.Select(attrs={"class": "form-select"}),
            "scout_shares": forms.NumberInput(
                attrs={
                    "class": "form-range",
                    "type": "range",
                    "min": "1",
                    "max": "5",
                    "step": "0.5",
                    "id": "scout-bonus-slider-create",
                }
            ),
        }
        help_texts = {
            "raw_loot_text": "Paste items directly from EVE client inventory",
            "scout_shares": "Number of shares scouts receive (1-5, regular = 1 share)",
        }

    def clean_raw_loot_text(self):
        loot_text = self.cleaned_data.get("raw_loot_text", "")
        if not loot_text or not loot_text.strip():
            raise ValidationError("Loot text cannot be empty")
        return loot_text.strip()


class LootPoolEditForm(forms.ModelForm):
    """Form for editing a loot pool's raw text and settings"""

    class Meta:
        model = LootPool
        fields = ["raw_loot_text", "pricing_method", "scout_shares"]
        widgets = {
            "raw_loot_text": forms.Textarea(
                attrs={
                    "class": "form-control font-monospace",
                    "rows": 10,
                    "placeholder": (
                        "Paste loot from EVE client here...\n\n"
                        "Example:\nCompressed Arkonor\t1000\nCompressed Bistot\t500"
                    ),
                }
            ),
            "pricing_method": forms.Select(attrs={"class": "form-select"}),
            "scout_shares": forms.NumberInput(
                attrs={
                    "class": "form-range",
                    "type": "range",
                    "min": "1",
                    "max": "5",
                    "step": "0.5",
                    "id": "scout-bonus-slider-edit",
                }
            ),
        }
        help_texts = {
            "raw_loot_text": "Paste items directly from EVE client inventory",
            "scout_shares": "Number of shares scouts receive (1-5, regular = 1 share)",
        }

    def clean_raw_loot_text(self):
        loot_text = self.cleaned_data.get("raw_loot_text", "")
        if not loot_text or not loot_text.strip():
            raise ValidationError("Loot text cannot be empty")
        return loot_text.strip()


class LootPoolApproveForm(forms.Form):
    """Form for approving a loot pool for payout"""

    confirm = forms.BooleanField(
        label="I confirm these values are correct and ready for payout",
        required=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, loot_pool, *args, **kwargs):
        self.loot_pool = loot_pool
        super().__init__(*args, **kwargs)


class PayoutMarkPaidForm(forms.Form):
    """Form for marking a single payout as paid"""

    payment_method = forms.ChoiceField(
        choices=constants.PAYMENT_METHOD_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
        initial=constants.PAYMENT_METHOD_MANUAL,
    )

    transaction_reference = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Contract ID, transaction reference, etc. (optional)",
            }
        ),
        help_text="Any reference to help track this payment",
    )

    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Additional notes (optional)",
            }
        ),
    )


class BulkPayoutMarkPaidForm(forms.Form):
    """Form for marking multiple payouts as paid"""

    payout_ids = forms.CharField(
        widget=forms.HiddenInput(),
        help_text="Comma-separated list of payout IDs",
    )

    payment_method = forms.ChoiceField(
        choices=constants.PAYMENT_METHOD_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
        initial=constants.PAYMENT_METHOD_MANUAL,
    )

    transaction_reference = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Bulk payment reference (optional)",
            }
        ),
        help_text="Reference for all selected payments",
    )

    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Notes for all selected payments (optional)",
            }
        ),
    )

    def clean_payout_ids(self):
        """Validate and parse payout IDs"""
        ids_str = self.cleaned_data.get("payout_ids", "")
        if not ids_str:
            raise ValidationError("No payouts selected")

        try:
            ids = [int(id_str.strip()) for id_str in ids_str.split(",") if id_str.strip()]
        except ValueError:
            raise ValidationError("Invalid payout IDs")

        if not ids:
            raise ValidationError("No payouts selected")

        return ids
