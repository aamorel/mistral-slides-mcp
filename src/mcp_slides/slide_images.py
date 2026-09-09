"""One contained attachment beside existing key-message or bullet text."""
import logging
import math
import re

from googleapiclient.errors import HttpError

from . import attachments, backgrounds
from .layouts import content_boxes, is_decoration, text_role

FRAME = (398, 132, 282, 237)
TEXT_BOXES = {'message': (50, 142, 310, 220), 'body': (62, 128, 298, 253)}
LIMITS = {'message': (90, 90), 'body': (55, 150)}
DESCRIPTION = 'User-provided image, displayed in full beside the slide text.'


def image_id(suffix):
    return f'mvp_attachment_{suffix}'


def managed_image(element, suffix):
    return (element.get('objectId') == image_id(suffix) and 'image' in element
            and element.get('description') == DESCRIPTION)


def has_image(page):
    suffix = page['objectId'].rsplit('_', 1)[-1]
    return any(managed_image(e, suffix) for e in page.get('pageElements', []))


def points(dimension):
    scale = {'PT': 1, 'EMU': 1 / 12700}.get(dimension.get('unit'))
    if scale is None:
        raise ValueError('Unknown dimension unit')
    value = dimension.get('magnitude', 0) * scale
    if not math.isfinite(value):
        raise ValueError('Invalid dimension')
    return value


def geometry(element):
    size, transform = element['size'], element['transform']
    if transform.get('shearX', 0) or transform.get('shearY', 0):
        raise ValueError('Rotated or sheared element')
    sx, sy = transform.get('scaleX', 0), transform.get('scaleY', 0)
    if sx <= 0 or sy <= 0:
        raise ValueError('Reflected or collapsed element')
    return (points({'magnitude': transform.get('translateX', 0), 'unit': transform['unit']}),
            points({'magnitude': transform.get('translateY', 0), 'unit': transform['unit']}),
            points(size['width']) * sx, points(size['height']) * sy)


def matches(element, expected):
    try:
        return all(abs(a - b) < .1 for a, b in zip(geometry(element), expected))
    except (KeyError, TypeError, ValueError):
        return False


def text_fits(role, lines):
    per_line, total = LIMITS[role]
    if not (1 <= len(lines) <= (1 if role == 'message' else 3)
            and all(len(line) <= per_line for line in lines) and sum(map(len, lines)) <= total):
        return False
    # Conservative wrap estimate across the four supported fonts. Character
    # caps alone miss wide glyphs and long words. This is not visual verification.
    size = 26 if role == 'message' else 18
    width = TEXT_BOXES[role][2] - (48 if role == 'body' else 16)
    def advance(char):
        if char.isspace():
            return .4 * size
        if char in 'MWmw@%' or not char.isascii():
            return 1.3 * size
        return (1 if char.isupper() else .8) * size
    line_count = 0
    for paragraph in lines:
        used, count = 0, 1
        for word in paragraph.split():
            length = sum(advance(c) for c in word)
            if used and used + .4 * size + length > width:
                count += 1
                used = 0
            elif used:
                used += .4 * size
            for char in word:
                if used + advance(char) > width:
                    count += 1
                    used = 0
                used += advance(char)
        line_count += count
    return line_count * size * 1.25 + len(lines) * 8 <= TEXT_BOXES[role][3] - 12


