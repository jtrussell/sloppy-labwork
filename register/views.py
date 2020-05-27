from django.db.models import Q
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.conf import settings
from django.views import generic
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from allauth.account.decorators import login_required
from requests import get
from decks.models import Deck
from .forms import RegiseterNewDeckForm
from .models import DeckRegistration
from botocore.exceptions import ClientError
import datetime
import boto3
import os
import time


class RegisterList(generic.ListView):
    template_name = 'register/page-list.html'
    paginate_by = 20

    def get_queryset(self):
        qs = DeckRegistration.objects.all()
        f = self.request.GET.get('f')
        if f:
            qs = qs.filter(Q(deck__name__icontains=f)
                           | Q(deck__id__icontains=f))
        if self.request.user.is_authenticated:
            qs = qs.filter(Q(has_photo_verification=1)
                           | Q(user=self.request.user))
        else:
            qs = qs.filter(has_photo_verification=1)
        return qs.order_by('-verified_on')


class RegisterDetail(generic.DetailView):
    model = DeckRegistration
    template_name = 'register/page-detail.html'


def about(request):
    return render(request, 'register/page-about.html', {})


def review(request, pk):
    registration = DeckRegistration.objects.get(pk=pk)
    return render(request, 'register/page-review.html', {
        'registration': registration
    })


def save_verification_photo(request, form, deck):
    s3_client = boto3.client('s3')
    f = request.FILES['verification_photo']
    orig_filename, ext = os.path.splitext(f.name)
    bucket_name = settings.AWS_S3_BUCKET_VERIFICATION_PHOTOS_BUCKET
    object_name = 'verification-photos/{}-{}-{}{}'.format(
        int(time.time()),
        request.user.id,
        deck.id,
        ext
    )
    response = s3_client.put_object(
        Body=f,
        Bucket=bucket_name,
        Key=object_name,
        ACL='public-read'
    )
    return 'https://static.sloppylabwork.com/{}'.format(
        object_name
    )


@login_required
def add(request):
    error_messages = []

    # Must have all info filled out before registering a field
    user_can_register_decks = request.user.profile.challonge_handle and request.user.profile.tco_handle

    # Can't register too many decks
    max_uploads_in_day = settings.MAX_UPLOADS_PER_DAY
    twenty_four_hours_ago = datetime.datetime.now() - datetime.timedelta(hours=24)
    my_uploads_today = DeckRegistration.objects.filter(
        user=request.user,
        created_on__gte=twenty_four_hours_ago)
    user_hit_register_rate_limit = len(
        my_uploads_today) > max_uploads_in_day - 1

    if request.method == 'POST':
        form = RegiseterNewDeckForm(request.POST, request.FILES)
        if form.is_valid():
            # Process the form...
            master_vault_url = form.cleaned_data['master_vault_link']
            master_vault_id = Deck.get_id_from_master_vault_url(
                master_vault_url)

            deck, created = Deck.objects.get_or_create(id=master_vault_id)
            if created:
                r = get(deck.get_master_vault_url())
                deck.name = r.json()['data']['name']
                deck.save()
            else:
                # TODO: Check if someone else the deck registered already

                old_registrations = DeckRegistration.objects.filter(
                    user=request.user,
                    deck=deck,
                    has_photo_verification=False
                )
                old_registrations.delete()

            registration = DeckRegistration()
            registration.user = request.user
            registration.deck = deck

            try:
                registration.photo_verification_link = save_verification_photo(
                    request, form, deck)
                registration.save()
                return HttpResponseRedirect(reverse('register-detail', kwargs={'pk': registration.id}))
            except ClientError:
                error_messages.append("Oops! Let's try that again")
    else:
        form = RegiseterNewDeckForm()

    return render(request, 'register/page-new.html', {
        'form': form,
        'user_can_register_decks': user_can_register_decks,
        'user_hit_register_rate_limit': user_hit_register_rate_limit,
        'error_messages': error_messages
    })


@staff_member_required
def verify(request, id):
    registration = DeckRegistration.objects.get(id=id)
    registration.has_photo_verification = True
    registration.verified_by = request.user
    registration.verified_on = datetime.datetime.now()
    registration.save()
    return HttpResponseRedirect('/admin/register/deckregistration/')
