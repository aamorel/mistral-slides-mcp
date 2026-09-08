"""Stable text roles shared by rendering, reading, editing and default styling."""
import re


def text_role(element_id):
    match = re.fullmatch(r'mvp_(title|body|message|heading_left|heading_right|body_left|body_right|steps)_(\d+)', element_id)
    return match[1] if match else None


def color_role(element_id):
    role = text_role(element_id)
    return 'title' if role == 'title' or (role and role.startswith('heading_')) else 'body'


def edit_limit(element_id, paragraph_count=1):
    role = text_role(element_id)
    limit = {'title': 80, 'body': 140, 'message': 180, 'heading_left': 40,
            'heading_right': 40, 'body_left': 80, 'body_right': 80, 'steps': 100}[role]
    budget = {'body': 420, 'body_left': 180, 'body_right': 180, 'steps': 350}.get(role, limit)
    return min(limit, budget // paragraph_count)


def text_budget(element_id):
    return {'body': 420, 'body_left': 180, 'body_right': 180, 'steps': 350}.get(
        text_role(element_id), edit_limit(element_id))


def content_boxes(slide):
    """Return role, text, geometry, font size and optional list style."""
    boxes = [('title', slide['title'], (40, 28, 640, 88), 26, None)]
    kind = slide['type']
    if kind == 'comparison':
        for side, x in (('left', 40), ('right', 380)):
            column = slide[side]
            boxes += [(f'heading_{side}', column['heading'], (x, 124, 300, 52), 20, None),
                      (f'body_{side}', '\n'.join(column['bullets']), (x + 12, 186, 288, 195), 16, 'BULLET_DISC_CIRCLE_SQUARE')]
    elif kind == 'key_message':
        boxes.append(('message', slide['message'], (50, 142, 620, 220), 26, None))
    elif kind == 'steps':
        boxes.append(('steps', '\n'.join(slide['steps']), (62, 128, 590, 253), 18, 'NUMBERED_DIGIT_ALPHA_ROMAN'))
    else:
        boxes.append(('body', '\n'.join(slide['bullets']), (62, 128, 590, 253), 18, 'BULLET_DISC_CIRCLE_SQUARE'))
    return boxes
