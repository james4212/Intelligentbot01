import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class Config:
    BOT_TOKEN: str = os.getenv('BOT_TOKEN', '8746827408:AAGvfAHF31mbV26D4JwV1Fqmwd5Cz-Vttv0')
    ADMIN_IDS: list = None
    DATABASE_PATH: str = 'bot_data.db'
    SUBSCRIPTION_PRICE: int = 10  # USD
    SUBSCRIPTION_DAYS: int = 30
    SPAM_THRESHOLD: int = 5  # messages per minute to trigger spam
    MUTE_DURATION: int = 3600  # 1 hour in seconds
    
    def __post_init__(self):
        if self.ADMIN_IDS is None:
            admin_ids = os.getenv('ADMIN_IDS', '')
            self.ADMIN_IDS = [int(x.strip()) for x in admin_ids.split(',') if x.strip()]
    
    @property
    def is_configured(self) -> bool:
        return self.BOT_TOKEN != '8746827408:AAGvfAHF31mbV26D4JwV1Fqmwd5Cz-Vttv0' and len(self.ADMIN_IDS) > 0

config = Config()
