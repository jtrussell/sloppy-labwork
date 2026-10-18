from allauth.account.models import EmailAddress
from django import forms
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from .models import UserProfile


class EditUsernameForm(forms.ModelForm):
    email = forms.EmailField()
    field_order = ['username', 'email']

    class Meta:
        model = User
        fields = ['username']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial.setdefault('email', self.instance.email)

    def clean_username(self):
        username = self.cleaned_data['username']
        is_taken_by_another_user = User.objects.filter(
            username__iexact=username).exclude(pk=self.instance.pk).exists()
        if is_taken_by_another_user:
            raise forms.ValidationError(
                _('A user with that username already exists.'))
        return username

    def clean_email(self):
        return self.cleaned_data['email'].lower()

    def has_email_changed(self):
        return self.cleaned_data['email'] != self.instance.email.lower()

    def request_email_change_if_changed(self, request):
        if self.has_email_changed():
            EmailAddress.objects.add_new_email(
                request, self.instance, self.cleaned_data['email'])


class EditUserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['challonge_handle', 'tco_handle', 'dok_handle', 'theme']
