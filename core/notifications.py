from .models import Notification


def notify_users(users, message):
	unique_users = {user.pk: user for user in users if user is not None}
	Notification.objects.bulk_create([
		Notification(user=user, message=message)
		for user in unique_users.values()
	])