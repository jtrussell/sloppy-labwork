from django.utils.translation import gettext_lazy as _
from django.db import models
from django.contrib.auth.models import User


class PodPlayer(models.Model):
    class Pod(models.IntegerChoices):
        DIS = 0, _('Dis')
        LOGOS = 1, _('Logos')
        SHADOWS = 2, _('Shadows')

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    user_handle = models.CharField(max_length=255)
    pod = models.IntegerField(choices=Pod.choices, default=Pod.SHADOWS)

    def __str__(self):
        return self.user_handle


class PastMatch(models.Model):
    class Meta:
        verbose_name_plural = 'Past matches'

    player = models.ForeignKey(
        PodPlayer, on_delete=models.CASCADE, related_name='past_matches')
    opponent = models.ForeignKey(
        PodPlayer, on_delete=models.CASCADE)


class NotCancelledManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_cancelled=False)


class MatchRequest(models.Model):
    class Meta:
        get_latest_by = 'created_on'

    player = models.ForeignKey(PodPlayer, on_delete=models.CASCADE)
    created_on = models.DateTimeField(auto_now_add=True)
    completed_by = models.OneToOneField(
        'self', on_delete=models.CASCADE, default=None, blank=True, null=True)
    is_cancelled = models.BooleanField(default=False)

    # objects = NotCancelledManager()
    # objects_all = models.Manager()

    def cancel_latest_for_player(self, player):
        req = self.objects.filter(player=player).latest()
        req.is_cancelled = True
        if req.completed_by:
            req.completed_by.is_cancelled = True
        req.save()

    def __str__(self):
        return self.player.user_handle


class MatchingService():
    @staticmethod
    def create_request_and_complete_if_able(player: PodPlayer):
        request = MatchRequest.objects.create(player=player)

        reqs_to_cancel = MatchRequest.objects.filter(player=player, is_cancelled=False).exclude(
            id=request.id)
        reqs_to_cancel.update(is_cancelled=True)
        MatchRequest.objects.filter(completed_by__in=reqs_to_cancel).update(
            is_cancelled=True)

        match_with = MatchRequest.objects.annotate(has_played=models.Exists(
            PastMatch.objects.filter(
                player=player, opponent=models.OuterRef('player'))
        )).filter(has_played=False, is_cancelled=False, completed_by=None).exclude(player=player).latest()

        if match_with:
            match_with.completed_by = request
            request.completed_by = match_with
            match_with.save()
            request.save()

        return request

    @ staticmethod
    def cancel_request_and_completing(match_request: MatchRequest):
        match_request.is_cancelled = True
        match_request.save()
        if (match_request.completed_by):
            match_request.completed_by.is_cancelled = True
            match_request.completed_by.save()
        return match_request
