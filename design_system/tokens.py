import re
from dataclasses import dataclass
from pathlib import Path

from django.contrib.staticfiles import finders
from django.core.exceptions import ImproperlyConfigured

TOKENS_STYLESHEET = 'css/tokens.css'
COMMENT = re.compile(r'/\*.*?\*/', re.S)
DECLARATION = re.compile(r'(--[a-z0-9-]+)\s*:\s*([^;]+);')
RULE = re.compile(r'^([^{}\n][^{}]*?)\s*\{([^{}]*)\}', re.M)
THEME_SELECTOR = re.compile(r'\[data-theme="(\d+)"\]')
MEDIA_BLOCK = re.compile(r'@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}')
MEDIUM_BREAKPOINT_ROOT = re.compile(r'@media \(min-width: 550px\)\s*\{\s*:root\s*\{([^{}]*)\}\s*\}')


@dataclass(frozen=True)
class Token:
    name: str
    value: str

    @property
    def group_key(self):
        return self.name[2:].split('-')[0]


def read_tokens_stylesheet():
    path = finders.find(TOKENS_STYLESHEET)
    if path is None:
        raise ImproperlyConfigured(f'{TOKENS_STYLESHEET} was not found by the staticfiles finders')
    return Path(path).read_text(encoding='utf-8')


def _rules(css):
    for selector, body in RULE.findall(MEDIA_BLOCK.sub('', COMMENT.sub('', css))):
        yield selector.strip(), body


def _declarations(body):
    return [Token(name, ' '.join(value.split())) for name, value in DECLARATION.findall(COMMENT.sub('', body))]


def root_tokens(css=None):
    css = css if css is not None else read_tokens_stylesheet()
    tokens = []
    for selector, body in _rules(css):
        selectors = [part.strip() for part in selector.split(',')]
        if selectors == [':root'] or selectors == [':root', '[data-theme="0"]']:
            tokens.extend(_declarations(body))
    return tokens


def medium_breakpoint_tokens(css=None):
    css = css if css is not None else read_tokens_stylesheet()
    return {token.name: token.value for block in MEDIUM_BREAKPOINT_ROOT.findall(COMMENT.sub('', css)) for token in _declarations(block)}


def derived_tokens(css=None):
    css = css if css is not None else read_tokens_stylesheet()
    tokens = []
    for selector, body in _rules(css):
        if [part.strip() for part in selector.split(',')] == [':root', '[data-theme]']:
            tokens.extend(_declarations(body))
    return tokens


def theme_tokens(css=None):
    css = css if css is not None else read_tokens_stylesheet()
    themes = {}
    for selector, body in _rules(css):
        selectors = [part.strip() for part in selector.split(',')]
        theme_numbers = [match.group(1) for part in selectors if (match := THEME_SELECTOR.fullmatch(part))]
        if len(theme_numbers) == 1 and len(selectors) <= 2:
            themes[theme_numbers[0]] = _declarations(body)
    return themes


def tokens_by_group(tokens):
    grouped = {}
    for token in tokens:
        grouped.setdefault(token.group_key, []).append(token)
    return grouped
