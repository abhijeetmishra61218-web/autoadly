# list_chats.py
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

API_ID = 37701222
API_HASH = "5e137a9ed23be5787dcdd9a92d9e48df"
SESSION_STRING = "1BVtsOLgBu2d_09lXu56BaCW9SOynMKCovdHXtzpsh1S39_T1RzIErXmEY9z0eudm_iMXM6fT2JNxdreAcZspLsRZ10g2sTAiu61XQy2IuGuiZF6bFluGxmKLv5Wbw1bEPkqwS1jlFZh_fAbQqAC0o314GQCNXo060L1YNrCA9aK9QCbRtKePiQSLYtpNr4ouCGu9298Ctx3FCQoVTY9kYP-EWsPkc3t1e8AqHoE7sNj0TZKnb-KOudCTaNEYGoHtkXETfPXYzOPJa-mWTvpRj06OaftbYklkYhkJdZHTKrQWPiUYMoAJ3eHV_80sBmPpG08nCqXG4hHky5PoDdhbLqsbUOKgI8c="

with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
    for dialog in client.iter_dialogs():
        if dialog.is_group or dialog.is_channel:
            print(f"Name: {dialog.name}")
            print(f"Chat ID: {dialog.id}")
            print(f"Is Forum: {getattr(dialog.entity, 'forum', False)}")
            print("-" * 40)