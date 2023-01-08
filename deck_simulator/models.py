from django.contrib.auth.models import User
from django.db import models


# Create your models here.
class GeneratedDeck(models.Model):
    uid = models.UUIDField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    deck_data = models.JSONField()
