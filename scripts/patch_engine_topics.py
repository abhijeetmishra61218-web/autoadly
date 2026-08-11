with open("engine.py", "r", encoding="utf-8") as f:
    content = f.read()

old = '''    try:
        target = marketplace["chat_id"]
        top_msg_id = None
        if marketplace["is_forum"]:
            top_msg_id = await db.get_forum_topic(marketplace["id"], ad["category"])

        from_peer = await client.get_input_entity(ad["source_chat_id"])
        to_peer = await client.get_input_entity(target)

        await client(ForwardMessagesRequest(
            from_peer=from_peer,
            id=[ad["source_message_id"]],
            to_peer=to_peer,
            top_msg_id=top_msg_id,
            random_id=[random.getrandbits(63)]
        ))
        return True
    except FloodWaitError:
        return False
    except (ChatWriteForbiddenError, UserBannedInChannelError):
        return False
    except Exception as e:
        logger.info(f"Skipped marketplace {marketplace['id']}: {e}")
        return False'''

new = '''    try:
        target = marketplace["chat_id"]
        from_peer = await client.get_input_entity(ad["source_chat_id"])
        to_peer = await client.get_input_entity(target)

        if not marketplace["is_forum"]:
            await client(ForwardMessagesRequest(
                from_peer=from_peer, id=[ad["source_message_id"]], to_peer=to_peer,
                top_msg_id=None, random_id=[random.getrandbits(63)]
            ))
            return True

        candidates = await db.get_ranked_topics(marketplace["id"], ad["category"])
        if not candidates:
            candidates = [None]  # no topics known/open — try the general/default thread

        for top_msg_id in candidates[:4]:  # cap attempts to limit flood risk on one marketplace
            try:
                await client(ForwardMessagesRequest(
                    from_peer=from_peer, id=[ad["source_message_id"]], to_peer=to_peer,
                    top_msg_id=top_msg_id, random_id=[random.getrandbits(63)]
                ))
                return True
            except (FloodWaitError, ChatWriteForbiddenError, UserBannedInChannelError):
                raise
            except Exception:
                continue  # this topic rejected the post, try the next candidate

        return False
    except FloodWaitError:
        return False
    except (ChatWriteForbiddenError, UserBannedInChannelError):
        return False
    except Exception as e:
        logger.info(f"Skipped marketplace {marketplace['id']}: {e}")
        return False'''

assert old in content, "Could not find post_to_marketplace body to patch"
content = content.replace(old, new)

with open("engine.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Engine topic-fallback patch applied.")
