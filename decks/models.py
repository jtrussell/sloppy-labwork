from django.db import models
from django.contrib.auth.models import User


class Deck(models.Model):
    id = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=200, unique=True)
    added_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name
