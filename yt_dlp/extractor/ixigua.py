import base64
import json

from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    get_element_by_id,
    int_or_none,
    js_to_json,
    str_or_none,
    try_call,
    url_or_none,
)
from ..utils.traversal import traverse_obj


class IxiguaBaseIE(InfoExtractor):
    _IXIGUA_AID = 1768
    _IXIGUA_DOMAIN = 'www.ixigua.com'

    def _real_initialize(self):
        if self._get_cookies(f'https://{self._IXIGUA_DOMAIN}').get('ttwid'):
            return

        urlh = self._request_webpage(
            'https://ttwid.bytedance.com/ttwid/union/register/', None,
            'Fetching ttwid', 'Unable to fetch ttwid', headers={
                'Content-Type': 'application/json',
            }, data=json.dumps({
                'aid': self._IXIGUA_AID,
                'needFid': False,
                'region': 'cn',
                'service': self._IXIGUA_DOMAIN,
                'union': True,
            }).encode(),
        )

        if ttwid := try_call(lambda: self._get_cookies(urlh.url)['ttwid'].value):
            self._set_cookie('.ixigua.com', 'ttwid', ttwid)
            return

        self.report_warning('Failed to fetch ttwid cookie. You may need to provide cookies manually.')

    def _media_selector(self, json_data):
        for path, override in (
            (('video_list', ), {}),
            (('dynamic_video', 'dynamic_video_list'), {'acodec': 'none'}),
            (('dynamic_video', 'dynamic_audio_list'), {'vcodec': 'none', 'ext': 'm4a'}),
        ):
            for media in traverse_obj(json_data, (..., *path, lambda _, v: v['main_url'])):
                main_url = media.get('main_url')
                if not main_url:
                    continue
                try:
                    decoded_url = base64.b64decode(main_url).decode()
                except Exception:
                    decoded_url = main_url

                yield {
                    'url': decoded_url,
                    'width': int_or_none(media.get('vwidth')),
                    'height': int_or_none(media.get('vheight')),
                    'fps': int_or_none(media.get('fps')),
                    'vcodec': media.get('codec_type'),
                    'format_id': str_or_none(media.get('quality_type')),
                    'filesize': int_or_none(media.get('size')),
                    'ext': 'mp4',
                    **override,
                }

    def _extract_subtitles(self, video_info):
        subtitles = {}
        subtitle_info = traverse_obj(video_info, ('subtitle_info', 'subtitles'))
        if subtitle_info:
            for sub in subtitle_info:
                lang = sub.get('lang') or 'zh'
                sub_url = sub.get('url')
                if sub_url:
                    subtitles.setdefault(lang, []).append({
                        'url': sub_url,
                        'ext': 'srt' if '.srt' in sub_url else 'vtt',
                    })
        return subtitles

    def _get_json_data(self, webpage, video_id):
        js_data = get_element_by_id('SSR_HYDRATED_DATA', webpage)
        if not js_data:
            if self._cookies_passed:
                raise ExtractorError('Failed to get SSR_HYDRATED_DATA')
            raise ExtractorError('Cookies (not necessarily logged in) are needed', expected=True)

        return self._parse_json(
            js_data.replace('window._SSR_HYDRATED_DATA=', ''), video_id, transform_source=js_to_json)


