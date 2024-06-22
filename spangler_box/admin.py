from django.contrib import admin
from .models import SecretChain, SecretPlayer, SecretChainLink, SecretChainTemplate, SecretChainTemplateLink


class SecretChainAdmin(admin.ModelAdmin):
    list_display = ('description', 'created_on')
    ordering = ('created_on',)


class SecretPlayerAdmin(admin.ModelAdmin):
    list_display = ('user', 'secret_chain', 'created_on')
    ordering = ('created_on',)


class SecretChainLinkAdmin(admin.ModelAdmin):
    list_display = ('secret_chain', 'kind', 'order', 'created_on')
    ordering = ('created_on',)


class SecretChainTemplateAdmin(admin.ModelAdmin):
    list_display = ('description',)
    ordering = ('description',)


class SecretChainTemplateLinkAdmin(admin.ModelAdmin):
    list_display = ('secret_chain_template', 'kind', 'order')
    ordering = ('secret_chain_template', 'order',)


admin.site.register(SecretChain, SecretChainAdmin)
admin.site.register(SecretPlayer, SecretPlayerAdmin)
admin.site.register(SecretChainLink, SecretChainLinkAdmin)
admin.site.register(SecretChainTemplate, SecretChainTemplateAdmin)
admin.site.register(SecretChainTemplateLink, SecretChainTemplateLinkAdmin)
