from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View, generic
from .forms import PostForm
from .models import Post


def redirect_to(request, url):
    if request.htmx:
        resp = HttpResponse(url)
        resp['HX-Redirect'] = url
        return resp
    return redirect(url)


def can_see_drafts(user):
    return user.has_perm('posts.change_post')


class VisiblePostsMixin:
    def get_queryset(self):
        posts = Post.objects.select_related('author').order_by('-published_on')
        if can_see_drafts(self.request.user):
            return posts
        return posts.filter(status=1)


class PostList(VisiblePostsMixin, generic.ListView):
    template_name = 'posts/list.html'
    paginate_by = 10


class PostDetail(VisiblePostsMixin, generic.DetailView):
    template_name = 'posts/detail.html'


class PostCreate(PermissionRequiredMixin, generic.CreateView):
    permission_required = 'posts.add_post'
    model = Post
    form_class = PostForm
    template_name = 'posts/form.html'

    def get_initial(self):
        return {'published_on': timezone.localtime().replace(second=0, microsecond=0)}

    def form_valid(self, form):
        form.instance.author = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f'Post "{self.object.title}" created!')
        return response


class PostUpdate(PermissionRequiredMixin, generic.UpdateView):
    permission_required = 'posts.change_post'
    model = Post
    form_class = PostForm
    template_name = 'posts/form.html'

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Post "{self.object.title}" updated!')
        return response


class PostDelete(PermissionRequiredMixin, generic.DeleteView):
    permission_required = 'posts.delete_post'
    model = Post
    http_method_names = ['post']

    def form_valid(self, form):
        post_title = self.object.title
        self.object.delete()
        messages.success(self.request, f'Post "{post_title}" deleted.')
        return redirect_to(self.request, reverse('posts-list'))


class MarkdownPreview(PermissionRequiredMixin, View):
    http_method_names = ['post']

    def has_permission(self):
        user = self.request.user
        return user.has_perm('posts.add_post') or user.has_perm('posts.change_post')

    def post(self, request):
        return render(request, 'posts/partials/markdown-preview.html', {
            'markdown_source': request.POST.get('markdown', ''),
        })
