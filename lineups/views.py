from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Prefetch
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST, require_http_methods
from xml.etree.ElementTree import Element, SubElement, tostring

from .models import Lineup, LineupNote, LineupVersion, LineupVersionNote, LineupVersionDeck
from .forms import LineupForm, LineupNoteForm, LineupVersionForm, LineupVersionNoteForm, DeckAddForm
from pmc.models import EventFormat
from decks.models import Deck


def redirect_to(request, url):
    if hasattr(request, 'htmx') and request.htmx:
        resp = HttpResponse(url)
        resp['HX-Redirect'] = url
        return resp
    return redirect(url)


def should_show_lineup_details(lineup, user):
    if lineup.visibility == Lineup.Visibility.PUBLIC:
        return True
    if user.is_authenticated and lineup.owner == user:
        return True
    return False


@login_required
def lineup_list(request):
    lineups = Lineup.objects.filter(owner=request.user).prefetch_related(
        Prefetch(
            'versions',
            queryset=LineupVersion.objects.annotate(deck_count=Count('version_decks'))
        )
    )

    search_query = request.GET.get('q', '').strip()
    if search_query:
        lineups = lineups.filter(name__icontains=search_query)

    format_filter = request.GET.get('format', '')
    if format_filter:
        lineups = lineups.filter(format_id=format_filter)

    paginator = Paginator(lineups, 10)
    page = request.GET.get('page', 1)
    lineups_page = paginator.get_page(page)

    formats = EventFormat.objects.all()

    context = {
        'lineups': lineups_page,
        'formats': formats,
        'search_query': search_query,
        'format_filter': format_filter,
    }

    if hasattr(request, 'htmx') and request.htmx:
        return render(request, 'lineups/partials/lineup-list-results.html', context)

    return render(request, 'lineups/list.html', context)


@login_required
def lineup_create(request):
    if request.method == 'POST':
        form = LineupForm(request.POST)
        if form.is_valid():
            lineup = form.save(commit=False)
            lineup.owner = request.user
            lineup.save()

            version = LineupVersion.objects.create(
                lineup=lineup,
                name="Version 1",
                sort_order=1
            )

            messages.success(request, f'Lineup "{lineup.name}" created!')
            return redirect_to(request, f'/lineups/versions/{version.code}/')
    else:
        form = LineupForm()

    return render(request, 'lineups/form.html', {
        'form': form,
        'is_edit': False,
    })


def lineup_detail(request, lineup_code):
    lineup = get_object_or_404(Lineup, code=lineup_code)

    if not lineup.can_view(request.user):
        raise PermissionDenied

    is_owner = lineup.can_edit(request.user)

    export_format = request.GET.get('f')
    if export_format == 'json':
        return lineup_to_json(lineup, request.user)
    elif export_format == 'xml':
        return lineup_to_xml(lineup, request.user)

    versions = lineup.get_visible_versions(request.user)
    version_paginator = Paginator(versions, 5)
    version_page = request.GET.get('vp', 1)
    versions_page = version_paginator.get_page(version_page)

    notes = lineup.notes.all()
    note_paginator = Paginator(notes, 5)
    note_page = request.GET.get('np', 1)
    notes_page = note_paginator.get_page(note_page)

    context = {
        'lineup': lineup,
        'versions': versions_page,
        'notes': notes_page,
        'is_owner': is_owner,
        'note_form': LineupNoteForm() if is_owner else None,
    }
    return render(request, 'lineups/detail.html', context)


@login_required
def lineup_edit(request, lineup_code):
    lineup = get_object_or_404(Lineup, code=lineup_code)

    if not lineup.can_edit(request.user):
        raise PermissionDenied

    if request.method == 'POST':
        form = LineupForm(request.POST, instance=lineup)
        if form.is_valid():
            form.save()
            messages.success(request, f'Lineup "{lineup.name}" updated!')
            return redirect_to(request, f'/lineups/{lineup.code}/')
    else:
        form = LineupForm(instance=lineup)

    return render(request, 'lineups/form.html', {
        'form': form,
        'lineup': lineup,
        'is_edit': True,
    })


