"""Typed outline boundaries and consistent rendering/editing/styling roles."""
import unittest
from unittest.mock import MagicMock, patch

from mcp_slides.mvp import outline, slides, layouts, editing, styling, preferences
from test_editing import box

TYPES = [
    {'type': 'key_message', 'title': 'Takeaway', 'message': 'Phones became our primary computers.'},
    {'type': 'bullets', 'title': 'Challenges', 'bullets': ['Repairability']},
    {'type': 'comparison', 'title': 'Two generations', 'left': {'heading': 'Feature phones', 'bullets': ['Calls', 'Long battery life']}, 'right': {'heading': 'Smartphones', 'bullets': ['General-purpose apps']}},
    {'type': 'steps', 'title': 'Connect a call', 'steps': ['Find a network', 'Route the call', 'Transmit audio']},
]


class SlideTypeTests(unittest.TestCase):
    def test_schema_accepts_all_types_and_variable_counts(self):
        deck = {'title': 'Phones', 'slides': TYPES}
        self.assertEqual(outline.validate_outline(deck, 4), deck)
        for count in (1, 5):
            slide = {'type': 'bullets', 'title': 'Points', 'bullets': ['Point'] * count}
            self.assertEqual(outline.validate_outline({'title': 'Demo', 'slides': [slide]}, 1)['slides'][0], slide)

    def test_rejects_invalid_type_counts_budgets_and_fields(self):
        invalid = [
            {**TYPES[0], 'type': 'chart'}, {**TYPES[0], 'message': 'x' * 181},
            {**TYPES[0], 'message': 'Line\nbreak'}, {**TYPES[0], 'api_calls': []},
            {**TYPES[1], 'bullets': []}, {**TYPES[1], 'bullets': ['a'] * 6},
            {**TYPES[1], 'bullets': ['x' * 100] * 5},
            {**TYPES[2], 'left': {'heading': 'x' * 41, 'bullets': ['a']}},
            {**TYPES[2], 'left': {'heading': 'Left', 'bullets': ['x' * 70] * 3}},
            {**TYPES[3], 'steps': ['Only one']}, {**TYPES[3], 'steps': ['x' * 90] * 4},
        ]
        for slide in invalid:
            with self.subTest(slide=slide), self.assertRaises(ValueError):
                outline.validate_outline({'title': 'Demo', 'slides': [slide]}, 1)
        with patch.object(slides, 'build') as build, self.assertRaises(ValueError):
            slides.create_deck(None, {'title': 'Demo', 'slides': [invalid[0]]}, palette=preferences.DEFAULT_STYLE.palette(), cover_image_url='https://example.com/cover.png')
        build.assert_not_called()

    def test_rendered_types_keep_editable_roles_and_style_support(self):
        fake = MagicMock()
        fake.presentations.return_value.create.return_value.execute.return_value = {'presentationId': 'deck1'}
        fake.presentations.return_value.get.return_value.execute.return_value = {}
        with patch.object(slides, 'build', return_value=fake):
            slides.create_deck(None, {'title': 'Phones', 'slides': TYPES}, palette=preferences.DEFAULT_STYLE.palette(), cover_image_url='https://example.com/cover.png')
        requests = fake.presentations.return_value.batchUpdate.call_args.kwargs['body']['requests']
        lists = {r['createParagraphBullets']['objectId']: r['createParagraphBullets']['bulletPreset'] for r in requests if 'createParagraphBullets' in r}
        self.assertNotIn('mvp_message_1', lists)
        self.assertEqual(lists['mvp_steps_4'], 'NUMBERED_DIGIT_ALPHA_ROMAN')
        self.assertEqual(set(lists), {'mvp_body_2', 'mvp_body_left_3', 'mvp_body_right_3', 'mvp_steps_4'})
        for index, slide in enumerate(TYPES, 1):
            page = {'objectId': f'mvp_slide_{index}', 'pageElements': []}
            for role, text, geometry, size, bullet in layouts.content_boxes(slide):
                element_id = f'mvp_{role}_{index}'
                element = box(element_id, text.split('\n'))
                page['pageElements'].append(element)
                self.assertTrue(editing.normalize_element(element)['editable'])
                x, y, w, h = geometry
                self.assertLessEqual(x + w, 720)
                self.assertLessEqual(y + h, 405)
            self.assertTrue(styling.inspect_slide(page)['supported'])
        self.assertEqual(layouts.color_role('mvp_heading_left_3'), 'title')
        self.assertEqual(layouts.color_role('mvp_body_left_3'), 'body')

    def test_edit_rejects_overall_text_budget_even_when_each_item_fits(self):
        target = {'mvp_body_left_1': {'paragraphs': ['A', 'B', 'C'],
            'max_characters': [80, 80, 80], 'max_total_characters': 180}}
        with self.assertRaisesRegex(ValueError, 'budget'):
            editing.validate_edit({'status': 'ok', 'replacements': [
                {'element_id': 'mvp_body_left_1', 'paragraphs': ['x' * 70] * 3}]}, target)

    def test_comparison_edit_changes_only_selected_column(self):
        page = {'objectId': 'mvp_slide_1', 'pageElements': [
            box('mvp_title_1', ['Comparison']), box('mvp_heading_left_1', ['Left']),
            box('mvp_body_left_1', ['First', 'Second']), box('mvp_body_right_1', ['Unchanged'])]}
        fake = MagicMock()
        fake.presentations.return_value.get.return_value.execute.return_value = {'revisionId': 'rev1', 'slides': [page]}
        with patch.object(editing, 'build', return_value=fake), patch.object(editing, 'propose_edit', return_value=[{'element_id': 'mvp_body_left_1', 'paragraphs': ['Revised', 'Second']}]) as propose:
            editing.edit_deck_slide(None, 'deck1', 'mvp_slide_1', 'rev1', 'Clarify left column', None)
        targets = propose.call_args.args[1]
        self.assertEqual(targets['mvp_heading_left_1']['max_characters'], [40])
        for request in fake.presentations.return_value.batchUpdate.call_args.kwargs['body']['requests']:
            self.assertEqual(next(iter(request.values()))['objectId'], 'mvp_body_left_1')
