from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import ExhibitorRegistrationForm, LoginForm
from notifications.utils import send_welcome_email


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
            send_html_email(
                'Registration Received - Al Ansaar Foundation',
                'emails/registration_pending.html',
                {'user': user, 'site_name': settings.SITE_NAME, 'site_url': settings.SITE_URL},
                [user.email],
            )
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
