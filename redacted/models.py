from django.db import models


class FallbackCollection(models.Model):
    dok_username = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['dok_username']

    def __str__(self):
        return self.dok_username
