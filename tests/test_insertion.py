"""Preservation, style selection, model boundaries and insertion concurrency."""
import asyncio
import copy
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError
from mcp.server.mcpserver.exceptions import ToolError
from mcp_slides.mvp import editing, insertion, preferences, server, slides, styling
from test_editing import box

NEW = {'type': 'bullets', 'title': 'Risks', 'bullets': ['Budget remains uncertain']}


def deck():
    pages = []
    palette = preferences.DEFAULT_STYLE.palette()
    for n in (1, 3):
        elements = [box(f'mvp_title_{n}', ['Manual title']), box(f'mvp_body_{n}', ['Manual content'])]
        for e, role in zip(elements, ('title', 'body')):
            e['shape']['text']['textElements'][1]['textRun']['style'].update(
                fontFamily='Georgia', foregroundColor={'opaqueColor': {'rgbColor': slides.rgb(palette[role])}})
        pages.append({'objectId': f'mvp_slide_{n}', 'pageElements': elements,
            'pageProperties': {'pageBackgroundFill': {'solidFill': {'color': {'rgbColor': slides.rgb('FFFFFF')}, 'alpha': 1}}}})
    return {'presentationId': 'deck1', 'title': 'Manual deck', 'revisionId': 'rev1', 'slides': pages,
        'pageSize': {'width': {'magnitude': 9144000, 'unit': 'EMU'}, 'height': {'magnitude': 5143500, 'unit': 'EMU'}}}


