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
from sloppy_labwork.utils import NewDeckRegistrationSubmittedEmail
from .forms import RegiseterNewDeckForm
from .models import DeckRegistration, SignedNonce
from botocore.exceptions import ClientError
from PIL import Image
from io import BytesIO
import datetime
import boto3
import time


class RegisterList(generic.ListView):
    template_name = 'register/page-list.html'
    paginate_by = 20

    def get_queryset(self):
        qs = DeckRegistration.objects
        f = self.request.GET.get('f')
        if f:
            qs = qs.filter(status=DeckRegistration.Status.VERIFIED_ACTIVE)
            qs = qs.filter(Q(deck__name__icontains=f)
                           | Q(deck__id__icontains=f))
        if self.request.user.is_authenticated:
            qs = qs.filter(Q(status=DeckRegistration.Status.VERIFIED_ACTIVE)
                           | Q(user=self.request.user))
        else:
            qs = qs.filter(status=DeckRegistration.Status.VERIFIED_ACTIVE)
        return qs.order_by('-verified_on')


class RegisterDetail(generic.DetailView):
    model = DeckRegistration
    template_name = 'register/page-detail.html'


class RegisterPhoto(generic.DetailView):
    model = DeckRegistration
    template_name = 'register/page-photo.html'


def about(request):
    return render(request, 'register/page-about.html', {})


def review(request, pk):
    registration = DeckRegistration.objects.get(pk=pk)
    return render(request, 'register/page-review.html', {
        'registration': registration
    })


def save_verification_photo(request, form, deck):
    img = request.FILES['verification_photo']
    img = resize_image(img)
    s3_client = boto3.client('s3')
    bucket_name = settings.AWS_S3_BUCKET_VERIFICATION_PHOTOS_BUCKET
    object_name = 'verification-photos/{}-{}-{}.jpg'.format(
        int(time.time()),
        request.user.id,
        deck.id
    )
    response = s3_client.put_object(
        Body=img,
        Bucket=bucket_name,
        Key=object_name,
        ACL='public-read'
    )
    return 'https://static.sloppylabwork.com/{}'.format(
        object_name
    )


def resize_image(img):
    # Shrink the image down so we're not storing massive photos just for kicks
    img = Image.open(img)
    max_dim = 600
    dims = (img.width, img.height)
    if max(dims) > max_dim:
        if dims[0] > dims[1]:
            dims = (max_dim, int(max_dim * dims[1] / dims[0]))
        else:
            dims = (int(max_dim * dims[0] / dims[1]), max_dim)
        img = img.resize(dims)
    buf = BytesIO()
    img.save(buf, format='JPEG', quality=60, optimize=True)
    return buf.getvalue()


@login_required
def add(request):
    error_messages = []

    # Must have all info filled out before registering a field
    user_can_register_decks = request.user.profile.is_complete()

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
        signed_nonce = SignedNonce.from_post(request.POST)
        if not signed_nonce.is_valid():
            error_messages.append(
                'The registration code just sumitted has expired. Please use the code below to submit a new registration request.')
        elif form.is_valid():
            # Process the form...
            master_vault_url = form.cleaned_data['master_vault_link']
            master_vault_id = Deck.get_id_from_master_vault_url(
                master_vault_url)

            deck, created = Deck.objects.get_or_create(id=master_vault_id)
            if created:
                r = get(deck.get_master_vault_api_url())
                deck.name = r.json()['data']['name']
                deck.save()
            else:
                # TODO: Check if someone else registered the deck already

                # Only allow the user to have one pending registartion per deck
                # TODO: This should probably happen after we've saved the new one
                old_registrations = DeckRegistration.objects.filter(
                    user=request.user,
                    deck=deck,
                    status=DeckRegistration.Status.PENDING
                )
                old_registrations.delete()

            registration = DeckRegistration()
            registration.user = request.user
            registration.deck = deck
            registration.verification_code = signed_nonce.nonce

            try:
                registration.verification_photo_url = save_verification_photo(
                    request, form, deck)
                registration.save()

                email = NewDeckRegistrationSubmittedEmail(registration)
                email.send()

                return HttpResponseRedirect(reverse('register-detail', kwargs={'pk': registration.id}))
            except ClientError:
                error_messages.append("Oops! Let's try that again")
    else:
        form = RegiseterNewDeckForm()

    return render(request, 'register/page-new.html', {
        'form': form,
        'signed_nonce': SignedNonce.create(),
        'user_can_register_decks': user_can_register_decks,
        'user_hit_register_rate_limit': user_hit_register_rate_limit,
        'error_messages': error_messages
    })


@staff_member_required
def verify(request, id):
    registration = DeckRegistration.objects.get(id=id)
    # Only allow one active registration per deck
    old_active_registrations = DeckRegistration.objects.filter(
        deck=registration.deck,
        status=DeckRegistration.Status.VERIFIED_ACTIVE
    )
    old_active_registrations.update(
        status=DeckRegistration.Status.VERIFIED
    )
    registration.status = DeckRegistration.Status.VERIFIED_ACTIVE
    registration.verified_by = request.user
    registration.verified_on = datetime.datetime.now()
    registration.save()
    return HttpResponseRedirect('/admin/register/deckregistration/')
