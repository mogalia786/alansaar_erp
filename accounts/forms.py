from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User


class ExhibitorRegistrationForm(UserCreationForm):
    company_name = forms.CharField(max_length=200, required=True, label='Company/Trading Name')
    phone = forms.CharField(max_length=20, required=True, label='Phone Number')

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'company_name', 'phone', 'password1', 'password2']


class LoginForm(AuthenticationForm):
    username = forms.CharField(label='Username or Email')