@login_required
@require_POST
def lineup_delete(request, lineup_code):
    lineup = get_object_or_404(Lineup, code=lineup_code)

    if not lineup.can_edit(request.user):
        raise PermissionDenied

    lineup_name = lineup.name
    lineup.delete()
    messages.success(request, f'Lineup "{lineup_name}" deleted.')
    return redirect_to(request, '/lineups/')


@login_required
@require_POST
def lineup_note_add(request, lineup_code):
    lineup = get_object_or_404(Lineup, code=lineup_code)

    if not lineup.can_edit(request.user):
        raise PermissionDenied

    form = LineupNoteForm(request.POST)
    if form.is_valid():
        note = form.save(commit=False)
        note.lineup = lineup
        note.save()
        messages.success(request, 'Note added.')

    return redirect_to(request, f'/lineups/{lineup.code}/')


@login_required
def lineup_note_edit(request, lineup_code, note_id):
    lineup = get_object_or_404(Lineup, code=lineup_code)
    note = get_object_or_404(LineupNote, id=note_id, lineup=lineup)

    if not lineup.can_edit(request.user):
        raise PermissionDenied

    if request.method == 'POST':
        form = LineupNoteForm(request.POST, instance=note)
        if form.is_valid():
            form.save()
            if hasattr(request, 'htmx') and request.htmx:
                return render(request, 'lineups/partials/note-item.html', {
                    'note': note,
                    'is_owner': True,
                    'lineup': lineup,
                })
            messages.success(request, 'Note updated.')
            return redirect_to(request, f'/lineups/{lineup.code}/')
    else:
        if request.GET.get('cancel'):
            return render(request, 'lineups/partials/note-item.html', {
                'note': note,
                'is_owner': True,
                'lineup': lineup,
            })
        form = LineupNoteForm(instance=note)

    if hasattr(request, 'htmx') and request.htmx:
        return render(request, 'lineups/partials/note-form.html', {
            'form': form,
            'note': note,
            'lineup': lineup,
        })

    return render(request, 'lineups/note-form.html', {
        'form': form,
        'note': note,
        'lineup': lineup,
    })


@login_required
@require_POST
def lineup_note_delete(request, lineup_code, note_id):
    lineup = get_object_or_404(Lineup, code=lineup_code)
    note = get_object_or_404(LineupNote, id=note_id, lineup=lineup)

    if not lineup.can_edit(request.user):
        raise PermissionDenied

    note.delete()
    messages.success(request, 'Note deleted.')

    if hasattr(request, 'htmx') and request.htmx:
        return HttpResponse('')

    return redirect_to(request, f'/lineups/{lineup.code}/')


@login_required
def version_create(request, lineup_code):
    lineup = get_object_or_404(Lineup, code=lineup_code)

    if not lineup.can_edit(request.user):
        raise PermissionDenied

    next_sort_order = lineup.versions.count() + 1

    if request.method == 'POST':
        form = LineupVersionForm(request.POST)
        if form.is_valid():
            version = form.save(commit=False)
            version.lineup = lineup
            version.save()
            messages.success(request, f'Version "{version.name}" created!')
            return redirect_to(request, f'/lineups/versions/{version.code}/')
    else:
        form = LineupVersionForm(initial={'name': f'Version {next_sort_order}'})

    return render(request, 'lineups/version-form.html', {
        'form': form,
        'lineup': lineup,
        'is_edit': False,
        'show_lineup_details': should_show_lineup_details(lineup, request.user),
    })