class IxiguaIE(IxiguaBaseIE):
    IE_NAME = 'ixigua'
    IE_DESC = '西瓜视频 (ixigua.com)'
    _VALID_URL = r'https?://(?:\w+\.)?ixigua\.com/(?:video/)?(?P<id>\d+).+'
    _TESTS = [{
        'url': 'https://www.ixigua.com/6996881461559165471',
        'info_dict': {
            'id': '6996881461559165471',
            'ext': 'mp4',
            'title': '盲目涉水风险大，亲身示范高水位行车注意事项',
            'description': 'md5:8c82f46186299add4a1c455430740229',
            'tags': ['video_car'],
            'like_count': int,
            'dislike_count': int,
            'view_count': int,
            'uploader': '懂车帝原创',
            'uploader_id': '6480145787',
            'thumbnail': r're:^https?://.+\.(avif|webp)',
            'timestamp': 1629088414,
            'duration': 1030,
        },
    }]

    def _real_extract(self, url):
        video_id = self._match_id(url)
        webpage = self._download_webpage(url, video_id)
        json_data = self._get_json_data(webpage, video_id)['anyVideo']['gidInformation']['packerData']['video']

        formats = list(self._media_selector(json_data.get('videoResource')))
        self._sort_formats(formats)

        subtitles = self._extract_subtitles(json_data)

        thumbnail = traverse_obj(json_data, (
            'videoResource', 'poster_url',
            'poster_url',
        ), get_all=False)

        uploader_info = json_data.get('user_info') or {}

        return {
            'id': video_id,
            'title': json_data.get('title'),
            'description': json_data.get('video_abstract'),
            'formats': formats,
            'like_count': json_data.get('video_like_count'),
            'duration': int_or_none(json_data.get('duration')),
            'tags': [json_data.get('tag')],
            'uploader_id': traverse_obj(json_data, ('user_info', 'user_id')),
            'uploader': traverse_obj(json_data, ('user_info', 'name')),
            'view_count': json_data.get('video_watch_count'),
            'dislike_count': json_data.get('video_unlike_count'),
            'timestamp': int_or_none(json_data.get('video_publish_time')),
            'thumbnail': url_or_none(thumbnail),
            'subtitles': subtitles,
        }


class IxiguaShortIE(IxiguaBaseIE):
    IE_NAME = 'ixigua:short'
    IE_DESC = '西瓜视频短视频'
    _VALID_URL = r'https?://(?:\w+\.)?ixigua\.com/(?:short|s)/(?P<id>[a-zA-Z0-9]+)'
    _TESTS = [{
        'url': 'https://www.ixigua.com/short/abc123',
        'only_matching': True,
    }]

    @classmethod
    def suitable(cls, url):
        return False if IxiguaIE.suitable(url) else super().suitable(url)

    def _real_extract(self, url):
        video_id = self._match_id(url)
        webpage = self._download_webpage(url, video_id)

        video_id_long = self._search_regex(
            r'ixigua\.com/video/(\d+)', webpage, 'video id', default=None)

        if video_id_long:
            self.to_screen(f'Redirecting to long video ID: {video_id_long}')
            return self.url_result(
                f'https://www.ixigua.com/{video_id_long}',
                IxiguaIE.ie_key(), video_id_long)

        js_data = self._search_regex(
            r'window\._SSR_HYDRATED_DATA\s*=\s*([^;]+)',
            webpage, 'hydrated data', default=None)

        if not js_data:
            raise ExtractorError('Unable to extract video data from short URL')

        json_data = self._parse_json(js_data, video_id, transform_source=js_to_json)

        video_info = traverse_obj(json_data, (
            'anyVideo', 'gidInformation', 'packerData', 'video',
        ), get_all=False)

        if not video_info:
            raise ExtractorError('Unable to extract video information')

        video_resource = video_info.get('videoResource') or {}

        formats = list(self._media_selector(video_resource))
        self._sort_formats(formats)

        subtitles = self._extract_subtitles(video_info)

        uploader_info = video_info.get('user_info') or video_info.get('creator_info') or {}

        return {
            'id': video_id,
            'title': video_info.get('title') or video_id,
            'description': video_info.get('video_abstract') or video_info.get('description'),
            'formats': formats,
            'like_count': int_or_none(video_info.get('video_like_count')),
            'duration': int_or_none(video_info.get('duration')),
            'tags': [video_info.get('tag')] if video_info.get('tag') else [],
            'uploader_id': str_or_none(uploader_info.get('user_id')),
            'uploader': uploader_info.get('name') or uploader_info.get('nickname'),
            'view_count': int_or_none(video_info.get('video_watch_count')),
            'dislike_count': int_or_none(video_info.get('video_unlike_count')),
            'timestamp': int_or_none(video_info.get('video_publish_time')),
            'thumbnail': url_or_none(video_info.get('poster_url')),
            'subtitles': subtitles,
        }
