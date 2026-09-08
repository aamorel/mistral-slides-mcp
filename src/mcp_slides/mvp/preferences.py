"""Validated, connection-scoped style preferences. No executable style instructions."""
from contextlib import closing
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import auth


class StyleSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    background: str = Field(pattern=r'^#[0-9A-Fa-f]{6}$')
    title_color: str = Field(pattern=r'^#[0-9A-Fa-f]{6}$')
    body_color: str = Field(pattern=r'^#[0-9A-Fa-f]{6}$')
    font_family: Literal['Arial', 'Verdana', 'Georgia', 'Trebuchet MS']

    @model_validator(mode='after')
    def check_contrast(self):
        def luminance(color):
            channels = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
            return sum((c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4) * w
                       for c, w in zip(channels, (.2126, .7152, .0722)))
        for color in (self.title_color, self.body_color):
            low, high = sorted([luminance(self.background), luminance(color)])
            if (high + .05) / (low + .05) < 4.5:
                raise ValueError('Title and body colors must each have at least 4.5:1 contrast against the background.')
        return self

    def palette(self):
        return {'background': self.background[1:], 'title': self.title_color[1:],
                'body': self.body_color[1:], 'font_family': self.font_family}


DEFAULT_STYLE = StyleSettings(background='#FFFFFF', title_color='#244B63', body_color='#263238', font_family='Arial')


def result(settings, saved):
    return {'saved': saved, 'settings': settings.model_dump(),
            'markdown': f'# Default presentation style\n\n- Background: {settings.background}\n'
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
        db.execute('insert into style_preferences values (?, ?) on conflict(subject) do update set settings_json=excluded.settings_json',
                   (subject, settings.model_dump_json()))
        db.commit()
    return result(settings, True)


def reset_style(subject):
    with closing(auth.connect()) as db:
        db.execute('delete from style_preferences where subject=?', (subject,))
        db.commit()
    return result(DEFAULT_STYLE, False)