def inspect_page(page):
    """Conservative admission: original text/geometry only, no arbitrary re-layout."""
    from .editing import paragraphs
    from .styling import inspect_slide

    inspected = inspect_slide(page)
    if not inspected['supported']:
        raise ValueError('This slide contains unsupported elements.')
    match = re.fullmatch(r'mvp_slide_([1-9]\d*)', page['objectId'])
    if not match:
        raise ValueError('Use a generated content slide; cover images are not changed by this tool.')
    suffix = match[1]
    texts = {text_role(e['objectId']): e for e in inspected['texts']}
    role = 'message' if 'message' in texts else 'body'
    if set(texts) != {'title', role} or len(inspected['texts']) != 2:
        raise ValueError('Images are supported only on key-message and bullet slides.')
    attached = [e for e in page.get('pageElements', []) if managed_image(e, suffix)]
    if len(attached) > 1:
        raise ValueError('Only one managed image per slide is supported.')
    lines = [p['text'] for p in paragraphs(texts[role])]
    if not text_fits(role, lines):
        raise ValueError('There is not enough room beside an image. Shorten the text: up to 90 message characters, or 3 bullets of 55 characters each (150 total). Wide text may need further shortening.')
    kind = 'key_message' if role == 'message' else 'bullets'
    dummy = {'type': kind, 'title': '', 'message': '', 'bullets': []}
    original = {r: (box, font) for r, _, box, font, _ in content_boxes(dummy)}
    fonts = ('Arial', 'Verdana', 'Georgia', 'Trebuchet MS')
    for text_role_name, element in texts.items():
        expected = TEXT_BOXES[role] if attached and text_role_name == role else original[text_role_name][0]
        if not matches(element, expected):
            raise ValueError('The text geometry was changed manually. Image placement is unavailable on this slide.')
        for entry in element['shape']['text']['textElements']:
            run = entry.get('textRun', {})
            if not run.get('content', '').strip():
                continue
            style = run.get('style', {})
            if style.get('fontFamily') not in fonts or abs(points(style.get('fontSize', {})) - original[text_role_name][1]) > .1:
                raise ValueError('Use the original font sizes and a supported font before adding an image.')
        autofit = element['shape'].get('shapeProperties', {}).get('autofit', {})
        if autofit.get('fontScale', 1) != 1 or autofit.get('autofitType', 'NONE') != 'NONE':
            raise ValueError('Automatically resized text is unsupported for image placement.')
        if text_role_name == role:
            for entry in element['shape']['text']['textElements']:
                marker = entry.get('paragraphMarker')
                if marker is None:
                    continue
                style = marker.get('style', {})
                # Google's standard level-zero bullet style can use 36 pt text
                # indentation (18 pt first line). It is not a custom layout.
                # Allow small PT/EMU conversion differences at each boundary.
                max_indent = 36 if role == 'body' else 0
                if (style.get('lineSpacing', 100) > 110.1 or marker.get('bullet', {}).get('nestingLevel', 0) != 0
                        or any(points(style.get(key, {'magnitude': 0, 'unit': 'PT'})) > maximum + .1
                               for key, maximum in [('spaceAbove', 0), ('spaceBelow', 8), ('indentStart', max_indent), ('indentEnd', 0)])):
                    raise ValueError('Custom paragraph spacing or indentation is unsupported for image placement. Shortening the wording will not fix this formatting issue.')
    # Rules and managed images may have been moved over the future text/image area.
    from .layouts import decoration_boxes
    rules = {f'mvp_{r}_{suffix}': box for r, box in decoration_boxes(kind)}
    for element in page.get('pageElements', []):
        if is_decoration(element, suffix) and (element['objectId'] not in rules or not matches(element, rules[element['objectId']])):
            raise ValueError('A decorative rule was moved or changed.')
        if element['objectId'] == f'mvp_gradient_{suffix}' and not matches(element, (0, 0, 720, 405)):
            raise ValueError('The background gradient geometry was changed.')
    if attached:
        x, y, w, h = geometry(attached[0])
        fx, fy, fw, fh = FRAME
        if x < fx - .1 or y < fy - .1 or x + w > fx + fw + .1 or y + h > fy + fh + .1:
            raise ValueError('The existing image was moved outside its supported frame.')
    return {'suffix': suffix, 'role': role, 'text': texts[role], 'image': attached[0] if attached else None}


def capability(page):
    try:
        inspected = inspect_page(page)
        return {'supported': True, 'has_image': bool(inspected['image']), 'fit': 'contain', 'placement': 'right'}
    except (ValueError, KeyError, TypeError, RuntimeError) as exc:
        return {'supported': False, 'has_image': has_image(page), 'reason': str(exc)}


