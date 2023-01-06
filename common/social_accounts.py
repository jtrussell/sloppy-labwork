from allauth.socialaccount.models import SocialAccount


def get_discord_data(user):
    user_social_accounts = SocialAccount.objects.filter(user=user, provider='discord')
    if len(user_social_accounts) == 0:
        return {}
    return user_social_accounts[0].extra_data
