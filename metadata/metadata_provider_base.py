import unicodedata

from utils.logger import setup_logger


class MetadataProvider:

    def __init__(self):
        self.logger = setup_logger(__name__)

    def replace_weird_characters(self, string):
        return ''.join(c for c in unicodedata.normalize('NFD', string)
                       if unicodedata.category(c) != 'Mn')

    def get_metadata(self, id, type):
        raise NotImplementedError
    
    async def get_duration_from_tmdb(self, tmdb_id, media_type='movie', season=None, episode=None):
        raise NotImplementedError
