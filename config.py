
import os
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class Config:
    BOT_TOKEN: Optional[str] = os.getenv('BOT_TOKEN')
    ADMIN_IDS: List[int] = None
    DATABASE_PATH: str = 'bot_data.db'
    SUBSCRIPTION_PRICE: int = 10
    SUBSCRIPTION_DAYS: int = 30
    SPAM_THRESHOLD: int = 5
    MUTE_DURATION: int = 3600

    def __post_init__(self):
        admin_ids = os.getenv('ADMIN_IDS', '')
        self.ADMIN_IDS = [int(x.strip()) for x in admin_ids.split(',') if x.strip()]

    @property
    def is_configured(self) -> bool:
        return bool(self.BOT_TOKEN) and len(self.ADMIN_IDS) > 0

config = Config()
