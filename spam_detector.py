import re
from typing import List, Tuple
import aiohttp

class SpamDetector:
    def __init__(self):
        self.suspicious_patterns = [
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
            r't\.me/\w+',
            r'telegram\.me/\w+',
            r'@\w{4,}',  # Username mentions
            r'(?:btc|bitcoin|crypto|forex|invest|earn|money|cash|profit).{0,20}(?:fast|quick|easy|free|guaranteed)',
            r'(?:click|join|subscribe).{0,10}(?:here|now|link)',
            r'(?i)\b(viagra|cialis|casino|lottery|winner|prize)\b',
        ]
        self.allowed_links = []  # Whitelist domains
    
    def contains_link(self, text: str) -> bool:
        """Check if message contains any links"""
        if not text:
            return False
        
        for pattern in self.suspicious_patterns[:3]:  # URL patterns
            if re.search(pattern, text):
                return True
        return False
    
    def is_spam(self, text: str, user_history: List[str] = None) -> Tuple[bool, str]:
        """
        Returns (is_spam, reason)
        """
        if not text:
            return False, ""
        
        text_lower = text.lower()
        
        # Check for spam patterns
        for pattern in self.suspicious_patterns:
            if re.search(pattern, text):
                return True, "Suspicious content detected"
        
        # Check for repetitive messages (if history provided)
        if user_history and len(user_history) > 3:
            recent = user_history[-3:]
            if all(msg == text for msg in recent):
                return True, "Repetitive message detected"
        
        # Check for excessive caps
        if len(text) > 20:
            caps_ratio = sum(1 for c in text if c.isupper()) / len(text)
            if caps_ratio > 0.7:
                return True, "Excessive capitalization"
        
        # Check for excessive emojis
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"  # emoticons
            u"\U0001F300-\U0001F5FF"  # symbols & pictographs
            u"\U0001F680-\U0001F6FF"  # transport & map symbols
            u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
            u"\U00002702-\U000027B0"
            u"\U000024C2-\U0001F251"
            "]+", flags=re.UNICODE)
        
        emojis = emoji_pattern.findall(text)
        if len(emojis) > 5:
            return True, "Excessive emoji usage"
        
        return False, ""
    
    def has_forbidden_content(self, text: str) -> bool:
        """Check for strictly forbidden content"""
        forbidden = [
            r'child\s*porn',
            r'cp\s*link',
            r'drug\s*dealer',
            r'hitman',
            r'kill\s*yourself',
        ]
        for pattern in forbidden:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

spam_detector = SpamDetector()
