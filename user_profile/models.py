from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from common.social_accounts import get_discord_data


class UserProfile(models.Model):
    class ThemeOptions(models.IntegerChoices):
        SL_Dark = (0, _('Dark'))
        SL_Light = (1, _('Light'))

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='profile')
    challonge_handle = models.CharField(
        max_length=255, unique=True, default=None, blank=True, null=True)
    tco_handle = models.CharField(max_length=255, unique=True,
                                  default=None, blank=True, null=True, verbose_name='TCO handle')
    dok_handle = models.CharField(max_length=255, unique=True,
                                  default=None, blank=True, null=True, verbose_name='DoK handle')

    discord_id = models.BigIntegerField(default=None, blank=True, null=True,
                                        verbose_name='Discord ID')
    theme = models.IntegerField(
        choices=ThemeOptions.choices, default=ThemeOptions.SL_Dark)

    def _get_discord_handle(self):
        discord_data = get_discord_data(self.user)
        return discord_data.get('username') or 'Unknown'

    discord_handle = property(_get_discord_handle)

    def is_complete(self):
        return self.challonge_handle and self.tco_handle


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
