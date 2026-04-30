import re

from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    determine_ext,
    int_or_none,
    parse_duration,
    str_or_none,
    traverse_obj,
    url_or_none,
    urljoin,
)


class ExampleSiteIE(InfoExtractor):
    IE_NAME = 'examplesite'
    IE_DESC = 'ExampleSite - 视频网站'
    
    _VALID_URL = r'''(?x)
        https?://(?:www\.)?examplesite\.com/
        (?:
            video/(?P<id>[^/?#&]+)|
            watch/(?P<id_watch>[^/?#&]+)
        )
    '''
    
    _TESTS = [{
        'url': 'https://www.examplesite.com/video/abc123',
        'info_dict': {
            'id': 'abc123',
            'ext': 'mp4',
            'title': '示例视频标题',
            'description': '示例视频描述',
            'uploader': '示例作者',
            'uploader_id': 'author123',
            'thumbnail': r're:^https?://.*\.jpg$',
            'duration': int,
        },
        'params': {'skip_download': 'm3u8'},
    }]
    
    _API_TOKEN = 'your-fixed-token-here'  
    _API_BASE_URL = 'https://api.examplesite.com'
    
    def _get_api_headers(self):
        return {
            'Authorization': f'Bearer {self._API_TOKEN}',
            'Referer': 'https://www.examplesite.com/',
        }
    
    def _real_extract(self, url):
        video_id = self._match_valid_url(url).group('id') or self._match_valid_url(url).group('id_watch')
        
        webpage = self._download_webpage(url, video_id)
        
        next_data = self._search_nextjs_data(webpage, video_id)
        
        page_props = traverse_obj(next_data, ('props', 'pageProps'))
        
        video_info = traverse_obj(page_props, ('video', 'data')) or page_props
        
        video_id = str_or_none(video_info.get('id') or video_info.get('videoId') or video_id)
        title = video_info.get('title') or self._og_search_title(webpage)
        description = video_info.get('description') or self._og_search_description(webpage)
        
        media_api_url = video_info.get('mediaUrl') or f'{self._API_BASE_URL}/media/{video_id}'
        
        media_data = self._download_json(
            media_api_url, video_id,
            headers=self._get_api_headers(),
            note='Downloading media metadata'
        )
        
        formats, subtitles = self._extract_formats(media_data, video_id)
        
        self._sort_formats(formats)
        
        return {
            'id': video_id,
            'title': title,
            'description': description,
            'thumbnail': video_info.get('thumbnail') or self._og_search_thumbnail(webpage),
            'uploader': traverse_obj(video_info, ('author', 'name')) or video_info.get('uploader'),
            'uploader_id': traverse_obj(video_info, ('author', 'id')) or video_info.get('uploaderId'),
            'duration': int_or_none(video_info.get('duration')) or parse_duration(video_info.get('durationText')),
            'formats': formats,
            'subtitles': subtitles,
        }
    
    def _extract_formats(self, media_data, video_id):
        formats = []
        subtitles = {}
        
        streams = traverse_obj(media_data, ('streams', ..., {dict})) or \
                  traverse_obj(media_data, ('data', 'streams', ..., {dict})) or \
                  [media_data]
        
        for stream in streams:
            stream_url = url_or_none(stream.get('url') or stream.get('playUrl') or stream.get('src'))
            if not stream_url:
                continue
            
            stream_type = stream.get('type') or stream.get('streamType') or ''
            ext = determine_ext(stream_url)
            
            is_audio_only = False
            codec_info = stream.get('codecs') or ''
            if 'avc1' not in codec_info and 'h264' not in codec_info and 'h265' not in codec_info:
                if 'mp4a' in codec_info or 'aac' in codec_info:
                    is_audio_only = True
            
            if stream.get('height') == 0 or stream.get('width') == 0:
                is_audio_only = True
            
            if is_audio_only:
                continue
            
            if ext == 'm3u8' or 'm3u8' in stream_url:
                fmts, subs = self._extract_m3u8_formats_and_subtitles(
                    stream_url, video_id, 'mp4',
                    m3u8_id=stream.get('quality') or 'hls',
                    fatal=False
                )
                
                for fmt in fmts:
                    if fmt.get('vcodec') == 'none':
                        continue
                    fmt.update({
                        'height': fmt.get('height') or int_or_none(stream.get('height')),
                        'width': fmt.get('width') or int_or_none(stream.get('width')),
                    })
                    formats.append(fmt)
                
                subtitles = self._merge_subtitles(subtitles, subs)
            
            elif ext == 'mpd' or 'mpd' in stream_url:
                fmts, subs = self._extract_mpd_formats_and_subtitles(
                    stream_url, video_id,
                    mpd_id=stream.get('quality') or 'dash',
                    fatal=False
                )
                
                for fmt in fmts:
                    if fmt.get('vcodec') == 'none':
                        continue
                    formats.append(fmt)
                
                subtitles = self._merge_subtitles(subtitles, subs)
            
            else:
                format_id = stream.get('quality') or stream.get('label')
                if format_id:
                    format_id = str(format_id).lower().replace(' ', '-')
                
                format_info = {
                    'url': stream_url,
                    'format_id': format_id,
                    'width': int_or_none(stream.get('width')),
                    'height': int_or_none(stream.get('height')),
                    'tbr': int_or_none(stream.get('bitrate')),
                    'vcodec': stream.get('videoCodec') or stream.get('vcodec'),
                    'acodec': stream.get('audioCodec') or stream.get('acodec'),
                }
                formats.append(format_info)
        
        return formats, subtitles


