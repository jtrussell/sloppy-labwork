from django.shortcuts import render


def privacy(request):
    print('heree!')
    return render(request, 'common/privacy.html')


def terms(request):
    return render(request, 'common/terms.html')
