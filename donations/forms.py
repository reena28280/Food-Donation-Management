from django import forms
from django.utils import timezone
from .models import FoodDonation


class FoodDonationForm(forms.ModelForm):
    total_servings = forms.IntegerField(min_value=1, label='Quantity in servings')
    prepared_at = forms.DateTimeField(
        label='Preparation date and time',
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}, format='%Y-%m-%dT%H:%M'),
    )
    pickup_deadline = forms.DateTimeField(
        label='Pickup deadline',
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}, format='%Y-%m-%dT%H:%M'),
    )
    image = forms.ImageField(
        required=False,
        error_messages={'invalid_image': 'Upload a valid JPEG, PNG, or WebP image.'},
    )
    packaging_confirmed = forms.BooleanField(
        label='Food is packed safely for pickup',
        error_messages={'required': 'Confirm the food is packed safely before publishing.'},
    )
    storage_confirmed = forms.BooleanField(
        label='Storage details are accurate',
        error_messages={'required': 'Confirm the storage information is accurate before publishing.'},
    )

    MAX_IMAGE_SIZE = 5 * 1024 * 1024
    ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}

    class Meta:
        model = FoodDonation
        fields = (
            'title', 'description', 'category', 'food_type', 'total_servings', 'image',
            'prepared_at', 'pickup_deadline', 'pickup_address', 'city', 'allergens',
            'storage_details', 'packaging_confirmed', 'storage_confirmed',
        )
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Vegetable rice lunch boxes'}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Describe the food, portions, and anything receivers should know.'}),
            'image': forms.ClearableFileInput(attrs={'accept': 'image/jpeg,image/png,image/webp'}),
            'pickup_address': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Full pickup address; shared only with approved participants.'}),
            'city': forms.TextInput(attrs={'placeholder': 'City or town'}),
            'allergens': forms.Textarea(attrs={'rows': 2, 'placeholder': 'List known allergens or enter None.'}),
            'storage_details': forms.Textarea(attrs={'rows': 2, 'placeholder': 'How has the food been stored?'}),
        }

    def clean_title(self):
        title = self.cleaned_data['title'].strip()
        if not title:
            raise forms.ValidationError('Enter a clear title for this food listing.')
        return title

    def clean_city(self):
        city = self.cleaned_data['city'].strip()
        if not city:
            raise forms.ValidationError('Enter the city where the food can be collected.')
        return city

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if not image:
            return image
        if image.size > self.MAX_IMAGE_SIZE:
            raise forms.ValidationError('Choose an image smaller than 5 MB.')
        image_format = getattr(getattr(image, 'image', None), 'format', None)
        if image_format not in self.ALLOWED_IMAGE_FORMATS:
            raise forms.ValidationError('Upload a valid JPEG, PNG, or WebP image.')
        return image

    def clean(self):
        cleaned_data = super().clean()
        prepared_at = cleaned_data.get('prepared_at')
        pickup_deadline = cleaned_data.get('pickup_deadline')
        now = timezone.now()
        if prepared_at and prepared_at > now:
            self.add_error('prepared_at', 'Preparation time cannot be in the future.')
        if pickup_deadline and pickup_deadline <= now:
            self.add_error('pickup_deadline', 'Pickup deadline must be in the future.')
        if prepared_at and pickup_deadline and pickup_deadline <= prepared_at:
            self.add_error('pickup_deadline', 'Pickup deadline must be after the preparation time.')
        return cleaned_data