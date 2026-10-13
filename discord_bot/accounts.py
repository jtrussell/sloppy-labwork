from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.models import AnonymousUser


def get_site_user_for_discord_id(discord_user_id):
    account = SocialAccount.objects.filter(
        provider='discord', uid=discord_user_id).select_related('user').first()
    if account is None:
        return AnonymousUser()
    return account.user
