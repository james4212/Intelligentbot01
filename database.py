database.pyimport sqlite3
import json
import asyncio
import aiosqlite
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from contextlib import asynccontextmanager

@dataclass
class User:
    user_id: int
    username: Optional[str]
    is_paid: bool
    subscription_end: Optional[datetime]
    created_at: datetime
    
@dataclass
class Group:
    group_id: int
    group_name: str
    owner_id: int
    is_active: bool
    activated_at: Optional[datetime]
    settings: Dict[str, Any]

@dataclass
class Analytics:
    date: str
    group_id: int
    message_count: int
    new_members: int
    spam_blocked: int

class Database:
    def __init__(self, db_path: str = 'bot_data.db'):
        self.db_path = db_path
    
    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Users table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    is_paid BOOLEAN DEFAULT 0,
                    subscription_end TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Groups table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS groups (
                    group_id INTEGER PRIMARY KEY,
                    group_name TEXT,
                    owner_id INTEGER,
                    is_active BOOLEAN DEFAULT 0,
                    activated_at TIMESTAMP,
                    settings TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (owner_id) REFERENCES users(user_id)
                )
            ''')
            
            # Analytics table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    group_id INTEGER,
                    message_count INTEGER DEFAULT 0,
                    new_members INTEGER DEFAULT 0,
                    spam_blocked INTEGER DEFAULT 0,
                    UNIQUE(date, group_id)
                )
            ''')
            
            # Spam tracking table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS spam_tracking (
                    user_id INTEGER,
                    group_id INTEGER,
                    message_count INTEGER DEFAULT 0,
                    last_message TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, group_id)
                )
            ''')
            
            # Authorized groups for users
            await db.execute('''
                CREATE TABLE IF NOT EXISTS user_groups (
                    user_id INTEGER,
                    group_id INTEGER,
                    is_authorized BOOLEAN DEFAULT 1,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, group_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (group_id) REFERENCES groups(group_id)
                )
            ''')
            
            await db.commit()
    
    @asynccontextmanager
    async def get_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            yield db
    
    # User methods
    async def get_user(self, user_id: int) -> Optional[User]:
        async with self.get_db() as db:
            cursor = await db.execute(
                'SELECT * FROM users WHERE user_id = ?', (user_id,)
            )
            row = await cursor.fetchone()
            if row:
                return User(
                    user_id=row['user_id'],
                    username=row['username'],
                    is_paid=bool(row['is_paid']),
                    subscription_end=row['subscription_end'],
                    created_at=row['created_at']
                )
            return None
    
    async def create_user(self, user_id: int, username: Optional[str] = None) -> User:
        async with self.get_db() as db:
            await db.execute(
                'INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)',
                (user_id, username)
            )
            await db.commit()
        return await self.get_user(user_id)
    
    async def activate_subscription(self, user_id: int, days: int = 30):
        end_date = datetime.now() + timedelta(days=days)
        async with self.get_db() as db:
            await db.execute(
                '''UPDATE users 
                   SET is_paid = 1, subscription_end = ? 
                   WHERE user_id = ?''',
                (end_date, user_id)
            )
            await db.commit()
    
    async def check_subscription(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        if not user:
            return False
        if not user.is_paid or not user.subscription_end:
            return False
        return datetime.now() < user.subscription_end
    
    # Group methods
    async def add_group(self, group_id: int, group_name: str, owner_id: int) -> Group:
        async with self.get_db() as db:
            await db.execute(
                '''INSERT OR REPLACE INTO groups 
                   (group_id, group_name, owner_id, is_active, activated_at, settings)
                   VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP, ?)''',
                (group_id, group_name, owner_id, json.dumps({
                    'spam_protection': True,
                    'welcome_message': True,
                    'auto_mute': True
                }))
            )
            await db.commit()
        return await self.get_group(group_id)
    
    async def get_group(self, group_id: int) -> Optional[Group]:
        async with self.get_db() as db:
            cursor = await db.execute(
                'SELECT * FROM groups WHERE group_id = ?', (group_id,)
            )
            row = await cursor.fetchone()
            if row:
                return Group(
                    group_id=row['group_id'],
                    group_name=row['group_name'],
                    owner_id=row['owner_id'],
                    is_active=bool(row['is_active']),
                    activated_at=row['activated_at'],
                    settings=json.loads(row['settings'] or '{}')
                )
            return None
    
    async def update_group_settings(self, group_id: int, settings: Dict[str, Any]):
        async with self.get_db() as db:
            await db.execute(
                'UPDATE groups SET settings = ? WHERE group_id = ?',
                (json.dumps(settings), group_id)
            )
            await db.commit()
    
    async def get_user_groups(self, user_id: int) -> List[Group]:
        async with self.get_db() as db:
            cursor = await db.execute(
                '''SELECT g.* FROM groups g
                   JOIN user_groups ug ON g.group_id = ug.group_id
                   WHERE ug.user_id = ? AND ug.is_authorized = 1''',
                (user_id,)
            )
            rows = await cursor.fetchall()
            return [Group(
                group_id=row['group_id'],
                group_name=row['group_name'],
                owner_id=row['owner_id'],
                is_active=bool(row['is_active']),
                activated_at=row['activated_at'],
                settings=json.loads(row['settings'] or '{}')
            ) for row in rows]
    
    # Analytics methods
    async def log_message(self, group_id: int):
        today = datetime.now().strftime('%Y-%m-%d')
        async with self.get_db() as db:
            await db.execute('''
                INSERT INTO analytics (date, group_id, message_count)
                VALUES (?, ?, 1)
                ON CONFLICT(date, group_id) 
                DO UPDATE SET message_count = message_count + 1
            ''', (today, group_id))
            await db.commit()
    
    async def log_new_member(self, group_id: int):
        today = datetime.now().strftime('%Y-%m-%d')
        async with self.get_db() as db:
            await db.execute('''
                INSERT INTO analytics (date, group_id, new_members)
                VALUES (?, ?, 1)
                ON CONFLICT(date, group_id) 
                DO UPDATE SET new_members = new_members + 1
            ''', (today, group_id))
            await db.commit()
    
    async def log_spam_blocked(self, group_id: int):
        today = datetime.now().strftime('%Y-%m-%d')
        async with self.get_db() as db:
            await db.execute('''
                INSERT INTO analytics (date, group_id, spam_blocked)
                VALUES (?, ?, 1)
                ON CONFLICT(date, group_id) 
                DO UPDATE SET spam_blocked = spam_blocked + 1
            ''', (today, group_id))
            await db.commit()
    
    async def get_stats(self, group_id: int, days: int = 7) -> List[Analytics]:
        async with self.get_db() as db:
            cursor = await db.execute('''
                SELECT * FROM analytics 
                WHERE group_id = ? AND date >= date('now', ?)
                ORDER BY date DESC
            ''', (group_id, f'-{days} days'))
            rows = await cursor.fetchall()
            return [Analytics(
                date=row['date'],
                group_id=row['group_id'],
                message_count=row['message_count'],
                new_members=row['new_members'],
                spam_blocked=row['spam_blocked']
            ) for row in rows]
    
    # Spam tracking
    async def check_spam(self, user_id: int, group_id: int, threshold: int = 5) -> bool:
        now = datetime.now()
        async with self.get_db() as db:
            # Get current count
            cursor = await db.execute(
                '''SELECT * FROM spam_tracking 
                   WHERE user_id = ? AND group_id = ?''',
                (user_id, group_id)
            )
            row = await cursor.fetchone()
            
            if not row:
                await db.execute(
                    '''INSERT INTO spam_tracking (user_id, group_id, message_count)
                       VALUES (?, ?, 1)''',
                    (user_id, group_id)
                )
                await db.commit()
                return False
            
            last_msg = datetime.fromisoformat(row['last_message'])
            count = row['message_count']
            
            # Reset if last message was more than 1 minute ago
            if (now - last_msg).seconds > 60:
                await db.execute(
                    '''UPDATE spam_tracking 
                       SET message_count = 1, last_message = ?
                       WHERE user_id = ? AND group_id = ?''',
                    (now, user_id, group_id)
                )
                await db.commit()
                return False
            
            # Increment count
            new_count = count + 1
            await db.execute(
                '''UPDATE spam_tracking 
                   SET message_count = ?, last_message = ?
                   WHERE user_id = ? AND group_id = ?''',
                (new_count, now, user_id, group_id)
            )
            await db.commit()
            
            return new_count >= threshold
    
    async def reset_spam_count(self, user_id: int, group_id: int):
        async with self.get_db() as db:
            await db.execute(
                'DELETE FROM spam_tracking WHERE user_id = ? AND group_id = ?',
                (user_id, group_id)
            )
            await db.commit()

db = Database()
