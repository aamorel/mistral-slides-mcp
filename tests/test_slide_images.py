"""Image placement preserves slide identity and remains compatible with iteration."""
import asyncio
import copy
from io import BytesIO
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image
from googleapiclient.errors import HttpError
from mcp.server.mcpserver.exceptions import ToolError

from mcp_slides import attachments, backgrounds, editing, insertion, layouts, preferences, server, slide_images, styling
from test_editing import box

URL = 'https://' + attachments.DEFAULT_HOST + '/image?sig=PRIVATE_SIGNATURE'
PALETTE = preferences.DEFAULT_STYLE.model_copy(update={'gradient': False}).palette()


def page(kind='bullets', lines=None):
    slide = {'type': kind, 'title': 'Evidence', 'message': 'A clear finding.', 'bullets': lines or ['One fact', 'Another fact']}
    elements = []
    for role, text, (x, y, w, h), size, _ in layouts.content_boxes(slide):
        element = box(f'mvp_{role}_1', text.split('\n'))
        element['size'] = {'width': {'magnitude': w, 'unit': 'PT'}, 'height': {'magnitude': h, 'unit': 'PT'}}
        element['transform'] = {'scaleX': 1, 'scaleY': 1, 'translateX': x, 'translateY': y, 'unit': 'PT'}
        for entry in element['shape']['text']['textElements']:
            if 'paragraphMarker' in entry:
                entry['paragraphMarker']['style'] = {'lineSpacing': 110, 'spaceAbove': {'magnitude': 0, 'unit': 'PT'}, 'spaceBelow': {'magnitude': 8, 'unit': 'PT'}}
            if 'textRun' in entry:
                entry['textRun']['style'].update(fontFamily='Arial', fontSize={'magnitude': size, 'unit': 'PT'},
                    foregroundColor={'opaqueColor': {'rgbColor': styling.rgb(PALETTE[layouts.color_role(element['objectId'])])}})
        elements.append(element)
    return {'objectId': 'mvp_slide_1', 'pageElements': elements,
            'pageProperties': {'pageBackgroundFill': {'solidFill': {'color': {'rgbColor': styling.rgb('FFFFFF')}}}}}


def deck(content):
    return {'title': 'Demo', 'revisionId': 'rev1', 'slides': [content],
            'pageSize': {'width': {'magnitude': 720, 'unit': 'PT'}, 'height': {'magnitude': 405, 'unit': 'PT'}}}


def apply_image_batch(content, batch):
    result = copy.deepcopy(content)
    for request in batch:
        if 'updatePageElementTransform' in request:
            op = request['updatePageElementTransform']
            next(e for e in result['pageElements'] if e['objectId'] == op['objectId'])['transform'] = op['transform']
        elif 'deleteObject' in request:
            result['pageElements'] = [e for e in result['pageElements'] if e['objectId'] != request['deleteObject']['objectId']]
        elif 'createImage' in request:
            op = request['createImage']
            result['pageElements'].append({'objectId': op['objectId'], 'image': {'sourceUrl': op['url']},
                                           **op['elementProperties']})
        elif 'updatePageElementAltText' in request:
            op = request['updatePageElementAltText']
            next(e for e in result['pageElements'] if e['objectId'] == op['objectId']).update(title=op['title'], description=op['description'])
    return result


