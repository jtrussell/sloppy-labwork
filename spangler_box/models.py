from typing import Any
from django.utils.translation import gettext_lazy as _
from django.db import models
from django.contrib.auth.models import User


class SecretChain(models.Model):
    description = models.CharField(max_length=255)
    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.description


class SecretPlayer(models.Model):
    class Meta:
        unique_together = (('secret_chain', 'player_number'),)

    class PlayerNumber(models.IntegerChoices):
        FIRST = 0, _('First player')
        SECOND = 1, _('Second player')

    secret_chain = models.ForeignKey(
        SecretChain, on_delete=models.CASCADE, related_name='secret_users')
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='secret_users')
    player_number = models.IntegerField(
        choices=(PlayerNumber.choices), blank=False, null=False)
    created_on = models.DateTimeField(auto_now_add=True)


class SecretChainLink(models.Model):
    class Kind(models.IntegerChoices):
        ADD_LIST_OF_KF_DECKS = 0, _('Add decks')
        BAN = 1, _('Ban')
        SAFE = 2, _('Safe')
        SELECT = 3, _('Select')

    secret_chain = models.ForeignKey(
        SecretChain, on_delete=models.CASCADE, related_name='links')
    kind = models.IntegerField(
        choices=Kind.choices, default=Kind.ADD_LIST_OF_KF_DECKS, blank=False, null=False)
    order = models.SmallIntegerField(default=0)
    created_on = models.DateTimeField(auto_now_add=True)


class SecretChainLinkTextResponse(models.Model):
    secret_chain_link = models.ForeignKey(
        SecretChainLink, on_delete=models.CASCADE)
    player_number = models.IntegerField(
        choices=(SecretPlayer.PlayerNumber.choices), blank=False, null=False)
    response = models.TextField()


class SecretChainLinkListItemResponse(models.Model):
    secret_chain_link = models.ForeignKey(
        SecretChainLink, on_delete=models.CASCADE)
    player_number = models.IntegerField(
        choices=(SecretPlayer.PlayerNumber.choices), blank=False, null=False)
    response = models.IntegerField()


class SecretChainTemplate(models.Model):
    description = models.CharField(max_length=255)
    created_on = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='secret_templates')

    def __str__(self):
        return self.description


class SecretChainTemplateLink(models.Model):
    secret_chain_template = models.ForeignKey(
        SecretChainTemplate, on_delete=models.CASCADE)
    kind = models.IntegerField(
        choices=SecretChainLink.Kind.choices, blank=False, null=False)
    order = models.SmallIntegerField(default=0)
