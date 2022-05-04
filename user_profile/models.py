from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from allauth.socialaccount.models import SocialAccount


class UserProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='profile')
    challonge_handle = models.CharField(
        max_length=255, unique=True, default=None, blank=True, null=True)
    tco_handle = models.CharField(max_length=255, unique=True,
                                  default=None, blank=True, null=True, verbose_name='TCO handle')
    dok_handle = models.CharField(max_length=255, unique=True,
                                  default=None, blank=True, null=True, verbose_name='DoK handle')

    def _get_discord_handle(self):
        try:
            discord_data = SocialAccount.objects.filter(
                user=self.user, provider='discord')[0].extra_data
            return discord_data.get('username')
        except (IndexError, AttributeError) as err:
            return 'Unknown'

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
