from django import forms
from .models import JournalEntry, JournalLine, Account


class JournalEntryForm(forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = ['date', 'description']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-sm'}),
            'description': forms.Textarea(attrs={'rows': 2, 'class': 'form-control form-control-sm'}),
        }


class JournalLineForm(forms.Form):
    account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
    description = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Optional'}),
    )
    debit = forms.DecimalField(
        required=False, max_digits=10, decimal_places=2, initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01'}),
    )
    credit = forms.DecimalField(
        required=False, max_digits=10, decimal_places=2, initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01'}),
    )