class SlideImageTests(unittest.IsolatedAsyncioTestCase):
    def service(self, raw):
        service = MagicMock()
        service.presentations.return_value.get.return_value.execute.return_value = copy.deepcopy(raw)
        service.presentations.return_value.batchUpdate.return_value.execute.return_value = {'writeControl': {'requiredRevisionId': 'rev2'}}
        return service

    async def run_image(self, raw=None, replace=False, failure=None):
        service = self.service(raw or deck(page()))
        if failure:
            service.presentations.return_value.batchUpdate.return_value.execute.side_effect = failure
        with patch.object(editing, 'build', return_value=service), patch.object(attachments, 'retrieve',
                new_callable=AsyncMock, return_value=(b'normalized', (317, 193))) as retrieve, patch.object(
                backgrounds, 'publish_image', return_value=('temporary-token', 'https://our-app/assets/token.png')) as publish, patch.object(backgrounds, 'remove_image') as remove:
            result = await slide_images.set_image('creds', 'alice', 'deck1', 'mvp_slide_1', 'rev1', URL, replace)
        return result, service, retrieve, publish, remove

    async def test_add_preserves_text_and_batches_transform_with_image(self):
        for kind in ('bullets', 'key_message'):
            original = page(kind)
            result, service, retrieve, publish, remove = await self.run_image(deck(original))
            self.assertEqual(result['status'], 'added')
            self.assertEqual(result['revision_id'], 'rev2')
            self.assertEqual(result['position'], 1)
            body = service.presentations.return_value.batchUpdate.call_args.kwargs['body']
            self.assertEqual(body['writeControl'], {'requiredRevisionId': 'rev1'})
            self.assertEqual([next(iter(r)) for r in body['requests']],
                ['updatePageElementTransform', 'createImage', 'updatePageElementAltText'])
            self.assertNotIn('PRIVATE_SIGNATURE', str(body))
            after = apply_image_batch(original, body['requests'])
            self.assertTrue(slide_images.capability(after)['has_image'])
            self.assertTrue(slide_images.capability(after)['supported'])
            for before, updated in zip(original['pageElements'], after['pageElements']):
                self.assertEqual(before['shape'], updated['shape'])
                self.assertEqual(before['objectId'], updated['objectId'])
            retrieve.assert_awaited_once_with(URL)
            publish.assert_called_once_with('alice', b'normalized')
            remove.assert_called_once_with('temporary-token')
            service.presentations.return_value.batchUpdate.return_value.execute.assert_called_once_with(num_retries=0)

    async def test_explicit_replacement_keeps_text_and_one_slot(self):
        original = page()
        populated = apply_image_batch(original, slide_images.requests(original, slide_images.inspect_page(original), 'https://our-app/old', (200, 800)))
        result, service, *_ = await self.run_image(deck(populated), replace=True)
        batch = service.presentations.return_value.batchUpdate.call_args.kwargs['body']['requests']
        self.assertEqual([next(iter(r)) for r in batch], ['deleteObject', 'createImage', 'updatePageElementAltText'])
        after = apply_image_batch(populated, batch)
        self.assertEqual(sum('image' in e for e in after['pageElements']), 1)
        self.assertEqual(after['pageElements'][:2], populated['pageElements'][:2])
        self.assertEqual(result['status'], 'replaced')
        for raw, replace in ((deck(populated), False), (deck(original), True)):
            with self.assertRaises(editing.EditError):
                await self.run_image(raw, replace=replace)

    async def test_rejects_stale_custom_dense_or_resized_before_download(self):
        altered = page()
        altered['pageElements'][1]['transform']['translateX'] += 5
        custom = page()
        custom['pageElements'].append({'objectId': 'custom', 'image': {}})
        raw_cases = [deck(altered), deck(custom), deck(page(lines=['Point'] * 4)),
                     {**deck(page()), 'revisionId': 'stale'}, {**deck(page()), 'pageSize': {}}]
        for raw in raw_cases:
            with patch.object(editing, 'build', return_value=self.service(raw)), patch.object(attachments, 'retrieve', new_callable=AsyncMock) as retrieve:
                with self.assertRaises(editing.EditError):
                    await slide_images.set_image('creds', 'alice', 'deck1', 'mvp_slide_1', 'rev1', URL, False)
                retrieve.assert_not_awaited()

    async def test_failed_download_never_publishes_or_changes_deck(self):
        service = self.service(deck(page()))
        with patch.object(editing, 'build', return_value=service), patch.object(attachments, 'retrieve',
                side_effect=attachments.AttachmentError('Attach it again.')), patch.object(backgrounds, 'publish_image') as publish:
            with self.assertRaises(attachments.AttachmentError):
                await slide_images.set_image('creds', 'alice', 'deck1', 'mvp_slide_1', 'rev1', URL, False)
        publish.assert_not_called()
        service.presentations.return_value.batchUpdate.assert_not_called()

    async def test_uncertain_write_cleans_asset_and_never_replays(self):
        for failure in (TimeoutError('PRIVATE_SIGNATURE'), HttpError(SimpleNamespace(status=409, reason='Conflict'), b'PRIVATE_SIGNATURE')):
            service = self.service(deck(page()))
            service.presentations.return_value.batchUpdate.return_value.execute.side_effect = failure
            with patch.object(editing, 'build', return_value=service), patch.object(attachments, 'retrieve', return_value=(b'png', (100, 100))), patch.object(
                    backgrounds, 'publish_image', return_value=('token', 'https://our-app/image')), patch.object(backgrounds, 'remove_image') as remove:
                with self.assertRaises(editing.EditError) as error:
                    await slide_images.set_image('creds', 'alice', 'deck1', 'mvp_slide_1', 'rev1', URL, False)
            self.assertNotIn('PRIVATE_SIGNATURE', str(error.exception))
            remove.assert_called_once_with('token')
            service.presentations.return_value.batchUpdate.return_value.execute.assert_called_once_with(num_retries=0)

    def test_contain_landscape_portrait_and_square(self):
        original = page()
        for dimensions in ((1600, 400), (200, 800), (500, 500)):
            batch = slide_images.requests(original, slide_images.inspect_page(original), 'url', dimensions)
            image = next(r['createImage']['elementProperties'] for r in batch if 'createImage' in r)
            x, y, w, h = slide_images.geometry(image)
            fx, fy, fw, fh = slide_images.FRAME
            self.assertAlmostEqual(w/h, dimensions[0]/dimensions[1])
            self.assertAlmostEqual(x+w/2, fx+fw/2)
            self.assertAlmostEqual(y+h/2, fy+fh/2)
            self.assertLessEqual(w, fw)
            self.assertLessEqual(h, fh)

    def test_dense_wide_text_and_unsupported_layouts_are_rejected(self):
        self.assertFalse(slide_images.text_fits('message', ['W' * 90]))
        self.assertTrue(slide_images.text_fits('message', ['Use evidence to guide the next decision.']))
        for key in ('message', 'body'):
            self.assertFalse(slide_images.text_fits(key, ['Text'] * 4))
        unsupported = page()
        unsupported['pageElements'][1]['objectId'] = 'mvp_steps_1'
        self.assertFalse(slide_images.capability(unsupported)['supported'])
        unsupported = page()
        unsupported['objectId'] = 'mvp_slide_0'
        self.assertFalse(slide_images.capability(unsupported)['supported'])

    def test_emu_geometry_is_accepted_without_changing_units_elsewhere(self):
        original = page()
        for element in original['pageElements']:
            for axis in ('width', 'height'):
                element['size'][axis]['magnitude'] *= 12700
                element['size'][axis]['unit'] = 'EMU'
            for axis in ('translateX', 'translateY'):
                element['transform'][axis] *= 12700
            element['transform']['unit'] = 'EMU'
        self.assertTrue(slide_images.capability(original)['supported'])
        populated = apply_image_batch(original, slide_images.requests(original, slide_images.inspect_page(original), 'url', (100, 100)))
        self.assertTrue(slide_images.capability(populated)['supported'])

    async def test_read_style_edit_and_insertion_palette_preserve_image(self):
        original = page()
        populated = apply_image_batch(original, slide_images.requests(original, slide_images.inspect_page(original), 'url', (200, 800)))
        service = self.service(deck(populated))
        with patch.object(editing, 'build', return_value=service):
            read = editing.get_deck('creds', 'deck1')
            self.assertTrue(read['slides'][0]['image_placement']['supported'])
            self.assertTrue(read['slides'][0]['style']['supported'])
            self.assertEqual(insertion.slide_palette(populated), PALETTE)
            result = styling.apply_style('creds', 'deck1', 'rev1', preferences.StyleChanges(font_family='Georgia'))
            self.assertEqual(result['applied_slide_ids'], ['mvp_slide_1'])
            for request in service.presentations.return_value.batchUpdate.call_args.kwargs['body']['requests']:
                self.assertNotIn('mvp_attachment_1', str(request))
            with patch.object(editing, 'propose_edit', return_value=[]) as propose:
                editing.edit_deck_slide('creds', 'deck1', 'mvp_slide_1', 'rev1', 'Shorten', None)
            target = propose.call_args.args[1]['mvp_body_1']
            self.assertEqual(target['max_characters'], [55, 55])
            self.assertEqual(target['max_total_characters'], 150)
            with patch.object(editing, 'propose_edit', return_value=[{'element_id': 'mvp_body_1', 'paragraphs': ['x'*56, 'Fact']}]):
                with self.assertRaises(editing.EditError):
                    editing.edit_deck_slide('creds', 'deck1', 'mvp_slide_1', 'rev1', 'Expand', None)

    async def test_tool_requires_auth_and_maps_attachment_error_safely(self):
        with patch.object(server, 'get_access_token', return_value=None), patch.object(slide_images, 'set_image') as set_image:
            with self.assertRaises(ToolError):
                await server.set_slide_image('deck1', 'mvp_slide_1', 'rev1', URL)
            set_image.assert_not_called()
        with patch.object(server, 'connected_credentials', return_value='creds'), patch.object(server, 'connection_subject', return_value='alice'), patch.object(
                slide_images, 'set_image', side_effect=attachments.AttachmentError('Attach it again.')):
            with self.assertRaisesRegex(ToolError, 'Attach it again'):
                await server.set_slide_image('deck1', 'mvp_slide_1', 'rev1', URL)


