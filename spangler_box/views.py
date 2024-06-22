from django.shortcuts import render
from .forms import SelectTemplateForm
from allauth.account.decorators import login_required


@login_required
def create_from_template(request):
    if request.method == 'POST':
        form = SelectTemplateForm(request.POST)
        if form.is_valid():
            template = form.cleaned_data['template']
            # Create a new secret chain from the template
            # Redirect to the new secret chain
            # Secrets needs a "join" link
            print(template, template.owner)
    else:
        form = SelectTemplateForm()
    return render(request, 'spangler_box/page-create-from-template.html', {
        'form': form,
    })
