"""Deterministic corner gradients, hosted only while Google copies the image."""
from contextlib import contextmanager
from io import BytesIO
import logging
import re
from urllib.parse import parse_qs, urlsplit, urlunsplit, urlencode

from PIL import Image

from . import backgrounds
from .preferences import gradient_colors


def render(background, accent):
    stops = [bytes.fromhex(color[1:]) for color in gradient_colors(background, accent)]
    width, height = 1600, 900
    # A broad soft tint in the upper right, fading to the base at other edges.
    x_weights = [x / (width - 1) for x in range(width)]
    data = b''.join(b''.join(stops[round(255 * weight * (1 - y / (height - 1)))]
                             for weight in x_weights) for y in range(height))
    output = BytesIO()
    Image.frombytes('RGB', (width, height), data).save(output, format='PNG')
    return output.getvalue()


@contextmanager
def image_pool(subject):
    cached, tokens = {}, []

    def publish(background, accent):
        key = (background.upper(), accent.upper())
        if key not in cached:
            token, url = backgrounds.publish_image(subject, render(*key))
            tokens.append(token)
            cached[key] = url
        return cached[key]

    try:
        yield publish
    finally:
        for token in tokens:
            try:
                backgrounds.remove_image(token)
            except Exception:
                logging.getLogger(__name__).warning('gradient_image_cleanup_failed')


def inspect(element, suffix):
    if element.get('objectId') != f'mvp_gradient_{suffix}' or 'image' not in element:
        return None
    try:
        properties = element['image'].get('imageProperties', {})
        if properties.get('brightness', 0) != 0 or properties.get('contrast', 0) != 0 or properties.get('recolor'):
            return None
        source_url = element['image'].get('sourceUrl', '')
        query = parse_qs(urlsplit(source_url).query)
        if query.get('gradient_v') not in (['1'], ['2']):
            return None
        base, accent = query['base'][0], query['accent'][0]
        if not all(re.fullmatch(r'[0-9A-Fa-f]{6}', c) for c in (base, accent)):
            return None
        if element.get('description') != description('#' + base, '#' + accent):
            return None
        return {'background': '#' + base, 'gradient_color': '#' + accent}
    except (ValueError, TypeError, KeyError, IndexError):
        return None


def description(background, accent):
    return f'Soft corner gradient from {background} with a gentle {accent} tint, fading toward the lower left.'


def with_images(subject, operation, *args, **kwargs):
    with image_pool(subject) as publish:
        return operation(*args, **kwargs, publish_gradient=publish)


def requests(index, background, accent, url):
    object_id = f'mvp_gradient_{index}'
    # The original source URL survives Google's copy; query parameters preserve
    # the rendering settings without putting machine metadata into accessible alt text.
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    query.update(gradient_v=['2'], base=[background[1:]], accent=[accent[1:]])
    url = urlunsplit(parts._replace(query=urlencode(query, doseq=True)))
    return [
        {'createImage': {'objectId': object_id, 'url': url, 'elementProperties': {
            'pageObjectId': f'mvp_slide_{index}',
            'size': {'width': {'magnitude': 720, 'unit': 'PT'}, 'height': {'magnitude': 405, 'unit': 'PT'}},
            'transform': {'scaleX': 1, 'scaleY': 1, 'translateX': 0, 'translateY': 0, 'unit': 'PT'}}}},
        {'updatePageElementAltText': {'objectId': object_id, 'title': 'Subtle gradient background', 'description': description(background, accent)}},
        {'updatePageElementsZOrder': {'pageElementObjectIds': [object_id], 'operation': 'SEND_TO_BACK'}},
    ]