def version_detail(request, version_code):
    version = get_object_or_404(LineupVersion, code=version_code)
    lineup = version.lineup

    if not version.can_view(request.user):
        raise PermissionDenied

    is_owner = lineup.can_edit(request.user)

    export_format = request.GET.get('f')
    if export_format == 'json':
        return version_to_json(version)
    elif export_format == 'xml':
        return version_to_xml(version)

    notes = version.notes.all()
    note_paginator = Paginator(notes, 5)
    note_page = request.GET.get('np', 1)
    notes_page = note_paginator.get_page(note_page)

    decks = version.version_decks.select_related(
        'deck__set', 'deck__house_1', 'deck__house_2', 'deck__house_3')

    context = {
        'lineup': lineup,
        'version': version,
        'decks': decks,
        'notes': notes_page,
        'is_owner': is_owner,
        'note_form': LineupVersionNoteForm() if is_owner else None,
        'deck_form': DeckAddForm() if is_owner else None,
        'show_lineup_details': should_show_lineup_details(lineup, request.user),
    }
    return render(request, 'lineups/version-detail.html', context)


@login_required
def version_edit(request, version_code):
    version = get_object_or_404(LineupVersion, code=version_code)
    lineup = version.lineup

    if not lineup.can_edit(request.user):
        raise PermissionDenied

    if request.method == 'POST':
        form = LineupVersionForm(request.POST, instance=version)
        if form.is_valid():
            form.save()
            messages.success(request, f'Version "{version.name}" updated!')
            return redirect_to(request, f'/lineups/versions/{version.code}/')
    else:
        form = LineupVersionForm(instance=version)

    return render(request, 'lineups/version-form.html', {
        'form': form,
        'lineup': lineup,
        'version': version,
        'is_edit': True,
        'show_lineup_details': should_show_lineup_details(lineup, request.user),
    })


@login_required
@require_POST
def version_delete(request, version_code):
    version = get_object_or_404(LineupVersion, code=version_code)
    lineup = version.lineup

    if not lineup.can_edit(request.user):
        raise PermissionDenied

    version_name = version.name
    version.delete()
    messages.success(request, f'Version "{version_name}" deleted.')
    return redirect_to(request, f'/lineups/{lineup.code}/')


@login_required
@require_POST
def version_note_add(request, version_code):
    version = get_object_or_404(LineupVersion, code=version_code)
    lineup = version.lineup

    if not lineup.can_edit(request.user):
        raise PermissionDenied

    form = LineupVersionNoteForm(request.POST)
    if form.is_valid():
        note = form.save(commit=False)
        note.version = version
        note.save()
        messages.success(request, 'Note added.')

    return redirect_to(request, f'/lineups/versions/{version.code}/')


@login_required
def version_note_edit(request, version_code, note_id):
    version = get_object_or_404(LineupVersion, code=version_code)
    lineup = version.lineup
    note = get_object_or_404(LineupVersionNote, id=note_id, version=version)

    if not lineup.can_edit(request.user):
        raise PermissionDenied

    if request.method == 'POST':
        form = LineupVersionNoteForm(request.POST, instance=note)
        if form.is_valid():
            form.save()
            if hasattr(request, 'htmx') and request.htmx:
                return render(request, 'lineups/partials/version-note-item.html', {
                    'note': note,
                    'is_owner': True,
                    'lineup': lineup,
                    'version': version,
                })
            messages.success(request, 'Note updated.')
            return redirect_to(request, f'/lineups/versions/{version.code}/')
    else:
        if request.GET.get('cancel'):
            return render(request, 'lineups/partials/version-note-item.html', {
                'note': note,
                'is_owner': True,
                'lineup': lineup,
                'version': version,
            })
        form = LineupVersionNoteForm(instance=note)

    if hasattr(request, 'htmx') and request.htmx:
        return render(request, 'lineups/partials/version-note-form.html', {
            'form': form,
            'note': note,
            'lineup': lineup,
            'version': version,
        })

    return render(request, 'lineups/version-note-form.html', {
        'form': form,
        'note': note,
        'lineup': lineup,
        'version': version,
    })


@login_required
@require_POST
def version_note_delete(request, version_code, note_id):
    version = get_object_or_404(LineupVersion, code=version_code)
    lineup = version.lineup
    note = get_object_or_404(LineupVersionNote, id=note_id, version=version)

    if not lineup.can_edit(request.user):
        raise PermissionDenied

    note.delete()
    messages.success(request, 'Note deleted.')

    if hasattr(request, 'htmx') and request.htmx:
        return HttpResponse('')

    return redirect_to(request, f'/lineups/versions/{version.code}/')


