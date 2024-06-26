from operator import is_
from django.utils.translation import gettext_lazy as _
from django.db import models
from django.contrib.auth.models import User
import uuid


class SecretChain(models.Model):
    description = models.CharField(max_length=255)
    join_key = models.UUIDField(default=uuid.uuid4, editable=False)
    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.description + ' (' + str(self.pk) + ')'

    def is_user_secret_player(self, user):
        return self.secret_players.filter(user=user).exists()

    def is_waiting_for_player_two_to_join(self):
        return self.secret_players.count() == 1


class SecretPlayer(models.Model):
    class Meta:
        unique_together = (('secret_chain', 'player_number'),
                           ('secret_chain', 'user'))

    class PlayerNumber(models.IntegerChoices):
        FIRST = 0, _('First player')
        SECOND = 1, _('Second player')

    secret_chain = models.ForeignKey(
        SecretChain, on_delete=models.CASCADE, related_name='secret_players')
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='secret_players')
    player_number = models.IntegerField(
        choices=(PlayerNumber.choices), blank=False, null=False)
    created_on = models.DateTimeField(auto_now_add=True)

    def is_first_player(self):
        return self.player_number == SecretPlayer.PlayerNumber.FIRST

    def is_second_player(self):
        return self.player_number == SecretPlayer.PlayerNumber.SECOND


class SecretChainLink(models.Model):
    class Meta:
        ordering = ['order']

    class Kind(models.IntegerChoices):
        ADD_LIST_OF_KF_DECKS = 0, _('Add decks')
        BAN = 1, _('Ban')
        SAFE = 2, _('Safe')
        SELECT = 3, _('Select')

    secret_chain = models.ForeignKey(
        SecretChain, on_delete=models.CASCADE, related_name='links')
    kind = models.IntegerField(
        choices=Kind.choices, default=Kind.ADD_LIST_OF_KF_DECKS, blank=False, null=False)
    description = models.CharField(max_length=255, blank=False, null=False)
    order = models.SmallIntegerField(default=0)
    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.description

    def is_complete(self):
        if self.kind == SecretChainLink.Kind.ADD_LIST_OF_KF_DECKS:
            return self.text_responses.count() == 2
        else:
            return self.list_item_responses.count() == 2


class SecretChainLinkTextResponse(models.Model):
    secret_chain_link = models.ForeignKey(
        SecretChainLink, on_delete=models.CASCADE, related_name='text_responses')
    player_number = models.IntegerField(
        choices=(SecretPlayer.PlayerNumber.choices), blank=False, null=False)
    response = models.TextField()


class SecretChainLinkListItemResponse(models.Model):
    secret_chain_link = models.ForeignKey(
        SecretChainLink, on_delete=models.CASCADE, related_name='list_item_responses')
    player_number = models.IntegerField(
        choices=(SecretPlayer.PlayerNumber.choices), blank=False, null=False)
    response = models.IntegerField()


class SecretChainTemplate(models.Model):
    description = models.CharField(max_length=255, blank=False, null=False)
    created_on = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='secret_templates')

    def __str__(self):
        return self.description


class SecretChainTemplateLink(models.Model):
    secret_chain_template = models.ForeignKey(
        SecretChainTemplate, on_delete=models.CASCADE, related_name='links')
    kind = models.IntegerField(
        choices=SecretChainLink.Kind.choices, blank=False, null=False)
    order = models.SmallIntegerField(default=0)


class SecretChainService():
    @staticmethod
    def create_from_template(template, first_player):
        chain = SecretChain(description=template.description)
        chain.save()
        for template_link in template.links.all():
            desc = dict(SecretChainLink.Kind.choices)[template_link.kind]
            link = SecretChainLink(
                secret_chain=chain, kind=template_link.kind, description=desc, order=template_link.order)
            link.save()
        chain_player = SecretPlayer(
            secret_chain=chain, user=first_player, player_number=SecretPlayer.PlayerNumber.FIRST)
        chain_player.save()
        return chain

    @staticmethod
    def join_chain_by_key(join_key, user):
        chain = SecretChain.objects.get(join_key=join_key)
        chain_player = SecretPlayer(
            secret_chain=chain, user=user, player_number=SecretPlayer.PlayerNumber.SECOND)
        chain_player.save()
        return chain
