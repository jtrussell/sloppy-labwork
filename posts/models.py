from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse


STATUS = (
    (0, "Draft"),
    (1, "Published")
)


class Post(models.Model):
    title = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=200, unique=True)
    author = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='posts')
    updated_on = models.DateTimeField(auto_now=True)
    summary = models.TextField(blank=True)
    featured_image_url = models.URLField(max_length=500, blank=True)
    featured_image_alt = models.CharField(max_length=200, blank=True)
    content = models.TextField()
    created_on = models.DateTimeField(auto_now_add=True)
    published_on = models.DateTimeField()
    status = models.IntegerField(choices=STATUS, default=0)

    class Meta:
        ordering = ['-published_on']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('posts-detail', args=[self.slug])

    @property
    def is_draft(self):
        return self.status == 0