@login_required
@require_POST
def version_deck_add(request, version_code):
    version = get_object_or_404(LineupVersion, code=version_code)
    lineup = version.lineup

    if not lineup.can_edit(request.user):
        raise PermissionDenied

    form = DeckAddForm(request.POST)
    if form.is_valid():
        deck_id = form.cleaned_data['deck_url']
        try:
            with transaction.atomic():
                deck, created = Deck.objects.get_or_create(id=deck_id)
                if created or not deck.name:
                    deck.hydrate_from_master_vault(save=True)

                if not LineupVersionDeck.objects.filter(version=version, deck=deck).exists():
                    LineupVersionDeck.objects.create(
                        version=version,
                        deck=deck
                    )
                    messages.success(request, f'Deck "{deck.name}" added.')
                else:
                    messages.warning(request, f'Deck "{deck.name}" is already in this version.')
        except Exception as e:
            messages.error(request, f'Failed to add deck: {str(e)}')
    else:
        messages.error(request, 'Invalid deck URL.')

    return redirect_to(request, f'/lineups/versions/{version.code}/')


@login_required
@require_POST
def version_deck_remove(request, version_code, deck_id):
    version = get_object_or_404(LineupVersion, code=version_code)
    lineup = version.lineup
    version_deck = get_object_or_404(LineupVersionDeck, id=deck_id, version=version)

    if not lineup.can_edit(request.user):
        raise PermissionDenied

    deck_name = version_deck.deck.name
    version_deck.delete()
    messages.success(request, f'Deck "{deck_name}" removed.')

    if hasattr(request, 'htmx') and request.htmx:
        return HttpResponse('')

    return redirect_to(request, f'/lineups/versions/{version.code}/')


@login_required
@require_POST
def version_deck_reorder(request, version_code):
    version = get_object_or_404(LineupVersion, code=version_code)
    lineup = version.lineup

    if not lineup.can_edit(request.user):
        raise PermissionDenied

    order = request.POST.getlist('order[]')
    for i, deck_id in enumerate(order):
        LineupVersionDeck.objects.filter(id=deck_id, version=version).update(sort_order=i)

    if hasattr(request, 'htmx') and request.htmx:
        return HttpResponse('')

    return redirect_to(request, f'/lineups/versions/{version.code}/')


def lineup_to_json(lineup, user):
    data = {
        'code': lineup.code,
        'name': lineup.name,
        'description': lineup.description,
        'format': lineup.format.name if lineup.format else None,
        'visibility': lineup.visibility,
        'created_on': lineup.created_on.isoformat(),
        'updated_on': lineup.updated_on.isoformat(),
        'versions': []
    }
    for version in lineup.get_visible_versions(user):
        version_data = {
            'code': version.code,
            'name': version.name,
            'description': version.description,
            'sort_order': version.sort_order,
            'created_on': version.created_on.isoformat(),
            'updated_on': version.updated_on.isoformat(),
            'decks': [
                {
                    'id': str(vd.deck.id),
                    'name': vd.deck.name,
                    'set': vd.deck.set.name if vd.deck.set else None,
                    'houses': [
                        vd.deck.house_1.name if vd.deck.house_1 else None,
                        vd.deck.house_2.name if vd.deck.house_2 else None,
                        vd.deck.house_3.name if vd.deck.house_3 else None,
                    ]
                }
                for vd in version.version_decks.select_related(
                    'deck__set', 'deck__house_1', 'deck__house_2', 'deck__house_3')
            ]
        }
        data['versions'].append(version_data)
    return JsonResponse(data)


def version_to_json(version):
    data = {
        'code': version.code,
        'name': version.name,
        'description': version.description,
        'sort_order': version.sort_order,
        'created_on': version.created_on.isoformat(),
        'updated_on': version.updated_on.isoformat(),
        'lineup': {
            'name': version.lineup.name,
        },
        'decks': [
            {
                'id': str(vd.deck.id),
                'name': vd.deck.name,
                'set': vd.deck.set.name if vd.deck.set else None,
                'houses': [
                    vd.deck.house_1.name if vd.deck.house_1 else None,
                    vd.deck.house_2.name if vd.deck.house_2 else None,
                    vd.deck.house_3.name if vd.deck.house_3 else None,
                ]
            }
            for vd in version.version_decks.select_related(
                'deck__set', 'deck__house_1', 'deck__house_2', 'deck__house_3')
        ]
    }
    return JsonResponse(data)


