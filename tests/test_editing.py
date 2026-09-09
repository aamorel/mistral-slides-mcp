import tempfile
from pathlib import Path
"""Boundaries, concurrency and UTF-16 updates for slide iteration."""
import asyncio
import copy
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError
from mcp.server.mcpserver.exceptions import ToolError
from mcp_slides import editing, server


def box(object_id, lines):
    entries, start = [], 0
    for text in lines:
        content = text + '\n'
        end = start + editing.utf16_length(content)
        entries.extend([
            {'startIndex': start, 'endIndex': end,
             'paragraphMarker': {'style': {'spaceAbove': {'magnitude': 4, 'unit': 'PT'}},
                                 'bullet': {'listId': 'list1', 'nestingLevel': 0}}},
            {'startIndex': start, 'endIndex': end,
             'textRun': {'content': content, 'style': {'fontSize': {'magnitude': 20, 'unit': 'PT'}}}},
        ])
        start = end
    return {'objectId': object_id, 'shape': {'shapeType': 'TEXT_BOX', 'text': {'textElements': entries}},
            'transform': {'translateX': 62}, 'size': {'width': {'magnitude': 590, 'unit': 'PT'}}}


DECK = {'presentationId': 'deck1', 'title': 'Demo', 'revisionId': 'rev1', 'slides': [
    {'objectId': 'mvp_slide_1', 'pageElements': [box('mvp_title_1', ['Manually edited title']),
        box('mvp_body_1', ['Pilot 😀', 'Budget €5,000', 'Unmeasured results']),
        {'objectId': 'photo', 'image': {}, 'description': 'Existing photo'}]},
    {'objectId': 'mvp_slide_2', 'pageElements': [box('mvp_title_2', ['Untouched'])]}]}


class EditingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        env = patch.dict(os.environ, {'TOKEN_DB_PATH': str(Path(temp.name) / 'tokens.db'),
            'PILOT_MAX_PAID_CALLS': '100', 'PILOT_PAID_CALLS_ENABLED': 'true',
            'GOOGLE_ALLOWED_DOMAIN': 'example.com', 'GOOGLE_ALLOWED_EMAILS': ''})
        env.start()
        self.addCleanup(temp.cleanup)
        self.addCleanup(env.stop)

    def service(self, deck=None):
        service = MagicMock()
        service.presentations.return_value.get.return_value.execute.return_value = copy.deepcopy(deck or DECK)
        return service

    def test_read_returns_elements_and_limitations_without_inventing_visual_content(self):
        deck = copy.deepcopy(DECK)
        deck['slides'][0]['pageElements'] += [
            {'objectId': 'table', 'table': {}}, {'objectId': 'chart', 'sheetsChart': {}},
            {'objectId': 'group', 'elementGroup': {'children': [box('mvp_body_9', ['Grouped'])]}}]
        with patch.object(editing, 'build', return_value=self.service(deck)):
            result = editing.get_deck('alice', 'deck1')
        self.assertEqual(result['revision_id'], 'rev1')
        elements = result['slides'][0]['elements']
        self.assertTrue(elements[0]['editable'])
        self.assertEqual(elements[0]['paragraphs'], ['Manually edited title'])
        for element in elements[2:]:
            self.assertFalse(element['editable'])
            self.assertIn('unsupported_reason', element)
        self.assertFalse(elements[-1]['children'][0]['editable'])
        self.assertNotIn('description', elements[2])
        self.assertEqual(elements[2]['alt_description'], 'Existing photo')

    def test_mixed_style_links_and_unfamiliar_shapes_are_not_editable(self):
        mixed = box('mvp_title_1', ['Mixed'])
        entries = mixed['shape']['text']['textElements']
        entries[1] = {'startIndex': 0, 'endIndex': 2, 'textRun': {'content': 'Mi', 'style': {'bold': True}}}
        entries.append({'startIndex': 2, 'endIndex': 6, 'textRun': {'content': 'xed\n', 'style': {}}})
        linked = box('mvp_title_1', ['Link'])
        linked['shape']['text']['textElements'][1]['textRun']['style']['link'] = {'url': 'https://example.com'}
        for element in (mixed, linked, box('custom', ['Custom']), box('mvp_title_1', [''])):
            self.assertFalse(editing.normalize_element(element)['editable'])

    def test_slide_two_edits_first_content_and_preserves_cover(self):
        deck = copy.deepcopy(DECK)
        deck['slides'].insert(0, {'objectId': 'mvp_slide_0', 'pageElements': [
            box('mvp_title_0', ['Cover']), {'objectId': 'mvp_cover_image', 'image': {}}]})
        service = self.service(deck)
        with patch.object(editing, 'build', return_value=service), \
             patch.object(editing, 'propose_edit', return_value=[
                 {'element_id': 'mvp_title_1', 'paragraphs': ['Revised content title']}]) as propose:
            current = editing.get_deck('alice', 'deck1')
            target = next(slide for slide in current['slides'] if slide['position'] == 2)
            self.assertEqual(target['slide_id'], 'mvp_slide_1')
            result = editing.edit_deck_slide('alice', 'deck1', target['slide_id'],
                                            current['revision_id'], 'Revise slide 2', None)
        self.assertEqual(result['position'], 2)
        self.assertEqual(propose.call_args.args[0]['slide_id'], 'mvp_slide_1')
        requests = service.presentations.return_value.batchUpdate.call_args.kwargs['body']['requests']
        self.assertTrue(requests)
        for request in requests:
            self.assertIn(next(iter(request)), ('insertText', 'deleteText'))
            self.assertEqual(next(iter(request.values()))['objectId'], 'mvp_title_1')

    def test_single_run_spanning_paragraphs(self):
        element = box('mvp_body_1', ['One', 'Two'])
        entries = element['shape']['text']['textElements']
        element['shape']['text']['textElements'] = [entries[0], entries[2],
            {'startIndex': 0, 'endIndex': 8, 'textRun': {'content': 'One\nTwo\n'}}]
        self.assertEqual([p['text'] for p in editing.paragraphs(element)], ['One', 'Two'])

    def test_edit_targets_only_changed_paragraphs_and_preserves_newlines(self):
        service = self.service()
        replacements = [{'element_id': 'mvp_body_1', 'paragraphs': ['Pilot 👍 revised', 'Budget €5,000', 'Not yet measured']}]
        with patch.object(editing, 'build', return_value=service), patch.object(editing, 'propose_edit', return_value=replacements) as propose:
            result = editing.edit_deck_slide('alice', 'deck1', 'mvp_slide_1', 'rev1', 'Clarify', None)
        self.assertEqual(propose.call_args.args[0]['elements'][0]['paragraphs'], ['Manually edited title'])
        body = service.presentations.return_value.batchUpdate.call_args.kwargs['body']
        self.assertEqual(body['writeControl'], {'requiredRevisionId': 'rev1'})
        self.assertEqual(len(body['requests']), 4)
        # Apply the actual ranges to UTF-16 bytes as Google does, checking Unicode
        # and that paragraph separators (which carry bullets/styles) survive.
        text = 'Pilot 😀\nBudget €5,000\nUnmeasured results\n'.encode('utf-16-le')
        for request in body['requests']:
            operation = next(iter(request.values()))
            self.assertEqual(operation['objectId'], 'mvp_body_1')
            if 'insertText' in request:
                at = operation['insertionIndex'] * 2
                text = text[:at] + operation['text'].encode('utf-16-le') + text[at:]
            else:
                interval = operation['textRange']
                removed = text[2 * interval['startIndex']:2 * interval['endIndex']].decode('utf-16-le')
                self.assertNotIn('\n', removed)
                text = text[:2 * interval['startIndex']] + text[2 * interval['endIndex']:]
        self.assertEqual(text.decode('utf-16-le'), 'Pilot 👍 revised\nBudget €5,000\nNot yet measured\n')
        self.assertEqual(result['status'], 'updated')
        self.assertEqual(len(result['changes']), 2)
        self.assertEqual(result['presentation_url'], 'https://docs.google.com/presentation/d/deck1/edit')
        service.presentations.return_value.batchUpdate.return_value.execute.assert_called_once_with(num_retries=0)

    def test_stale_revision_missing_slide_and_unsupported_slide_fail_before_mistral(self):
        for revision, slide_id in [('old', 'mvp_slide_1'), ('rev1', 'missing')]:
            service = self.service()
            with patch.object(editing, 'build', return_value=service), patch.object(editing, 'propose_edit') as propose:
                with self.assertRaises(editing.EditError):
                    editing.edit_deck_slide('alice', 'deck1', slide_id, revision, 'Clarify', None)
                propose.assert_not_called()
                service.presentations.return_value.batchUpdate.assert_not_called()
        deck = copy.deepcopy(DECK)
        deck['slides'][0]['pageElements'] = [{'objectId': 'photo', 'image': {}}]
        with patch.object(editing, 'build', return_value=self.service(deck)), patch.object(editing, 'propose_edit') as propose:
            with self.assertRaisesRegex(editing.EditError, 'No supported'):
                editing.edit_deck_slide('alice', 'deck1', 'mvp_slide_1', 'rev1', 'Clarify', None)
            propose.assert_not_called()

    def test_noop_and_unsupported_request_do_not_write(self):
        for outcome in ([], editing.EditError('No changes made. Image edits are unsupported.')):
            service = self.service()
            with patch.object(editing, 'build', return_value=service), patch.object(editing, 'propose_edit') as propose:
                if isinstance(outcome, Exception):
                    propose.side_effect = outcome
                    with self.assertRaisesRegex(editing.EditError, 'unsupported'):
                        editing.edit_deck_slide('alice', 'deck1', 'mvp_slide_1', 'rev1', 'Add image', None)
                else:
                    propose.return_value = outcome
                    self.assertEqual(editing.edit_deck_slide('alice', 'deck1', 'mvp_slide_1', 'rev1', 'Keep it', None)['status'], 'unchanged')
                service.presentations.return_value.batchUpdate.assert_not_called()

    def test_write_conflict_and_uncertain_network_outcome_are_not_retried(self):
        errors = [HttpError(SimpleNamespace(status=400, reason='Bad Request'), b'private details'), TimeoutError()]
        for error in errors:
            service = self.service()
            service.presentations.return_value.batchUpdate.return_value.execute.side_effect = error
            with patch.object(editing, 'build', return_value=service), patch.object(editing, 'propose_edit', return_value=[
                {'element_id': 'mvp_title_1', 'paragraphs': ['New title']} ]):
                with self.assertRaises(editing.EditError) as caught:
                    editing.edit_deck_slide('alice', 'deck1', 'mvp_slide_1', 'rev1', 'Clarify', None)
                self.assertNotIn('private details', str(caught.exception))
                self.assertIn('Read the deck', str(caught.exception))
                service.presentations.return_value.batchUpdate.return_value.execute.assert_called_once()

    def test_model_output_validation_rejects_other_elements_and_structural_changes(self):
        targets = {'mvp_title_1': {'paragraphs': ['Title'], 'max_characters': [100]}}
        for replacements in ([{'element_id': 'mvp_title_2', 'paragraphs': ['Oops']}],
                             [{'element_id': 'mvp_title_1', 'paragraphs': ['One', 'Two']}],
                             [{'element_id': 'mvp_title_1', 'paragraphs': ['Line\nbreak']}],
                             [{'element_id': 'mvp_title_1', 'paragraphs': ['x' * 101]}],
                             [{'element_id': 'mvp_title_1', 'paragraphs': ['\ue000']}],
                             [{'element_id': 'mvp_title_1', 'paragraphs': ['Title']}] * 2):
            with self.assertRaises(ValueError):
                editing.validate_edit({'status': 'ok', 'replacements': replacements}, targets)

    def test_mistral_receives_current_text_source_and_retries_bad_output_once(self):
        fake = MagicMock()
        fake.__enter__.return_value = fake
        def response(content):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
        fake.chat.complete.side_effect = [response('bad'), response(json.dumps({'status': 'ok', 'replacements': []}))]
        with patch.dict(os.environ, {'MISTRAL_API_KEY': 'test'}), patch.object(editing, 'Mistral', return_value=fake):
            self.assertEqual(editing.propose_edit({'text': 'Manual wording'}, {}, 'Keep budget', 'Budget €5,000'), [])
        brief = json.loads(fake.chat.complete.call_args.kwargs['messages'][1]['content'])
        self.assertEqual(brief['slide']['text'], 'Manual wording')
        self.assertEqual(brief['source_content'], 'Budget €5,000')
        self.assertEqual(brief['instructions'], 'Keep budget')
        self.assertEqual(fake.chat.complete.call_count, 2)

    def test_authentication_is_required_for_both_tools(self):
        with patch.object(server, 'get_access_token', return_value=None), patch.object(editing, 'get_deck') as read, patch.object(editing, 'edit_deck_slide') as edit:
            for call in (server.get_presentation('deck1'), server.edit_slide('deck1', 'slide1', 'rev1', 'Clarify')):
                with self.assertRaises(ToolError):
                    asyncio.run(call)
            read.assert_not_called()
            edit.assert_not_called()

    def test_access_denial_is_actionable_and_hides_upstream_details(self):
        for status in (403, 404):
            service = self.service()
            service.presentations.return_value.get.return_value.execute.side_effect = HttpError(
                SimpleNamespace(status=status, reason='Forbidden'), b'private details')
            with patch.object(editing, 'build', return_value=service):
                with self.assertRaisesRegex(editing.EditError, 'connected Google account') as caught:
                    editing.get_deck('alice', 'deck1')
                self.assertNotIn('private details', str(caught.exception))

    def test_model_declines_unsupported_and_stops_after_two_invalid_responses(self):
        for content, expected_calls, message in (
            (json.dumps({'status': 'unsupported', 'reason': 'Cannot add images.', 'replacements': []}), 1, 'Cannot add images'),
            ('bad', 2, 'invalid edit twice'),
        ):
            fake = MagicMock()
            fake.__enter__.return_value = fake
            fake.chat.complete.return_value = SimpleNamespace(choices=[
                SimpleNamespace(message=SimpleNamespace(content=content))])
            service = self.service()
            with patch.dict(os.environ, {'MISTRAL_API_KEY': 'test'}), patch.object(editing, 'Mistral', return_value=fake), patch.object(editing, 'build', return_value=service):
                with self.assertRaisesRegex(editing.EditError, message):
                    editing.edit_deck_slide('alice', 'deck1', 'mvp_slide_1', 'rev1', 'Add image', None)
                self.assertEqual(fake.chat.complete.call_count, expected_calls)
                service.presentations.return_value.batchUpdate.assert_not_called()
