from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from .models import Profile


def member_role_required(role, approved=False):
	def decorator(view_func):
		@wraps(view_func)
		def wrapped(request, *args, **kwargs):
			if not request.user.is_authenticated:
				return redirect('login')
			if request.user.is_staff or request.user.is_superuser:
				messages.info(request, 'Use the administration site for staff actions.')
				return redirect('admin:index')
			profile = Profile.objects.filter(user=request.user).first()
			if profile is None:
				messages.error(request, 'A NourishLoop member profile is required for this action.')
				return redirect('home')
			if profile.role != role:
				messages.error(request, f'This action is only available to {role.lower()} accounts.')
				return redirect('dashboard')
			if approved and profile.verification_status != 'APPROVED':
				messages.error(request, 'Your account must be approved before you can perform this action.')
				return redirect('dashboard')
			return view_func(request, *args, **kwargs)
		return wrapped
	return decorator