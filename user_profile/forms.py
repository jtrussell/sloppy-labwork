from django import forms
from django.contrib.auth.models import User
from .models import UserProfile


class EditUsernameForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email']


class EditUserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['challonge_handle', 'tco_handle']
