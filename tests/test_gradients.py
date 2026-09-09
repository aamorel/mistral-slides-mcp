"""Gradient lifecycle, readable styles, contrast, and solid-background opt-out."""
from io import BytesIO
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from mcp_slides import gradients, preferences, slides, styling, editing, insertion, backgrounds
from test_insertion import deck, NEW


URL = 'https://example.com/gradient.png'


def add_gradient(page):
    suffix = page['objectId'].rsplit('_', 1)[-1]
    requests = gradients.requests(suffix, '#FFFFFF', '#93B4E8', URL)
    page['pageElements'].append({'objectId': f'mvp_gradient_{suffix}',
        'image': {'sourceUrl': requests[0]['createImage']['url']}, 'description': requests[1]['updatePageElementAltText']['description']})
    return page


class GradientTests(unittest.TestCase):
    def test_defaults_legacy_settings_and_contrast_over_the_whole_gradient(self):
        legacy = dict(background='#FFFFFF', title_color='#244B63', body_color='#263238', font_family='Arial')
        self.assertTrue(preferences.StyleSettings(**legacy).gradient)
        self.assertEqual(preferences.DEFAULT_STYLE.gradient_color, '#93B4E8')
        # This foreground is valid on white, but fails on the tinted end.
        preferences.StyleSettings(**{**legacy, 'body_color': '#767676'}, gradient=False)
        with self.assertRaises(ValueError):
            preferences.StyleSettings(**{**legacy, 'body_color': '#767676'})
        self.assertEqual(preferences.StyleChanges(gradient=False).model_dump(exclude_unset=True), {'gradient': False})

    def test_pixels_match_validated_stops_and_fade_into_base(self):
        data = gradients.render('#FFFFFF', '#93B4E8')
        with Image.open(BytesIO(data)) as image:
            self.assertEqual(image.size, (1600, 900))
            self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
            self.assertEqual(image.getpixel((1599, 899)), (255, 255, 255))
            self.assertEqual(image.getpixel((1599, 0)), (225, 234, 249))
            allowed = {tuple(bytes.fromhex(c[1:])) for c in preferences.gradient_colors('#FFFFFF', '#93B4E8')}
            self.assertTrue(set(image.getdata()).issubset(allowed))

    def test_image_pool_reuses_asset_and_cleans_up_on_failure(self):
        with patch.object(backgrounds, 'publish_image', return_value=('token', URL)) as publish, patch.object(backgrounds, 'remove_image') as remove:
            with self.assertRaisesRegex(RuntimeError, 'failed'):
                with gradients.image_pool('alice') as prepare:
                    self.assertEqual(prepare('#FFFFFF', '#93B4E8'), URL)
                    self.assertEqual(prepare('#ffffff', '#93b4e8'), URL)
                    raise RuntimeError('failed')
            publish.assert_called_once()
            remove.assert_called_once_with('token')

    def test_default_deck_has_gradient_on_content_and_keeps_cover_image(self):
        service = MagicMock()
        service.presentations.return_value.create.return_value.execute.return_value = {'presentationId': 'deck1'}
        service.presentations.return_value.get.return_value.execute.return_value = {}
        prepare = MagicMock(return_value=URL)
        with patch.object(slides, 'build', return_value=service):
            slides.create_deck(None, {'title': 'Demo', 'slides': [NEW, NEW]},
                palette=preferences.DEFAULT_STYLE.palette(), cover_image_url='https://example.com/cover.png',
                publish_gradient=prepare)
        prepare.assert_called_once_with('#FFFFFF', '#93B4E8')
        requests = service.presentations.return_value.batchUpdate.call_args.kwargs['body']['requests']
        ids = [r['createImage']['objectId'] for r in requests if 'createImage' in r]
        self.assertEqual(ids, ['mvp_cover_image', 'mvp_gradient_1', 'mvp_gradient_2'])
        self.assertEqual(len([r for r in requests if 'updatePageElementsZOrder' in r]), 2)

    def test_read_and_insert_inherit_gradient_and_reject_replaced_images(self):
        raw = deck()
        page = add_gradient(raw['slides'][0])
        self.assertTrue(styling.style_capability(page)['gradient'])
        self.assertTrue(styling.inspect_slide(page)['supported'])
        self.assertTrue(insertion.slide_palette(page)['gradient'])
        service = MagicMock()
        service.presentations.return_value.get.return_value.execute.return_value = raw
        prepare = MagicMock(return_value=URL)
        with patch.object(editing, 'build', return_value=service), patch.object(insertion, 'propose_slide', return_value=NEW):
            result = insertion.add_deck_slide(None, 'deck1', 'rev1', 'Add risks', None, 'mvp_slide_1', MagicMock(), publish_gradient=prepare)
        self.assertEqual(result['style_source']['slide_id'], 'mvp_slide_1')
        prepare.assert_called_once_with('#FFFFFF', '#93B4E8')
        requests = service.presentations.return_value.batchUpdate.call_args.kwargs['body']['requests']
        self.assertTrue(any('createImage' in r for r in requests))
        page['pageElements'][-1]['image']['sourceUrl'] = 'https://example.com/manual.png'
        self.assertFalse(styling.inspect_slide(page)['supported'])

    def test_remove_recolor_and_font_only_preserve_content(self):
        for changes in ({'gradient': False}, {'gradient_color': '#D4A6CC'}, {'font_family': 'Verdana'}):
            raw = deck()
            raw['slides'] = [add_gradient(raw['slides'][0])]
            service = MagicMock()
            service.presentations.return_value.get.return_value.execute.return_value = raw
            prepare = MagicMock(return_value=URL)
            with patch.object(editing, 'build', return_value=service):
                result = styling.apply_style(None, 'deck1', 'rev1', preferences.StyleChanges(**changes), publish_gradient=prepare)
            self.assertEqual(result['status'], 'applied')
            requests = service.presentations.return_value.batchUpdate.call_args.kwargs['body']['requests']
            self.assertFalse(any('insertText' in r or 'deleteText' in r for r in requests))
            if 'gradient' in changes:
                self.assertEqual(requests, [{'deleteObject': {'objectId': 'mvp_gradient_1'}}])
                prepare.assert_not_called()
                raw['slides'][0]['pageElements'].pop()
                self.assertFalse(insertion.slide_palette(raw['slides'][0])['gradient'])
            elif 'gradient_color' in changes:
                prepare.assert_called_once_with('#FFFFFF', '#D4A6CC')
                self.assertEqual(requests[0], {'deleteObject': {'objectId': 'mvp_gradient_1'}})
            else:
                prepare.assert_not_called()
                self.assertTrue(all('updateTextStyle' in r for r in requests))

    def test_partial_color_change_checks_gradient_not_only_base(self):
        raw = deck()
        raw['slides'] = [add_gradient(raw['slides'][0])]
        service = MagicMock()
        service.presentations.return_value.get.return_value.execute.return_value = raw
        with patch.object(editing, 'build', return_value=service):
            result = styling.apply_style(None, 'deck1', 'rev1', preferences.StyleChanges(body_color='#767676'))
        self.assertEqual(result['status'], 'unsupported')
        service.presentations.return_value.batchUpdate.assert_not_called()
