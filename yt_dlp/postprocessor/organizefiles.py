import json
import os
from datetime import datetime

from .common import PostProcessor
from ..compat import shutil
from ..utils import (
    PostProcessingError,
    make_dir,
    variadic,
)


class OrganizeFilesPP(PostProcessor):
    def __init__(self, downloader=None, path_template='%(upload_year)s/%(upload_month)s/%(uploader)s',
                 database_path='download_history.json', keep_original=False):
        PostProcessor.__init__(self, downloader)
        self.path_template = path_template
        self.database_path = database_path
        self.keep_original = keep_original

    @classmethod
    def pp_key(cls):
        return 'OrganizeFiles'

    def _get_unique_path(self, base_path):
        if not os.path.exists(base_path):
            return base_path
        
        dirname, filename = os.path.split(base_path)
        name, ext = os.path.splitext(filename)
        counter = 1
        
        while True:
            new_filename = f'{name}_{counter}{ext}'
            new_path = os.path.join(dirname, new_filename)
            if not os.path.exists(new_path):
                return new_path
            counter += 1

    def _load_database(self):
        if not os.path.exists(self.database_path):
            return []
        try:
            with open(self.database_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            self.report_warning(f'无法读取数据库文件 {self.database_path}，将创建新的数据库')
            return []

    def _save_database(self, data):
        try:
            make_dir(self.database_path, PostProcessingError)
            with open(self.database_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except IOError as e:
            self.report_warning(f'无法保存数据库文件 {self.database_path}: {e}')

    def _add_to_history(self, info, new_path):
        history = self._load_database()
        
        entry = {
            'id': info.get('id'),
            'title': info.get('title'),
            'uploader': info.get('uploader'),
            'upload_date': info.get('upload_date'),
            'original_path': info.get('filepath'),
            'new_path': new_path,
            'download_timestamp': datetime.now().isoformat(),
            'extractor': info.get('extractor'),
            'webpage_url': info.get('webpage_url'),
        }
        
        history.append(entry)
        self._save_database(history)
        self.to_screen(f'已添加到下载历史: {new_path}')

    def run(self, info):
        filepath = info.get('filepath')
        if not filepath or not os.path.exists(filepath):
            self.report_warning('文件不存在，跳过组织')
            return [], info
        
        relative_dir = self._downloader.evaluate_outtmpl(self.path_template, info, sanitize=True)
        if not relative_dir:
            self.report_warning('路径模板解析结果为空，跳过组织')
            return [], info
        
        filename = os.path.basename(filepath)
        if os.path.isabs(filepath):
            base_dir = os.path.dirname(filepath)
        elif os.path.isabs(relative_dir):
            base_dir = ''
        else:
            base_dir = os.getcwd()
        
        target_dir = os.path.join(base_dir, relative_dir) if base_dir else relative_dir
        target_path = os.path.join(target_dir, filename)
        
        if os.path.abspath(filepath) == os.path.abspath(target_path):
            self.to_screen('文件已在目标位置，跳过移动')
            return [], info
        
        final_path = self._get_unique_path(target_path)
        
        try:
            make_dir(final_path, PostProcessingError)
            
            if self.keep_original:
                self.to_screen(f'复制文件 "{filepath}" 到 "{final_path}"')
                shutil.copy2(filepath, final_path)
            else:
                self.to_screen(f'移动文件 "{filepath}" 到 "{final_path}"')
                shutil.move(filepath, final_path)
            
            self._add_to_history(info, final_path)
            
            info['filepath'] = final_path
            return [], info
            
        except Exception as e:
            raise PostProcessingError(f'组织文件时出错: {e}')
