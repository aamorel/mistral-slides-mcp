"""Style updates preserve content, honor revisions, and report unsupported slides."""
import asyncio
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

from googleapiclient.errors import HttpError
from mcp.server.mcpserver.exceptions import ToolError
from mcp_slides import editing, preferences, server, styling
from test_editing import box

SETTINGS = preferences.StyleSettings(background='#FFFFFF', title_color='#D32F2F', body_color='#263238', font_family='Georgia', gradient=False)
DECK = {'title': 'Trees', 'revisionId': 'rev1', 'slides': [
    {'objectId': 'mvp_slide_0', 'pageElements': [box('mvp_title_0', ['Trees']),
        {'objectId': 'mvp_cover_band', 'shape': {'shapeType': 'TEXT_BOX'}},
        {'objectId': 'mvp_cover_image', 'image': {'contentUrl': 'unchanged'}}]},
    {'objectId': 'mvp_slide_1', 'pageElements': [box('mvp_title_1', ['Forests']), box('mvp_body_1', ['Oak', 'Pine'])]},
    {'objectId': 'custom_slide', 'pageElements': [box('custom_text', ['Custom'])]}]}


class StylingTests(unittest.TestCase):
    def service(self, deck=DECK):
        service = MagicMock()
        service.presentations.return_value.get.return_value.execute.return_value = copy.deepcopy(deck)
        return service

    def test_applies_only_style_fields_and_reports_skipped_slides(self):
        service = self.service()
        with patch.object(editing, 'build', return_value=service):
            result = styling.apply_style('alice', 'deck1', 'rev1', preferences.StyleChanges(**SETTINGS.model_dump()))
            read = editing.get_deck('alice', 'deck1')
        self.assertTrue(read['slides'][0]['style']['supported'])
        self.assertFalse(read['slides'][2]['style']['supported'])
        self.assertEqual(result['applied_slide_ids'], ['mvp_slide_0', 'mvp_slide_1'])
        self.assertEqual(result['skipped_slides'][0]['slide_id'], 'custom_slide')
        self.assertEqual(result['presentation_url'], 'https://docs.google.com/presentation/d/deck1/edit')
        batch = service.presentations.return_value.batchUpdate.call_args.kwargs['body']
        self.assertEqual(batch['writeControl'], {'requiredRevisionId': 'rev1'})
        self.assertEqual(len(batch['requests']), 6)
        for request in batch['requests']:
            kind, operation = next(iter(request.items()))
            self.assertIn(kind, ('updatePageProperties', 'updateShapeProperties', 'updateTextStyle'))
            self.assertNotIn(operation['objectId'], ('mvp_cover_image', 'custom_text', 'custom_slide'))
            if kind == 'updateTextStyle':
                self.assertEqual(operation['fields'], 'fontFamily,foregroundColor')
                self.assertEqual(operation['style']['fontFamily'], 'Georgia')
                color = '#263238' if operation['objectId'].startswith('mvp_body') else '#D32F2F'
                self.assertEqual(operation['style']['foregroundColor']['opaqueColor']['rgbColor'], styling.rgb(color[1:]))
        service.presentations.return_value.batchUpdate.return_value.execute.assert_called_once_with(num_retries=0)

    def test_modified_cover_and_unsupported_text_skip_whole_slide(self):
        for element in (box('custom', ['Other']), {'objectId': 'group', 'elementGroup': {'children': []}}):
            page = copy.deepcopy(DECK['slides'][1])
            page['pageElements'].append(element)
            service = self.service({'revisionId': 'rev1', 'slides': [page]})
            with patch.object(editing, 'build', return_value=service):
                result = styling.apply_style('alice', 'deck1', 'rev1', preferences.StyleChanges(**SETTINGS.model_dump()))
            self.assertEqual(result['status'], 'unsupported')
            service.presentations.return_value.batchUpdate.assert_not_called()
        page = copy.deepcopy(DECK['slides'][0])
        page['pageElements'][1] = box('mvp_cover_band', [''])
        self.assertTrue(styling.inspect_slide(page)['supported'])
        page['pageElements'][1] = box('mvp_cover_band', ['Manual text'])
        self.assertFalse(styling.inspect_slide(page)['supported'])
        page = copy.deepcopy(DECK['slides'][1])
        page['pageElements'][0]['shape']['text']['textElements'][1]['textRun']['style']['link'] = {'url': 'https://example.com'}
        self.assertFalse(styling.inspect_slide(page)['supported'])

    def test_stale_or_missing_revision_never_writes(self):
        for revision in ('old', None):
            deck = {**DECK, 'revisionId': revision}
            service = self.service(deck)
            with patch.object(editing, 'build', return_value=service):
                with self.assertRaisesRegex(editing.EditError, 'Read it again'):
                    styling.apply_style('alice', 'deck1', 'rev1', preferences.StyleChanges(**SETTINGS.model_dump()))
            service.presentations.return_value.batchUpdate.assert_not_called()

    def test_conflicts_and_uncertain_writes_are_not_retried(self):
        for error in (HttpError(SimpleNamespace(status=409, reason='Conflict'), b'private'), TimeoutError()):
            service = self.service()
            service.presentations.return_value.batchUpdate.return_value.execute.side_effect = error
            with patch.object(editing, 'build', return_value=service):
                with self.assertRaisesRegex(editing.EditError, 'Read the deck') as caught:
                    styling.apply_style('alice', 'deck1', 'rev1', preferences.StyleChanges(**SETTINGS.model_dump()))
            self.assertNotIn('private', str(caught.exception))
            service.presentations.return_value.batchUpdate.return_value.execute.assert_called_once_with(num_retries=0)

    def test_tool_uses_connection_defaults_and_requires_authentication(self):
        with patch.object(server, 'get_access_token', return_value=None), patch.object(styling, 'apply_style') as apply:
            with self.assertRaises(ToolError):
                asyncio.run(server.set_presentation_style('deck1', 'rev1', use_default_style=True))
            apply.assert_not_called()
        with patch.object(server, 'get_access_token', return_value=SimpleNamespace(subject='alice')), patch.object(server.auth, 'load_credentials', return_value='alice-creds'), patch.object(preferences, 'get_style', return_value=preferences.result(SETTINGS, True)) as get, patch.object(styling, 'apply_style', return_value={'status': 'applied'}) as apply:
            asyncio.run(server.set_presentation_style('deck1', 'rev1', use_default_style=True))
            get.assert_called_once_with('alice')
            apply.assert_called_once_with('alice-creds', 'deck1', 'rev1', preferences.StyleChanges(**SETTINGS.model_dump()), publish_gradient=ANY)

    def colored_deck(self):
        deck = copy.deepcopy(DECK)
        for page in deck['slides']:
            page['pageProperties'] = {'pageBackgroundFill': {'solidFill': {
                'color': {'rgbColor': styling.rgb('FFFFFF')}}}}
            for element in page['pageElements']:
                if element['objectId'] == 'mvp_cover_band':
                    element['shape']['shapeProperties'] = {'shapeBackgroundFill': page['pageProperties']['pageBackgroundFill']}
                for entry in element.get('shape', {}).get('text', {}).get('textElements', []):
                    if 'textRun' in entry:
                        entry['textRun']['style'].update(fontFamily='Georgia', foregroundColor={
                            'opaqueColor': {'rgbColor': styling.rgb('263238')}})
        return deck

    def test_partial_title_color_preserves_background_font_and_body(self):
        service = self.service(self.colored_deck())
        service.presentations.return_value.batchUpdate.return_value.execute.return_value = {
            'writeControl': {'requiredRevisionId': 'rev2'}}
        with patch.object(editing, 'build', return_value=service):
            result = styling.apply_style('alice', 'deck1', 'rev1', preferences.StyleChanges(title_color='#244B63'))
        requests = service.presentations.return_value.batchUpdate.call_args.kwargs['body']['requests']
        self.assertEqual(len(requests), 2)
        for request in requests:
            update = request['updateTextStyle']
            self.assertTrue(update['objectId'].startswith('mvp_title_'))
            self.assertEqual(update['fields'], 'foregroundColor')
            self.assertNotIn('fontFamily', update['style'])
        self.assertEqual(result['revision_id'], 'rev2')

    def test_background_change_checks_existing_text_and_skips_unsafe_slides(self):
        service = self.service(self.colored_deck())
        with patch.object(editing, 'build', return_value=service):
            result = styling.apply_style('alice', 'deck1', 'rev1', preferences.StyleChanges(background='#263238'))
        self.assertEqual(result['status'], 'unsupported')
        self.assertEqual(len(result['warnings']), 3)
        service.presentations.return_value.batchUpdate.assert_not_called()

    def test_font_only_needs_no_color_inference(self):
        service = self.service()
        with patch.object(editing, 'build', return_value=service):
            styling.apply_style('alice', 'deck1', 'rev1', preferences.StyleChanges(font_family='Verdana'))
        for request in service.presentations.return_value.batchUpdate.call_args.kwargs['body']['requests']:
            self.assertEqual(request['updateTextStyle']['fields'], 'fontFamily')

    def test_deck_changes_do_not_read_or_write_defaults_and_reject_ambiguous_mode(self):
        changes = preferences.StyleChanges(title_color='#244B63')
        with patch.object(server, 'connection_subject', return_value='alice'), patch.object(server, 'connected_credentials', return_value='creds'), patch.object(preferences, 'get_style') as get, patch.object(preferences, 'set_style') as save, patch.object(styling, 'apply_style', return_value={'status': 'applied'}) as apply:
            asyncio.run(server.set_presentation_style('deck1', 'rev1', changes))
            get.assert_not_called()
            save.assert_not_called()
            apply.assert_called_once_with('creds', 'deck1', 'rev1', changes, publish_gradient=ANY)
            for values in ({}, {'changes': changes, 'use_default_style': True}):
                with self.assertRaises(ToolError):
                    asyncio.run(server.set_presentation_style('deck1', 'rev1', **values))
