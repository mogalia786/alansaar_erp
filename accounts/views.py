from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.contrib import messages
from django.http import JsonResponse
from django.utils.crypto import get_random_string
from django.utils.http import url_has_allowed_host_and_scheme
import logging
from .forms import ExhibitorRegistrationForm, LoginForm
from .models import User
from notifications.utils import send_welcome_email


def check_username(request):
    username = (request.GET.get('username') or '').strip()
    if not username:
        return JsonResponse({'exists': False})
    return JsonResponse({'exists': User.objects.filter(username__iexact=username).exists()})


def _generate_password():
    upper = get_random_string(4, 'ABCDEFGHJKLMNPQRSTUVWXYZ')
    lower = get_random_string(4, 'abcdefghjkmnpqrstuvwxyz')
    digits = get_random_string(3, '23456789')
    symbol = get_random_string(1, '!@#$%*+=')
    return upper + lower + digits + symbol


def forgot_password(request):
    if request.method == 'POST':
        identifier = (request.POST.get('identifier') or '').strip()
        user = None
        if identifier:
            user = (User.objects.filter(username__iexact=identifier).first()
                    or User.objects.filter(email__iexact=identifier).first())
        if user and user.is_active and user.email:
            new_password = _generate_password()
            user.set_password(new_password)
            user.save(update_fields=['password'])
            request.session['temp_password'] = new_password
            request.session['temp_user'] = user.username
            try:
                from notifications.utils import send_html_email
                from django.conf import settings
                send_html_email(
                    'Your New Password - Al Ansaar Foundation',
                    'emails/password_reset_email.html',
                    {'user': user, 'new_password': new_password, 'site_name': settings.SITE_NAME, 'site_url': settings.SITE_URL},
                    [user.email],
                )
                messages.success(request, 'Your new password has been emailed to your registered email address. Please check your inbox (and spam folder) then log in below.')
            except Exception as e:
                logging.getLogger(__name__).exception(f'Failed to email new password to {user.email}: {e}')
                messages.error(request, 'We could not email your new password right now. Please try again shortly.')
        else:
            messages.info(request, 'If an account exists with that username or email, a new password has been emailed to it.')
        return redirect('accounts:forgot_password')
    return render(request, 'accounts/forgot_password.html')


def change_password(request):
    authenticated = request.user.is_authenticated
    target = request.user if authenticated else None

    if request.method == 'POST':
        identifier = (request.POST.get('identifier') or '').strip()
        current = request.POST.get('current_password', '')
        new1 = request.POST.get('new_password1', '')
        new2 = request.POST.get('new_password2', '')
        errors = []

        if not authenticated:
            target = (User.objects.filter(username__iexact=identifier).first()
                      or User.objects.filter(email__iexact=identifier).first())
            if target is None:
                errors.append('No account found with that username or email address.')

        if target is not None:
            if not target.check_password(current):
                errors.append('Your current password is incorrect.')
            if current and new1 == current:
                errors.append('Your new password must be different from your current password.')
        if new1 != new2:
            errors.append('Your new passwords do not match.')
        if target is not None and new1:
            try:
                validate_password(new1, user=target)
            except Exception as e:
                errors.extend(getattr(e, 'messages', [str(e)]))

        if not errors:
            target.set_password(new1)
            target.save(update_fields=['password'])
            request.session.pop('temp_password', None)
            request.session.pop('temp_user', None)
            if authenticated:
                update_session_auth_hash(request, target)
                messages.success(request, 'Your password has been updated successfully.')
                return redirect('accounts:dashboard')
            messages.success(request, 'Your password has been updated successfully. Please log in with your new password.')
            return redirect('accounts:login')
        for err in errors:
            messages.error(request, err)

    identifier = ''
    if authenticated:
        identifier = request.user.username
    elif request.method == 'POST':
        identifier = request.POST.get('identifier') or ''

    return render(request, 'accounts/change_password.html', {
        'temp_password': request.session.get('temp_password'),
        'authenticated': authenticated,
        'identifier': identifier,
    })


def exhibitor_register(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    if request.method == 'POST':
        form = ExhibitorRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            user.user_type = 'exhibitor'
            user.is_verified = False
            user.save()
            from notifications.utils import send_html_email
            from django.conf import settings
            import logging
            try:
                send_html_email(
                    'Registration Received - Al Ansaar Foundation',
                    'emails/registration_pending.html',
                    {'user': user, 'site_name': settings.SITE_NAME, 'site_url': settings.SITE_URL},
                    [user.email],
                )
            except Exception as e:
                logging.getLogger(__name__).exception(f'Failed to send registration email to {user.email}: {e}')
                messages.warning(request, 'Your registration was saved but the confirmation email could not be sent. We will contact you once approved.')
            messages.success(request, 'Registration submitted! Your account is pending verification. You will receive an email once approved.')
            return redirect('accounts:login')
    else:
        form = ExhibitorRegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})


def exhibitor_login(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if user.user_type == 'exhibitor':
                if not user.is_verified:
                    messages.error(request, 'Your account is pending verification. Please wait for admin approval before logging in.')
                    return render(request, 'accounts/login.html', {'form': form})
                login(request, user)
                next_url = request.POST.get('next') or request.GET.get('next')
                if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts=None):
                    return redirect(next_url)
                return redirect('accounts:dashboard')
            else:
                messages.error(request, 'Invalid credentials.')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


@login_required
def exhibitor_logout(request):
    logout(request)
    return redirect('home')


@login_required
def exhibitor_dashboard(request):
    bookings = request.user.bookings.all().select_related('event', 'stall')
    return render(request, 'accounts/dashboard.html', {'bookings': bookings})


@login_required
def notifications_view(request):
    notifications = request.user.notifications.all()
    unread_count = notifications.filter(is_read=False).count()
    return render(request, 'notifications/list.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })
