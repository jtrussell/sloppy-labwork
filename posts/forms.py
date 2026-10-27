from django import forms
from django.utils.text import slugify
from .models import Post


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = [
            'title', 'slug', 'status', 'published_on',
            'featured_image_url', 'featured_image_alt',
            'summary', 'content',
        ]
        widgets = {
            'published_on': forms.DateTimeInput(
                attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'summary': forms.Textarea(attrs={'rows': 4}),
            'content': forms.Textarea(attrs={'rows': 20}),
        }
        labels = {
            'published_on': 'Publish date',
            'featured_image_url': 'Featured image URL',
            'featured_image_alt': 'Featured image description',
        }
        help_texts = {
            'slug': 'Used in the post URL. Leave blank to build it from the title.',
            'featured_image_alt': 'Alt text for screen readers. Leave blank if the image is decorative.',
            'summary': 'Markdown supported. Shown on the Lab Notes list; defaults to the start of the post.',
            'content': 'Markdown supported.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].required = False

    def clean_slug(self):
        return self.cleaned_data.get('slug') or slugify(self.cleaned_data.get('title', ''))
