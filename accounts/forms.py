from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User


class ExhibitorRegistrationForm(UserCreationForm):
    company_name = forms.CharField(max_length=200, required=True, label='Company/Trading Name')
    company_reg_number = forms.CharField(max_length=50, required=False, label='Company Registration Number', help_text='e.g. 2018/123456/07')
    vat_number = forms.CharField(max_length=50, required=False, label='VAT Number', help_text='Leave blank if not VAT registered')
    phone = forms.CharField(max_length=20, required=True, label='Phone Number')
    address = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=True, label='Physical Address')
    proof_of_address = forms.FileField(required=True, label='Proof of Address', help_text='Upload a PDF, JPG, or PNG file (max 5MB)')
    photo = forms.ImageField(
        required=True,
        label='Passport Photo (Selfie)',
        help_text='Upload a clear, recent selfie following passport photo requirements: plain white or light background, face fully visible and centred, eyes open, no sunglasses, hat or head covering (except for religious reasons), no filters, and high resolution. JPG or PNG only (max 5MB).',
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'company_name', 'company_reg_number', 'vat_number', 'phone', 'address', 'proof_of_address', 'photo', 'password1', 'password2']

    def clean_photo(self):
        f = self.cleaned_data.get('photo')
        if f:
            if f.size > 5 * 1024 * 1024:
                raise forms.ValidationError('File size must be under 5MB.')
            ext = f.name.rsplit('.', 1)[-1].lower()
            if ext not in ('jpg', 'jpeg', 'png'):
                raise forms.ValidationError('Only JPG or PNG image files are accepted.')
        return f

    def clean_proof_of_address(self):
        f = self.cleaned_data.get('proof_of_address')
        if f:
            if f.size > 5 * 1024 * 1024:
                raise forms.ValidationError('File size must be under 5MB.')
            ext = f.name.rsplit('.', 1)[-1].lower()
            if ext not in ('pdf', 'jpg', 'jpeg', 'png'):
                raise forms.ValidationError('Only PDF, JPG, or PNG files are accepted.')
        return f


class LoginForm(AuthenticationForm):
    username = forms.CharField(label='Username or Email')
