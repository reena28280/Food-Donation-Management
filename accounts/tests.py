from django.test import TestCase
from .forms import SignUpForm


class SignUpOrganizationTypeTests(TestCase):
    def test_receiver_signup_includes_additional_organization_types(self):
        form = SignUpForm({'role': 'RECEIVER'})
        choices = dict(form.fields['organization_type'].choices)

        self.assertEqual(choices['ORPHANAGE'], 'Orphanage')
        self.assertEqual(choices['OLD_AGE_HOME'], 'Old-age home')
        self.assertEqual(choices['COMMUNITY_CENTRE'], 'Community centre')

    def test_receiver_signup_accepts_additional_organization_types(self):
        for organization_type in ('ORPHANAGE', 'OLD_AGE_HOME', 'COMMUNITY_CENTRE'):
            with self.subTest(organization_type=organization_type):
                form = SignUpForm({
                    'username': f'user_{organization_type.lower()}',
                    'first_name': 'Test',
                    'last_name': 'User',
                    'email': f'{organization_type.lower()}@example.com',
                    'password1': 'Safe-password-2026',
                    'password2': 'Safe-password-2026',
                    'role': 'RECEIVER',
                    'organization_type': organization_type,
                    'organization_name': 'Test organization',
                    'phone': '1234567890',
                    'address': '123 Test Street',
                    'city': 'Test City',
                })

                self.assertTrue(form.is_valid(), form.errors)