def lineup_to_xml(lineup, user):
    root = Element('lineup')
    SubElement(root, 'code').text = lineup.code
    SubElement(root, 'name').text = lineup.name
    SubElement(root, 'description').text = lineup.description or ''
    SubElement(root, 'format').text = lineup.format.name if lineup.format else ''
    SubElement(root, 'visibility').text = lineup.visibility
    SubElement(root, 'created_on').text = lineup.created_on.isoformat()
    SubElement(root, 'updated_on').text = lineup.updated_on.isoformat()

    versions_elem = SubElement(root, 'versions')
    for version in lineup.get_visible_versions(user):
        version_elem = SubElement(versions_elem, 'version')
        SubElement(version_elem, 'code').text = version.code
        SubElement(version_elem, 'name').text = version.name
        SubElement(version_elem, 'description').text = version.description or ''
        SubElement(version_elem, 'sort_order').text = str(version.sort_order)
        SubElement(version_elem, 'created_on').text = version.created_on.isoformat()
        SubElement(version_elem, 'updated_on').text = version.updated_on.isoformat()

        decks_elem = SubElement(version_elem, 'decks')
        for vd in version.version_decks.select_related(
                'deck__set', 'deck__house_1', 'deck__house_2', 'deck__house_3'):
            deck_elem = SubElement(decks_elem, 'deck')
            SubElement(deck_elem, 'id').text = str(vd.deck.id)
            SubElement(deck_elem, 'name').text = vd.deck.name or ''
            SubElement(deck_elem, 'dok_url').text = vd.deck.get_dok_url()
            SubElement(deck_elem, 'set').text = vd.deck.set.name if vd.deck.set else ''
            SubElement(deck_elem, 'house_1').text = vd.deck.house_1.name if vd.deck.house_1 else ''
            SubElement(deck_elem, 'house_2').text = vd.deck.house_2.name if vd.deck.house_2 else ''
            SubElement(deck_elem, 'house_3').text = vd.deck.house_3.name if vd.deck.house_3 else ''

    return HttpResponse(
        '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding='unicode'),
        content_type='application/xml'
    )


def version_to_xml(version):
    root = Element('version')
    SubElement(root, 'code').text = version.code
    SubElement(root, 'name').text = version.name
    SubElement(root, 'description').text = version.description or ''
    SubElement(root, 'sort_order').text = str(version.sort_order)
    SubElement(root, 'created_on').text = version.created_on.isoformat()
    SubElement(root, 'updated_on').text = version.updated_on.isoformat()

    lineup_elem = SubElement(root, 'lineup')
    SubElement(lineup_elem, 'name').text = version.lineup.name

    decks_elem = SubElement(root, 'decks')
    for vd in version.version_decks.select_related(
            'deck__set', 'deck__house_1', 'deck__house_2', 'deck__house_3'):
        deck_elem = SubElement(decks_elem, 'deck')
        SubElement(deck_elem, 'id').text = str(vd.deck.id)
        SubElement(deck_elem, 'name').text = vd.deck.name or ''
        SubElement(deck_elem, 'dok_url').text = vd.deck.get_dok_url()
        SubElement(deck_elem, 'set').text = vd.deck.set.name if vd.deck.set else ''
        SubElement(deck_elem, 'house_1').text = vd.deck.house_1.name if vd.deck.house_1 else ''
        SubElement(deck_elem, 'house_2').text = vd.deck.house_2.name if vd.deck.house_2 else ''
        SubElement(deck_elem, 'house_3').text = vd.deck.house_3.name if vd.deck.house_3 else ''

    return HttpResponse(
        '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding='unicode'),
        content_type='application/xml'
    )
