from django import forms
from .models import Subscriber


class SubscriptionForm(forms.ModelForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your email',
            'autocomplete': 'email',
        })
    )
    phone = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your phone (optional)',
            'autocomplete': 'tel',
        })
    )

    message = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={
            'class': 'form-input',
            'placeholder': 'Your message (optional)',
            'rows': 4,
            'maxlength': 1000,
        })
    )

    class Meta:
        model = Subscriber
        fields = ['email', 'phone', 'message']

    def validate_unique(self):
        # The email uniqueness rule lives in clean_email(): a confirmed address is
        # refused, an unconfirmed one may be submitted again (the view then re-sends
        # the confirmation email instead of creating a duplicate row).
        exclude = self._get_validation_exclusions()
        exclude.add('email')
        try:
            self.instance.validate_unique(exclude=exclude)
        except forms.ValidationError as e:
            self._update_errors(e)

    def clean_email(self):
        email = self.cleaned_data['email']
        if Subscriber.objects.filter(email=email).exists():
            subscriber = Subscriber.objects.get(email=email)
            if subscriber.is_active:
                raise forms.ValidationError('This email is already subscribed.')
            # If not active, we'll allow resubmitting and resend confirmation
        return email
