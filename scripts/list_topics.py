# list_topics.py
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest

API_ID = 37701222
API_HASH = "5e137a9ed23be5787dcdd9a92d9e48df"
SESSION_STRING = "1BVtsOLgBu2d_09lXu56BaCW9SOynMKCovdHXtzpsh1S39_T1RzIErXmEY9z0eudm_iMXM6fT2JNxdreAcZspLsRZ10g2sTAiu61XQy2IuGuiZF6bFluGxmKLv5Wbw1bEPkqwS1jlFZh_fAbQqAC0o314GQCNXo060L1YNrCA9aK9QCbRtKePiQSLYtpNr4ouCGu9298Ctx3FCQoVTY9kYP-EWsPkc3t1e8AqHoE7sNj0TZKnb-KOudCTaNEYGoHtkXETfPXYzOPJa-mWTvpRj06OaftbYklkYhkJdZHTKrQWPiUYMoAJ3eHV_80sBmPpG08nCqXG4hHky5PoDdhbLqsbUOKgI8c="
FORUM_CHAT_ID = -1001676369027  # quick Market

with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
    entity = client.get_entity(FORUM_CHAT_ID)
    result = client(GetForumTopicsRequest(
        peer=entity,
        offset_date=None,
        offset_id=0,
        offset_topic=0,
        limit=100
    ))
    for topic in result.topics:
        print(f"Topic: {topic.title}")
        print(f"Topic ID: {topic.id}")
        print("-" * 40)