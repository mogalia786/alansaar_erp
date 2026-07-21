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
        form = ExhibitorRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.user_type = 'exhibitor'
            user.save()
            send_welcome_email(user)
            login(request, user)
            messages.success(request, 'Registration successful! Welcome.')
            return redirect('accounts:dashboard')
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