def requests(page, inspected, url, dimensions):
    suffix, element = inspected['suffix'], inspected['text']
    result = []
    if inspected['image']:
        result.append({'deleteObject': {'objectId': image_id(suffix)}})
    else:
        x, y, w, h = TEXT_BOXES[inspected['role']]
        result.append({'updatePageElementTransform': {'objectId': element['objectId'], 'applyMode': 'ABSOLUTE',
            'transform': {'scaleX': w / points(element['size']['width']), 'scaleY': h / points(element['size']['height']),
                          'shearX': 0, 'shearY': 0, 'translateX': x, 'translateY': y, 'unit': 'PT'}}})
    fx, fy, fw, fh = FRAME
    width, height = dimensions
    ratio = min(fw / width, fh / height)
    w, h = width * ratio, height * ratio
    result.extend([
        {'createImage': {'objectId': image_id(suffix), 'url': url, 'elementProperties': {
            'pageObjectId': page['objectId'],
            'size': {'width': {'magnitude': w, 'unit': 'PT'}, 'height': {'magnitude': h, 'unit': 'PT'}},
            'transform': {'scaleX': 1, 'scaleY': 1, 'translateX': fx + (fw-w)/2,
                          'translateY': fy + (fh-h)/2, 'unit': 'PT'}}}},
        {'updatePageElementAltText': {'objectId': image_id(suffix), 'title': 'Attached image', 'description': DESCRIPTION}},
    ])
    return result


async def set_image(creds, subject, presentation_id, slide_id, revision, image_url, replace):
    from starlette.concurrency import run_in_threadpool
    from .editing import EditError, read_deck
    service, raw, deck = await run_in_threadpool(read_deck, creds, presentation_id)
    if not deck['revision_id'] or deck['revision_id'] != revision:
        raise EditError('The deck changed or its revision is unavailable. Read it again before adding an image.')
    try:
        if any(abs(points(raw.get('pageSize', {}).get(axis, {})) - expected) > .1
               for axis, expected in [('width', 720), ('height', 405)]):
            raise ValueError()
    except (ValueError, TypeError):
        raise EditError('Only original 720 × 405 point decks support image placement.') from None
    page = next((p for p in raw.get('slides', []) if p['objectId'] == slide_id), None)
    if page is None:
        raise EditError('Slide not found. Read the deck and resolve its current position including the cover.')
    try:
        inspected = inspect_page(page)
    except (ValueError, KeyError, TypeError) as exc:
        raise EditError('No image added. ' + str(exc)) from None
    if bool(inspected['image']) != replace:
        raise EditError('This slide already has an image. Use replace=true only when replacement was requested.'
                        if inspected['image'] else 'There is no image to replace; use replace=false to add one.')
    data, dimensions = await attachments.retrieve(image_url)
    token, url = await run_in_threadpool(backgrounds.publish_image, subject, data)
    try:
        batch = requests(page, inspected, url, dimensions)
        try:
            response = await run_in_threadpool(lambda: service.presentations().batchUpdate(
                presentationId=presentation_id, body={'requests': batch,
                    'writeControl': {'requiredRevisionId': revision}}).execute(num_retries=0))
        except HttpError as exc:
            if exc.resp.status in (400, 409, 412):
                raise EditError('Google rejected image placement; read the deck again before retrying.') from None
            raise EditError(f'Image placement could not be confirmed. Read the deck and check {image_id(inspected["suffix"])} before retrying.') from None
        except Exception:
            raise EditError(f'Image placement could not be confirmed. Read the deck and check {image_id(inspected["suffix"])} before retrying.') from None
    finally:
        try:
            await run_in_threadpool(backgrounds.remove_image, token)
        except Exception:
            logging.getLogger(__name__).warning('temporary_image_cleanup_failed')
    return {'status': 'replaced' if replace else 'added', 'presentation_id': presentation_id,
            'presentation_url': deck['presentation_url'], 'slide_id': slide_id,
            'position': next(s['position'] for s in deck['slides'] if s['slide_id'] == slide_id),
            'image_id': image_id(inspected['suffix']), 'revision_id': response.get('writeControl', {}).get('requiredRevisionId'),
            'changes': [{'slide_id': slide_id, 'action': 'image_replaced' if replace else 'image_added',
                         'placement': 'right', 'fit': 'contain'}], 'warnings': []}
