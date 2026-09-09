"""Validated, connection-scoped style preferences. No executable style instructions."""
from contextlib import closing
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import auth


def validate_contrast(background: str, foreground: str):
    def luminance(color):
        channels = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
        return sum((c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4) * w
                   for c, w in zip(channels, (.2126, .7152, .0722)))

    low, high = sorted([luminance(background), luminance(foreground)])
    if (high + .05) / (low + .05) < 4.5:
        raise ValueError('Title and body colors must each have at least 4.5:1 contrast against the background.')


def gradient_colors(background, accent):
    """All quantized stops in our fixed, gentle 12% corner tint."""
    base = tuple(int(background[i:i+2], 16) for i in (1, 3, 5))
    tint = tuple(int(accent[i:i+2], 16) for i in (1, 3, 5))
    return ['#' + ''.join(f'{round(a + (b-a) * .12 * n / 255):02X}'
                         for a, b in zip(base, tint)) for n in range(256)]


def validate_background_contrast(background, foreground, gradient=False, gradient_color='#93B4E8'):
    for color in set(gradient_colors(background, gradient_color) if gradient else [background]):
        validate_contrast(color, foreground)


class StyleSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    background: str = Field(pattern=r'^#[0-9A-Fa-f]{6}$')
    title_color: str = Field(pattern=r'^#[0-9A-Fa-f]{6}$')
    body_color: str = Field(pattern=r'^#[0-9A-Fa-f]{6}$')
    font_family: Literal['Arial', 'Verdana', 'Georgia', 'Trebuchet MS']
    gradient: bool = True
    gradient_color: str = Field(default='#93B4E8', pattern=r'^#[0-9A-Fa-f]{6}$')

    @model_validator(mode='after')
    def check_contrast(self):
        for color in (self.title_color, self.body_color):
            validate_background_contrast(self.background, color, self.gradient, self.gradient_color)
        return self

    def palette(self):
        return {'background': self.background[1:], 'title': self.title_color[1:],
                'body': self.body_color[1:], 'font_family': self.font_family,
                'gradient': self.gradient, 'gradient_color': self.gradient_color[1:]}


class StyleChanges(BaseModel):
    """Only supplied fields are changed; null is not a style value."""
    model_config = ConfigDict(extra='forbid')
    background: str | None = Field(default=None, pattern=r'^#[0-9A-Fa-f]{6}$')
    title_color: str | None = Field(default=None, pattern=r'^#[0-9A-Fa-f]{6}$')
    body_color: str | None = Field(default=None, pattern=r'^#[0-9A-Fa-f]{6}$')
    font_family: Literal['Arial', 'Verdana', 'Georgia', 'Trebuchet MS'] | None = None
    gradient: bool | None = None
    gradient_color: str | None = Field(default=None, pattern=r'^#[0-9A-Fa-f]{6}$')

    @model_validator(mode='after')
    def check_changes(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('Supply at least one style field; omit unchanged fields instead of using null.')
        return self


DEFAULT_STYLE = StyleSettings(background='#FFFFFF', title_color='#244B63', body_color='#263238', font_family='Arial')


def result(settings, saved):
    return {'saved': saved, 'settings': settings.model_dump(),
            'markdown': f'# Default presentation style\n\n- Background: {settings.background}\n'
                        f'- Gradient: {"on" if settings.gradient else "off"}\n- Gradient color: {settings.gradient_color}\n'
                        f'- Title color: {settings.title_color}\n- Body color: {settings.body_color}\n'
                        f'- Font: {settings.font_family}\n',
            'scope': 'This connection only. Applies to future decks; reconnecting starts a new preference scope.'}


def get_style(subject):
    with closing(auth.connect()) as db:
        row = db.execute('select settings_json from style_preferences where subject=?', (subject,)).fetchone()
    return result(StyleSettings.model_validate_json(row[0]) if row else DEFAULT_STYLE, bool(row))


def set_style(subject, settings):
    with closing(auth.connect()) as db:
        db.execute('begin immediate')
        # A concurrent disconnect must not recreate personal state.
        if not db.execute('select 1 from google_tokens where connection_id=?', (subject,)).fetchone():
            raise RuntimeError('Reconnect this connector before saving a style.')
        row = db.execute('select settings_json from style_preferences where subject=?', (subject,)).fetchone()
        current = StyleSettings.model_validate_json(row[0]) if row else DEFAULT_STYLE
        settings = StyleSettings.model_validate({**current.model_dump(), **settings.model_dump(exclude_unset=True)})
        db.execute('insert into style_preferences values (?, ?) on conflict(subject) do update set settings_json=excluded.settings_json',
                   (subject, settings.model_dump_json()))
        db.commit()
    return result(settings, True)


def reset_style(subject):
    with closing(auth.connect()) as db:
        db.execute('delete from style_preferences where subject=?', (subject,))
        db.commit()
    return result(DEFAULT_STYLE, False)
