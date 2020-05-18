from django.views import generic
from .models import Post


class PostList(generic.ListView):
    queryset = Post.objects.filter(status=1).order_by('-published_on')
    template_name = 'posts/list.html'


class PostDetail(generic.DetailView):
    model = Post
    template_name = 'posts/detail.html'