class InsertionTests(unittest.TestCase):
    def service(self, raw):
        service = MagicMock()
        service.presentations.return_value.get.return_value.execute.return_value = raw
        return service

    def test_append_and_insert_preserve_existing_objects_and_added_slide_is_editable(self):
        for anchor, index in [(None, 2), ('mvp_slide_1', 1)]:
            raw = deck()
            # Include an unrelated nested object with a conflicting numeric suffix.
            raw['layouts'] = [{'objectId': 'layout1', 'pageElements': [{'objectId': 'mvp_body_12'}]}]
            original = copy.deepcopy(raw)
            service = self.service(raw)
            fallback = MagicMock()
            with patch.object(editing, 'build', return_value=service), patch.object(insertion, 'propose_slide', return_value=NEW) as propose:
                result = insertion.add_deck_slide('alice', 'deck1', 'rev1', 'Add risks', 'Budget uncertain', anchor, fallback)
            self.assertEqual(raw, original)
            self.assertEqual(result['slide_id'], 'mvp_slide_13')
            self.assertEqual(result['position'], index + 1)
            self.assertEqual(result['total_slide_count'], 3)
            self.assertEqual(result['presentation_url'], 'https://docs.google.com/presentation/d/deck1/edit')
            self.assertEqual(result['style_source']['source'], 'existing_slide')
            fallback.assert_not_called()
            self.assertIn('Manual content', str(propose.call_args.args[0]))
            body = service.presentations.return_value.batchUpdate.call_args.kwargs['body']
            self.assertEqual(body['writeControl'], {'requiredRevisionId': 'rev1'})
            requests = body['requests']
            self.assertEqual(requests[0]['createSlide']['insertionIndex'], index)
            old_ids = set(insertion.object_ids(raw))
            for request in requests:
                self.assertNotIn('deleteObject', request)
                operation = next(iter(request.values()))
                self.assertNotIn(operation.get('objectId'), old_ids)
            self.assertTrue(all(r['updateTextStyle']['style']['fontFamily'] == 'Georgia' for r in requests if 'updateTextStyle' in r))
            page = {'objectId': result['slide_id'], 'pageElements': [
                box(r['insertText']['objectId'], r['insertText']['text'].split('\n')) for r in requests if 'insertText' in r]}
            self.assertTrue(all(editing.normalize_element(e)['editable'] for e in page['pageElements']))
            self.assertTrue(styling.inspect_slide(page)['supported'])
            # A subsequent normal text edit can target the newly inserted title.
            after = copy.deepcopy(raw)
            after['slides'].insert(index, page)
            after['revisionId'] = 'rev2'
            next_service = self.service(after)
            with patch.object(editing, 'build', return_value=next_service), patch.object(editing, 'propose_edit',
                    return_value=[{'element_id': 'mvp_title_13', 'paragraphs': ['Updated risks']}]):
                edited = editing.edit_deck_slide('alice', 'deck1', 'mvp_slide_13', 'rev2', 'Clarify', None)
            self.assertEqual(edited['status'], 'updated')
            self.assertEqual(edited['position'], index + 1)
            service.presentations.return_value.create.assert_not_called()
            service.presentations.return_value.batchUpdate.return_value.execute.assert_called_once_with(num_retries=0)

    def test_style_nearest_then_fallback_is_explicit(self):
        pages = deck()['slides']
        palette, source, warnings = insertion.choose_palette(pages, 1, MagicMock())
        self.assertEqual(source['slide_id'], 'mvp_slide_1')
        self.assertEqual(palette['font_family'], 'Georgia')
        self.assertEqual(warnings, [])
        pages[0]['pageElements'][0]['shape']['text']['textElements'][1]['textRun']['style']['fontFamily'] = 'Arial'
        self.assertEqual(insertion.choose_palette(pages, 1, MagicMock())[1]['slide_id'], 'mvp_slide_3')
        pages[1]['pageProperties'] = {}
        fallback = MagicMock(return_value=preferences.DEFAULT_STYLE.palette())
        palette, source, warnings = insertion.choose_palette(pages, 1, fallback)
        self.assertEqual(source['source'], 'saved_default')
        self.assertIn('may differ', warnings[0])
        fallback.assert_called_once()

    def test_stale_missing_anchor_wrong_size_fail_before_generation(self):
        for revision, anchor, width in [('old', None, 720), ('rev1', 'missing', 720), ('rev1', None, 900)]:
            raw = deck()
            raw['pageSize']['width'] = {'magnitude': width, 'unit': 'PT'}
            service = self.service(raw)
            with patch.object(editing, 'build', return_value=service), patch.object(insertion, 'propose_slide') as propose:
                with self.assertRaises(editing.EditError):
                    insertion.add_deck_slide('alice', 'deck1', revision, 'Add risks', None, anchor, MagicMock())
                propose.assert_not_called()
                service.presentations.return_value.batchUpdate.assert_not_called()

    def test_write_errors_never_retry_and_uncertainty_identifies_new_slide(self):
        for error in [HttpError(SimpleNamespace(status=400, reason='Bad'), b'private'), TimeoutError()]:
            service = self.service(deck())
            service.presentations.return_value.batchUpdate.return_value.execute.side_effect = error
            with patch.object(editing, 'build', return_value=service), patch.object(insertion, 'propose_slide', return_value=NEW):
                with self.assertRaises(editing.EditError) as caught:
                    insertion.add_deck_slide('alice', 'deck1', 'rev1', 'Add risks', None, None, MagicMock())
            self.assertIn('Read the deck', str(caught.exception))
            self.assertNotIn('private', str(caught.exception))
            if isinstance(error, TimeoutError):
                self.assertIn('mvp_slide_4', str(caught.exception))
            service.presentations.return_value.batchUpdate.return_value.execute.assert_called_once_with(num_retries=0)

    def test_invalid_or_unsupported_model_response_cannot_write(self):
        for output, calls in [({'status': 'unsupported', 'reason': 'Images unsupported'}, 1),
                              ({'status': 'ok', 'slide': {**NEW, 'image': 'url'}}, 2),
                              ({'status': 'ok', 'slide': {**NEW, 'bullets': ['x' * 141]}}, 2)]:
            fake = MagicMock()
            fake.__enter__.return_value = fake
            fake.chat.complete.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(output)))])
            service = self.service(deck())
            with patch.dict(os.environ, {'MISTRAL_API_KEY': 'test'}), patch.object(insertion, 'Mistral', return_value=fake), patch.object(editing, 'build', return_value=service):
                with self.assertRaises(editing.EditError):
                    insertion.add_deck_slide('alice', 'deck1', 'rev1', 'Add risks', None, None, MagicMock())
            self.assertEqual(fake.chat.complete.call_count, calls)
            service.presentations.return_value.batchUpdate.assert_not_called()

    def test_model_retries_and_receives_context_and_source_separately(self):
        fake = MagicMock()
        fake.__enter__.return_value = fake
        fake.chat.complete.side_effect = [SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=value))])
            for value in ['bad', json.dumps({'status': 'ok', 'slide': NEW})]]
        with patch.dict(os.environ, {'MISTRAL_API_KEY': 'test'}), patch.object(insertion, 'Mistral', return_value=fake):
            self.assertEqual(insertion.propose_slide({'title': 'Manual'}, 'Add risks', 'Budget uncertain'), NEW)
        brief = json.loads(fake.chat.complete.call_args.kwargs['messages'][1]['content'])
        self.assertEqual(brief['current_deck'], {'title': 'Manual'})
        self.assertEqual(brief['instructions'], 'Add risks')
        self.assertEqual(brief['source_content'], 'Budget uncertain')

    def test_auth_required_and_blank_input_rejected(self):
        with patch.object(server, 'get_access_token', return_value=None), patch.object(insertion, 'add_deck_slide') as add:
            for revision, instructions, source in [('rev1', 'Add risks', None), (' ', 'Add', None), ('rev1', ' ', None), ('rev1', 'Add', ' ')]:
                with self.assertRaises(ToolError):
                    asyncio.run(server.add_slide('deck1', revision, instructions, source))
            add.assert_not_called()