class ExampleSiteUserIE(InfoExtractor):
    IE_NAME = 'examplesite:user'
    IE_DESC = 'ExampleSite - 用户/作者主页'
    
    _VALID_URL = r'''(?x)
        https?://(?:www\.)?examplesite\.com/
        (?:
            user/(?P<user_id>[^/?#&]+)|
            @(?P<username>[^/?#&]+)|
            creator/(?P<creator_id>[^/?#&]+)
        )
    '''
    
    _TESTS = [{
        'url': 'https://www.examplesite.com/user/creator123',
        'info_dict': {
            'id': 'creator123',
            'title': '示例作者的视频列表',
            'description': '示例作者的所有视频',
        },
        'playlist_mincount': 1,
    }]
    
    def _real_extract(self, url):
        mobj = self._match_valid_url(url)
        user_id = mobj.group('user_id') or mobj.group('username') or mobj.group('creator_id')
        
        webpage = self._download_webpage(url, user_id)
        
        next_data = self._search_nextjs_data(webpage, user_id, fatal=False)
        
        page_props = traverse_obj(next_data, ('props', 'pageProps')) or {}
        
        entries = []
        
        videos = traverse_obj(page_props, ('videos', 'items', ..., {dict})) or \
                traverse_obj(page_props, ('user', 'videos', ..., {dict})) or \
                traverse_obj(page_props, ('profile', 'videos', ..., {dict}))
        
        if not videos:
            videos = self._extract_videos_from_page(webpage, user_id, page_props)
        
        for video in videos:
            video_url = self._get_video_url(video)
            if video_url:
                entries.append(self.url_result(video_url, ExampleSiteIE))
        
        playlist_title = page_props.get('title') or \
                         traverse_obj(page_props, ('user', 'name')) or \
                         traverse_obj(page_props, ('profile', 'name')) or \
                         f'{user_id} 的视频'
        
        return self.playlist_result(
            entries,
            playlist_id=user_id,
            playlist_title=playlist_title,
            playlist_description=traverse_obj(page_props, ('user', 'bio')) or page_props.get('description')
        )
    
    def _extract_videos_from_page(self, webpage, user_id, page_props):
        videos = []
        
        initial_state = traverse_obj(page_props, ('initialState', {dict}))
        if initial_state:
            videos = traverse_obj(initial_state, ('videos', 'items', ..., {dict})) or \
                    traverse_obj(initial_state, ('user', 'videos', 'items', ..., {dict}))
        
        if not videos:
            for mobj in re.finditer(
                    r'<a[^>]+href=["\'](/video/[^"\'>]+)["\'>]',
                    webpage):
                link = mobj.group(1)
                videos.append({'id': link.split('/')[-1]})
        
        return videos
    
    def _get_video_url(self, video):
        video_id = str_or_none(video.get('id') or video.get('videoId'))
        if video_id:
            return f'https://www.examplesite.com/video/{video_id}'
        
        video_url = url_or_none(video.get('url'))
        if video_url:
            if video_url.startswith('/'):
                video_url = urljoin('https://www.examplesite.com/', video_url)
            return video_url
        
        return None
