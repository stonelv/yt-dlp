import concurrent.futures
import json
import math
import os
import random
import threading
import time

from .common import FileDownloader
from ..networking import Request
from ..networking.exceptions import (
    CertificateVerifyError,
    HTTPError,
    TransportError,
)
from ..utils import (
    ContentTooShortError,
    RetryManager,
    ThrottledDownload,
    int_or_none,
    parse_http_range,
    try_call,
)
from ..utils.networking import HTTPHeaderDict


class HttpFD(FileDownloader):
    def real_download(self, filename, info_dict):
        url = info_dict['url']
        request_data = info_dict.get('request_data', None)
        request_extensions = {}
        impersonate_target = self._get_impersonate_target(info_dict)
        if impersonate_target is not None:
            request_extensions['impersonate'] = impersonate_target

        class DownloadContext(dict):
            __getattr__ = dict.get
            __setattr__ = dict.__setitem__
            __delattr__ = dict.__delitem__

        ctx = DownloadContext()
        ctx.filename = filename
        ctx.tmpfilename = self.temp_name(filename)
        ctx.stream = None

        # Disable compression
        headers = HTTPHeaderDict({'Accept-Encoding': 'identity'}, info_dict.get('http_headers'))

        is_test = self.params.get('test', False)
        chunk_size = self._TEST_FILE_SIZE if is_test else (
            self.params.get('http_chunk_size')
            or info_dict.get('downloader_options', {}).get('http_chunk_size')
            or 0)

        concurrent_fragments = self.params.get('concurrent_fragment_downloads', 1)
        use_parallel_download = chunk_size > 0 and concurrent_fragments > 1

        ctx.open_mode = 'wb'
        ctx.resume_len = 0
        ctx.block_size = self.params.get('buffersize', 1024)
        ctx.start_time = time.time()

        # parse given Range
        req_start, req_end, _ = parse_http_range(headers.get('Range'))

        if self.params.get('continuedl', True):
            # Establish possible resume length
            if os.path.isfile(ctx.tmpfilename):
                ctx.resume_len = os.path.getsize(ctx.tmpfilename)

        ctx.is_resume = ctx.resume_len > 0

        class SucceedDownload(Exception):
            pass

        class RetryDownload(Exception):
            def __init__(self, source_error):
                self.source_error = source_error

        class NextFragment(Exception):
            pass

        def establish_connection():
            ctx.chunk_size = (random.randint(int(chunk_size * 0.95), chunk_size)
                              if not is_test and chunk_size else chunk_size)
            if ctx.resume_len > 0:
                range_start = ctx.resume_len
                if req_start is not None:
                    # offset the beginning of Range to be within request
                    range_start += req_start
                if ctx.is_resume:
                    self.report_resuming_byte(ctx.resume_len)
                ctx.open_mode = 'ab'
            elif req_start is not None:
                range_start = req_start
            elif ctx.chunk_size > 0:
                range_start = 0
            else:
                range_start = None
            ctx.is_resume = False

            if ctx.chunk_size:
                chunk_aware_end = range_start + ctx.chunk_size - 1
                # we're not allowed to download outside Range
                range_end = chunk_aware_end if req_end is None else min(chunk_aware_end, req_end)
            elif req_end is not None:
                # there's no need for chunked downloads, so download until the end of Range
                range_end = req_end
            else:
                range_end = None

            if try_call(lambda: range_start > range_end):
                ctx.resume_len = 0
                ctx.open_mode = 'wb'
                raise RetryDownload(Exception(f'Conflicting range. (start={range_start} > end={range_end})'))

            if try_call(lambda: range_end >= ctx.content_len):
                range_end = ctx.content_len - 1

            request = Request(url, request_data, headers, extensions=request_extensions)
            has_range = range_start is not None
            if has_range:
                request.headers['Range'] = f'bytes={int(range_start)}-{int_or_none(range_end) or ""}'
            # Establish connection
            try:
                ctx.data = self.ydl.urlopen(request)
                # When trying to resume, Content-Range HTTP header of response has to be checked
                # to match the value of requested Range HTTP header. This is due to a webservers
                # that don't support resuming and serve a whole file with no Content-Range
                # set in response despite of requested Range (see
                # https://github.com/ytdl-org/youtube-dl/issues/6057#issuecomment-126129799)
                if has_range:
                    content_range = ctx.data.headers.get('Content-Range')
                    content_range_start, content_range_end, content_len = parse_http_range(content_range)
                    # Content-Range is present and matches requested Range, resume is possible
                    if range_start == content_range_start and (
                            # Non-chunked download
                            not ctx.chunk_size
                            # Chunked download and requested piece or
                            # its part is promised to be served
                            or content_range_end == range_end
                            or content_len < range_end):
                        ctx.content_len = content_len
                        if content_len or req_end:
                            ctx.data_len = min(content_len or req_end, req_end or content_len) - (req_start or 0)
                        return
                    # Content-Range is either not present or invalid. Assuming remote webserver is
                    # trying to send the whole file, resume is not possible, so wiping the local file
                    # and performing entire redownload
                    elif range_start > 0:
                        self.report_unable_to_resume()
                    ctx.resume_len = 0
                    ctx.open_mode = 'wb'
                ctx.data_len = ctx.content_len = int_or_none(ctx.data.headers.get('Content-length', None))
            except HTTPError as err:
                if err.status == 416:
                    # Unable to resume (requested range not satisfiable)
                    try:
                        # Open the connection again without the range header
                        ctx.data = self.ydl.urlopen(
                            Request(url, request_data, headers))
                        content_length = ctx.data.headers['Content-Length']
                    except HTTPError as err:
                        if err.status < 500 or err.status >= 600:
                            raise
                    else:
                        # Examine the reported length
                        if (content_length is not None
                                and (ctx.resume_len - 100 < int(content_length) < ctx.resume_len + 100)):
                            # The file had already been fully downloaded.
                            # Explanation to the above condition: in issue #175 it was revealed that
                            # YouTube sometimes adds or removes a few bytes from the end of the file,
                            # changing the file size slightly and causing problems for some users. So
                            # I decided to implement a suggested change and consider the file
                            # completely downloaded if the file size differs less than 100 bytes from
                            # the one in the hard drive.
                            self.report_file_already_downloaded(ctx.filename)
                            self.try_rename(ctx.tmpfilename, ctx.filename)
                            self._hook_progress({
                                'filename': ctx.filename,
                                'status': 'finished',
                                'downloaded_bytes': ctx.resume_len,
                                'total_bytes': ctx.resume_len,
                            }, info_dict)
                            raise SucceedDownload
                        else:
                            # The length does not match, we start the download over
                            self.report_unable_to_resume()
                            ctx.resume_len = 0
                            ctx.open_mode = 'wb'
                            return
                elif err.status < 500 or err.status >= 600:
                    # Unexpected HTTP error
                    raise
                raise RetryDownload(err)
            except CertificateVerifyError:
                raise
            except TransportError as err:
                raise RetryDownload(err)

        def close_stream():
            if ctx.stream is not None:
                if ctx.tmpfilename != '-':
                    ctx.stream.close()
                ctx.stream = None

        def download():
            data_len = ctx.data.headers.get('Content-length')

            if ctx.data.headers.get('Content-encoding'):
                # Content-encoding is present, Content-length is not reliable anymore as we are
                # doing auto decompression. (See: https://github.com/yt-dlp/yt-dlp/pull/6176)
                data_len = None

            # Range HTTP header may be ignored/unsupported by a webserver
            # (e.g. extractor/scivee.py, extractor/bambuser.py).
            # However, for a test we still would like to download just a piece of a file.
            # To achieve this we limit data_len to _TEST_FILE_SIZE and manually control
            # block size when downloading a file.
            if is_test and (data_len is None or int(data_len) > self._TEST_FILE_SIZE):
                data_len = self._TEST_FILE_SIZE

            if data_len is not None:
                data_len = int(data_len) + ctx.resume_len
                min_data_len = self.params.get('min_filesize')
                max_data_len = self.params.get('max_filesize')
                if min_data_len is not None and data_len < min_data_len:
                    self.to_screen(
                        f'\r[download] File is smaller than min-filesize ({data_len} bytes < {min_data_len} bytes). Aborting.')
                    return False
                if max_data_len is not None and data_len > max_data_len:
                    self.to_screen(
                        f'\r[download] File is larger than max-filesize ({data_len} bytes > {max_data_len} bytes). Aborting.')
                    return False

            byte_counter = 0 + ctx.resume_len
            block_size = ctx.block_size
            start = time.time()

            # measure time over whole while-loop, so slow_down() and best_block_size() work together properly
            now = None  # needed for slow_down() in the first loop run
            before = start  # start measuring

            def retry(e):
                close_stream()
                if ctx.tmpfilename == '-':
                    ctx.resume_len = byte_counter
                else:
                    try:
                        ctx.resume_len = os.path.getsize(ctx.tmpfilename)
                    except FileNotFoundError:
                        ctx.resume_len = 0
                raise RetryDownload(e)

            while True:
                try:
                    # Download and write
                    data_block = ctx.data.read(block_size if not is_test else min(block_size, data_len - byte_counter))
                except TransportError as err:
                    retry(err)

                byte_counter += len(data_block)

                # exit loop when download is finished
                if len(data_block) == 0:
                    break

                # Open destination file just in time
                if ctx.stream is None:
                    try:
                        ctx.stream, ctx.tmpfilename = self.sanitize_open(
                            ctx.tmpfilename, ctx.open_mode)
                        assert ctx.stream is not None
                        ctx.filename = self.undo_temp_name(ctx.tmpfilename)
                        self.report_destination(ctx.filename)
                    except OSError as err:
                        self.report_error(f'unable to open for writing: {err}')
                        return False

                try:
                    ctx.stream.write(data_block)
                except OSError as err:
                    self.to_stderr('\n')
                    self.report_error(f'unable to write data: {err}')
                    return False

                # Apply rate limit
                self.slow_down(start, now, byte_counter - ctx.resume_len)

                # end measuring of one loop run
                now = time.time()
                after = now

                # Adjust block size
                if not self.params.get('noresizebuffer', False):
                    block_size = self.best_block_size(after - before, len(data_block))

                before = after

                # Progress message
                speed = self.calc_speed(start, now, byte_counter - ctx.resume_len)
                if ctx.data_len is None:
                    eta = None
                else:
                    eta = self.calc_eta(start, time.time(), ctx.data_len - ctx.resume_len, byte_counter - ctx.resume_len)

                self._hook_progress({
                    'status': 'downloading',
                    'downloaded_bytes': byte_counter,
                    'total_bytes': ctx.data_len,
                    'tmpfilename': ctx.tmpfilename,
                    'filename': ctx.filename,
                    'eta': eta,
                    'speed': speed,
                    'elapsed': now - ctx.start_time,
                    'ctx_id': info_dict.get('ctx_id'),
                }, info_dict)

                if data_len is not None and byte_counter == data_len:
                    break

                if speed and speed < (self.params.get('throttledratelimit') or 0):
                    # The speed must stay below the limit for 3 seconds
                    # This prevents raising error when the speed temporarily goes down
                    if ctx.throttle_start is None:
                        ctx.throttle_start = now
                    elif now - ctx.throttle_start > 3:
                        if ctx.stream is not None and ctx.tmpfilename != '-':
                            ctx.stream.close()
                        raise ThrottledDownload
                elif speed:
                    ctx.throttle_start = None

            if ctx.stream is None:
                self.to_stderr('\n')
                self.report_error('Did not get any data blocks')
                return False

            if not is_test and ctx.chunk_size and ctx.content_len is not None and byte_counter < ctx.content_len:
                ctx.resume_len = byte_counter
                raise NextFragment

            if ctx.tmpfilename != '-':
                ctx.stream.close()

            if data_len is not None and byte_counter != data_len:
                err = ContentTooShortError(byte_counter, int(data_len))
                retry(err)

            self.try_rename(ctx.tmpfilename, ctx.filename)

            # Update file modification time
            if self.params.get('updatetime'):
                info_dict['filetime'] = self.try_utime(ctx.filename, ctx.data.headers.get('last-modified', None))

            self._hook_progress({
                'downloaded_bytes': byte_counter,
                'total_bytes': byte_counter,
                'filename': ctx.filename,
                'status': 'finished',
                'elapsed': time.time() - ctx.start_time,
                'ctx_id': info_dict.get('ctx_id'),
            }, info_dict)

            return True

        if use_parallel_download:
            # Try parallel download first. If it fails (e.g., cannot determine file size),
            # fall back to sequential download
            parallel_result = self._parallel_download(
                url, request_data, headers, request_extensions,
                chunk_size, concurrent_fragments, ctx, info_dict, req_start, req_end
            )
            if parallel_result is not None:
                return parallel_result

        for retry in RetryManager(self.params.get('retries'), self.report_retry):
            try:
                establish_connection()
                return download()
            except RetryDownload as err:
                retry.error = err.source_error
                continue
            except NextFragment:
                retry.error = None
                retry.attempt -= 1
                continue
            except SucceedDownload:
                return True
            except:  # noqa: E722
                close_stream()
                raise
        return False

    def _parallel_download(self, url, request_data, headers, request_extensions,
                            chunk_size, concurrent_fragments, ctx, info_dict,
                            req_start=None, req_end=None):
        ytdl_filename = self.ytdl_filename(ctx.filename)
        continuedl = self.params.get('continuedl', True)
        is_test = self.params.get('test', False)

        def read_ytdl_file():
            if not os.path.isfile(ytdl_filename):
                return None
            try:
                with open(ytdl_filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return None

        def write_ytdl_file(data):
            try:
                with open(ytdl_filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f)
            except Exception:
                pass

        def get_file_size():
            # Try to get file size using Range request first (more reliable)
            try:
                request = Request(url, request_data, headers.copy(), extensions=request_extensions)
                request.headers['Range'] = 'bytes=0-0'
                with self.ydl.urlopen(request) as response:
                    content_range = response.headers.get('Content-Range')
                    if content_range:
                        _, _, content_len = parse_http_range(content_range)
                        return content_len
                    return int_or_none(response.headers.get('Content-Length'))
            except Exception:
                pass
            # Fall back to HEAD request
            try:
                request = Request(url, request_data, headers.copy(), extensions=request_extensions)
                request.method = 'HEAD'
                with self.ydl.urlopen(request) as response:
                    return int_or_none(response.headers.get('Content-Length'))
            except Exception:
                return None

        content_len = get_file_size()
        if content_len is None:
            self.to_screen('[download] Unable to determine file size for parallel download, falling back to sequential download')
            # Return None to indicate caller should fall back to sequential download
            return None

        if req_end is not None:
            content_len = min(content_len, req_end + 1)
        if req_start is not None:
            content_len = content_len - req_start

        total_chunks = math.ceil(content_len / chunk_size)

        self.to_screen(f'[download] Total fragments: {total_chunks} (concurrent: {concurrent_fragments})')

        ytdl_data = read_ytdl_file() if continuedl else None
        if ytdl_data is None:
            ytdl_data = {
                'downloader': {
                    'content_len': content_len,
                    'chunk_size': chunk_size,
                    'fragments': [{'downloaded': False, 'start': i * chunk_size, 'end': min((i + 1) * chunk_size, content_len)}
                                  for i in range(total_chunks)]
                }
            }
            write_ytdl_file(ytdl_data)

        fragments = ytdl_data['downloader'].get('fragments', [])

        existing_file_size = 0
        if os.path.isfile(ctx.tmpfilename):
            existing_file_size = os.path.getsize(ctx.tmpfilename)

        if existing_file_size > 0 and existing_file_size != content_len:
            self.report_warning('Existing file size mismatch, will re-download')
            self.try_remove(ctx.tmpfilename)
            for i, frag in enumerate(fragments):
                frag['downloaded'] = False
            write_ytdl_file(ytdl_data)
            existing_file_size = 0

        if existing_file_size == content_len:
            all_downloaded = all(f.get('downloaded', False) for f in fragments)
            if all_downloaded:
                self.report_file_already_downloaded(ctx.filename)
                self.try_rename(ctx.tmpfilename, ctx.filename)
                if os.path.isfile(ytdl_filename):
                    self.try_remove(ytdl_filename)
                self._hook_progress({
                    'filename': ctx.filename,
                    'status': 'finished',
                    'downloaded_bytes': content_len,
                    'total_bytes': content_len,
                }, info_dict)
                return True

        # Create sparse file to ensure we have enough space and can seek to any position
        if not os.path.isfile(ctx.tmpfilename):
            f, _ = self.sanitize_open(ctx.tmpfilename, 'wb')
            try:
                f.seek(content_len - 1)
                f.write(b'\0')
            finally:
                f.close()

        self.report_destination(ctx.filename)

        downloaded_bytes = sum(f['end'] - f['start'] for f in fragments if f.get('downloaded', False))
        progress_lock = threading.Lock()

        class SharedProgress:
            def __init__(self):
                self.start_time = time.time()
                self.downloaded = downloaded_bytes
                self.total = content_len
                self.speed = None
                self.eta = None

        shared_progress = SharedProgress()

        def update_progress(frag_idx, frag_downloaded, frag_total):
            with progress_lock:
                now = time.time()
                elapsed = now - shared_progress.start_time
                shared_progress.speed = self.calc_speed(shared_progress.start_time, now, shared_progress.downloaded)
                if shared_progress.speed:
                    remaining = shared_progress.total - shared_progress.downloaded
                    shared_progress.eta = int(remaining / shared_progress.speed) if shared_progress.speed else None

                self._hook_progress({
                    'status': 'downloading',
                    'downloaded_bytes': shared_progress.downloaded,
                    'total_bytes': shared_progress.total,
                    'tmpfilename': ctx.tmpfilename,
                    'filename': ctx.filename,
                    'eta': shared_progress.eta,
                    'speed': shared_progress.speed,
                    'elapsed': elapsed,
                    'ctx_id': info_dict.get('ctx_id'),
                    'fragment_index': frag_idx + 1,
                    'fragment_count': total_chunks,
                }, info_dict)

        def download_fragment(frag_idx):
            frag = fragments[frag_idx]
            if frag.get('downloaded', False):
                return True

            frag_start = frag['start']
            frag_end = frag['end'] - 1
            if req_start is not None:
                frag_start += req_start
                frag_end += req_start

            # TODO: Implement fragment-level resume by checking partial fragment file
            frag_resume_len = 0

            def error_callback(err, count, retries):
                self.report_retry(err, count, retries, frag_idx + 1)

            for retry in RetryManager(self.params.get('retries'), error_callback):
                try:
                    request = Request(url, request_data, headers.copy(), extensions=request_extensions)
                    request.headers['Range'] = f'bytes={frag_start + frag_resume_len}-{frag_end}'

                    with self.ydl.urlopen(request) as response:
                        content_range = response.headers.get('Content-Range')
                        if content_range:
                            cr_start, cr_end, cr_total = parse_http_range(content_range)
                            if cr_start != frag_start + frag_resume_len:
                                self.report_warning(f'Fragment {frag_idx + 1}: Range request not supported')
                                frag_resume_len = 0

                        data_len = response.headers.get('Content-Length')
                        if data_len:
                            data_len = int(data_len)

                        block_size = self.params.get('buffersize', 1024)
                        start = time.time()
                        now = None
                        before = start
                        byte_counter = frag_resume_len

                        file_offset = frag['start'] + frag_resume_len
                        f = open(ctx.tmpfilename, 'r+b')
                        try:
                            f.seek(file_offset)

                            while True:
                                try:
                                    read_size = block_size
                                    if is_test and data_len:
                                        read_size = min(read_size, data_len - byte_counter)
                                    data_block = response.read(read_size)
                                except TransportError as err:
                                    retry.error = err
                                    break

                                if not data_block:
                                    break

                                byte_counter += len(data_block)

                                try:
                                    f.write(data_block)
                                    f.flush()
                                except OSError as err:
                                    self.report_error(f'unable to write fragment {frag_idx + 1}: {err}')
                                    return False

                                with progress_lock:
                                    shared_progress.downloaded += len(data_block)

                                # Apply rate limit
                                self.slow_down(start, now, byte_counter - frag_resume_len)

                                now = time.time()
                                after = now

                                # Adjust block size
                                if not self.params.get('noresizebuffer', False):
                                    block_size = self.best_block_size(after - before, len(data_block))

                                before = after

                                update_progress(frag_idx, byte_counter, frag['end'] - frag['start'])

                            frag_actual_size = byte_counter
                            frag_expected_size = frag['end'] - frag['start']

                            if frag_actual_size < frag_expected_size and not is_test:
                                raise ContentTooShortError(frag_actual_size, frag_expected_size)

                            with progress_lock:
                                fragments[frag_idx]['downloaded'] = True
                                ytdl_data['downloader']['fragments'] = fragments
                                write_ytdl_file(ytdl_data)

                            return True
                        finally:
                            f.close()

                except HTTPError as err:
                    if err.status < 500 or err.status >= 600:
                        raise
                    retry.error = err
                    continue
                except TransportError as err:
                    retry.error = err
                    continue
                except ContentTooShortError as err:
                    retry.error = err
                    continue
                except CertificateVerifyError:
                    raise

            return False

        pending_fragments = [i for i, f in enumerate(fragments) if not f.get('downloaded', False)]

        if not pending_fragments:
            self._finish_parallel_download(ctx, info_dict, content_len, ytdl_filename)
            return True

        update_progress(0, 0, 0)

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_fragments) as executor:
            futures = {executor.submit(download_fragment, idx): idx for idx in pending_fragments}
            try:
                for future in concurrent.futures.as_completed(futures):
                    idx = futures[future]
                    try:
                        result = future.result()
                        if not result:
                            self.report_error(f'Fragment {idx + 1} download failed')
                            return False
                    except Exception as e:
                        self.report_error(f'Fragment {idx + 1} download error: {e}')
                        return False
            except KeyboardInterrupt:
                self._finish_multiline_status()
                self.report_error('Interrupted by user. Waiting for all threads to shutdown...', is_error=False, tb=False)
                executor.shutdown(wait=False)
                raise

        return self._finish_parallel_download(ctx, info_dict, content_len, ytdl_filename)

    def _finish_parallel_download(self, ctx, info_dict, content_len, ytdl_filename):
        if os.path.isfile(ytdl_filename):
            self.try_remove(ytdl_filename)

        self.try_rename(ctx.tmpfilename, ctx.filename)

        self._hook_progress({
            'downloaded_bytes': content_len,
            'total_bytes': content_len,
            'filename': ctx.filename,
            'status': 'finished',
            'elapsed': time.time() - ctx.start_time,
            'ctx_id': info_dict.get('ctx_id'),
        }, info_dict)

        return True
