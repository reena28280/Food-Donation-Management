from django import forms

from .models import ContactEnquiry


class ContactEnquiryForm(forms.ModelForm):
    class Meta:
        model = ContactEnquiry
        fields = ('name', 'email', 'subject', 'message')
        widgets = {
            'name': forms.TextInput(attrs={'autocomplete': 'name', 'maxlength': 120}),
            'email': forms.EmailInput(attrs={'autocomplete': 'email', 'maxlength': 254}),
            'subject': forms.TextInput(attrs={'maxlength': 200}),
            'message': forms.Textarea(attrs={'rows': 6, 'maxlength': 5000}),
        }

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if not name:
            raise forms.ValidationError('Enter your name.')
        return name

    def clean_subject(self):
        subject = self.cleaned_data['subject'].strip()
        if not subject:
            raise forms.ValidationError('Enter a subject.')
        return subject

    def clean_message(self):
        message = self.cleaned_data['message'].strip()
        if not message:
            raise forms.ValidationError('Enter a message.')
        return message