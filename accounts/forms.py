from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from .models import Profile


ORGANIZATION_TYPES_BY_ROLE = Profile.ORGANIZATION_TYPES_BY_ROLE
ORGANIZATION_LABELS = dict(Profile.ORGANIZATION_CHOICES)
SIGNUP_ORGANIZATION_TYPES_BY_ROLE = {
    'DONOR': {'COLLEGE', 'HOSTEL', 'RESTAURANT', 'HOTEL', 'EVENT', 'INDIVIDUAL'},
    'RECEIVER': {
        'NGO', 'COMMUNITY', 'CHARITY', 'COMMUNITY_GROUP', 'ORPHANAGE',
        'OLD_AGE_HOME', 'COMMUNITY_CENTRE',
    },
    'VOLUNTEER': ORGANIZATION_TYPES_BY_ROLE['VOLUNTEER'],
}


def organization_choices(role):
    valid_types = SIGNUP_ORGANIZATION_TYPES_BY_ROLE.get(role, set())
    return [(code, label) for code, label in Profile.ORGANIZATION_CHOICES if code in valid_types]


class SignUpForm(UserCreationForm):
    email = forms.EmailField()
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    role = forms.ChoiceField(choices=Profile.ROLE_CHOICES)
    organization_type = forms.ChoiceField(
        choices=Profile.ORGANIZATION_CHOICES,
        error_messages={'invalid_choice': 'Choose an organization type that matches your account role.'},
    )
    organization_name = forms.CharField(max_length=150, required=False)
    phone = forms.CharField(max_length=15)
    address = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}))
    city = forms.CharField(max_length=100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        role = self.data.get('role') or self.initial.get('role') or 'DONOR'
        self.fields['organization_type'].choices = organization_choices(role)
        self.fields['organization_type'].initial = 'INDIVIDUAL'

    class Meta:
        model = User
        fields = (
            'username', 'first_name', 'last_name', 'email', 'password1', 'password2',
            'role', 'organization_type', 'organization_name', 'phone', 'address', 'city',
        )

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        organization_type = cleaned_data.get('organization_type')
        if role and organization_type and organization_type not in SIGNUP_ORGANIZATION_TYPES_BY_ROLE.get(role, set()):
            self.add_error('organization_type', 'Choose an organization type that matches your account role.')
        return cleaned_data


class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    role = forms.ChoiceField(choices=Profile.ROLE_CHOICES, required=False)

    class Meta:
        model = Profile
        fields = ('role', 'organization_type', 'organization_name', 'phone', 'address', 'city')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields.pop('role')
            role = self.instance.role
        else:
            self.fields['role'].required = True
            role = (
                self.data.get(self.add_prefix('role'))
                or self.initial.get('role')
                or self.instance.role
            )
        valid_types = ORGANIZATION_TYPES_BY_ROLE.get(role)
        if valid_types:
            self.fields['organization_type'].choices = [
                (code, label) for code, label in Profile.ORGANIZATION_CHOICES if code in valid_types
            ]

    def clean_organization_type(self):
        organization_type = self.cleaned_data['organization_type']
        role = self.cleaned_data.get('role') or self.instance.role
        if role not in ORGANIZATION_TYPES_BY_ROLE or organization_type not in ORGANIZATION_TYPES_BY_ROLE[role]:
            raise forms.ValidationError('Choose an organization type that matches your account role.')
        return organization_type


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label='Username',
        error_messages={'required': 'Enter your username.'},
        widget=forms.TextInput(attrs={'autocomplete': 'username'}),
    )
    password = forms.CharField(
        label='Password',
        error_messages={'required': 'Enter your password.'},
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': 'The username or password you entered is incorrect. Check both and try again.',
        'inactive': 'This account is inactive. Contact an administrator for help.',
    }