class NormalizationTests(unittest.TestCase):
    def test_alpha_orientation_and_metadata(self):
        source = Image.new('RGBA', (17, 9), (10, 20, 30, 0))
        source.putpixel((2, 3), (255, 0, 0, 255))
        exif = Image.Exif()
        exif[274] = 6
        exif[315] = 'Private author'
        data = BytesIO()
        source.save(data, format='PNG', exif=exif)
        normalized, size = attachments.normalize(data.getvalue())
        self.assertEqual(size, (9, 17))
        with Image.open(BytesIO(normalized)) as image:
            self.assertEqual(image.mode, 'RGBA')
            self.assertEqual(image.getpixel((0, 0))[3], 0)
            self.assertFalse(image.getexif())
        self.assertNotIn(b'Private author', normalized)

    def test_invalid_oversized_and_animated_images(self):
        for data in (b'not-image', b'x' * (attachments.MAX_BYTES+1)):
            with self.assertRaises(attachments.AttachmentError):
                attachments.normalize(data)
        data = BytesIO()
        Image.new('RGB', (10, 10), 'red').save(data, format='PNG', save_all=True,
                                            append_images=[Image.new('RGB', (10, 10), 'blue')])
        with self.assertRaises(attachments.AttachmentError):
            attachments.normalize(data.getvalue())
