from django import forms


class ApproveForm(forms.Form):
    allow_errors = forms.BooleanField(required=False)
    allow_overwrite_edits = forms.BooleanField(required=False)


class RejectForm(forms.Form):
    notes = forms.CharField(required=False)


class RevisionForm(forms.Form):
    notes = forms.CharField()
    targets = forms.CharField(required=False, help_text="Comma-separated section/exercise ids")

    def clean_targets(self) -> list[str]:
        raw: str = self.cleaned_data["targets"]
        return [t.strip() for t in raw.split(",") if t.strip()]
