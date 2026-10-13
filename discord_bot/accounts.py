from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.models import AnonymousUser
from .links import absolute_url


def get_site_user_for_discord_id(discord_user_id):
    account = SocialAccount.objects.filter(
        provider='discord', uid=discord_user_id).select_related('user').first()
    if account is None:
        return AnonymousUser()
    return account.user


def account_not_linked_message():
    connections_url = absolute_url('socialaccount_connections')
    return f'I don\'t know which Sloppy Labwork account is yours. Link your Discord account at {connections_url} and try again.'
