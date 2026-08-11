with open("handlers.py", "r", encoding="utf-8") as f:
    content = f.read()

old = '''def _plan_detail_text(plan):
    custom_groups = "Unlimited" if plan["custom_groups"] == -1 else plan["custom_groups"]
    return (
        f"<b>{plan['name']} Plan</b>\\n\\n"
        f"Price: {plan['price']}\\n"
        f"Ad Accounts: {plan['ad_accounts']}\\n"
        f"Supported Groups: {plan['supported_groups']}\\n"
        f"Custom Groups Allowed: {custom_groups}\\n"
        f"Simultaneous Ads: {plan['simultaneous_ads']}\\n\\n"
        f"{plan['features']}"
    )'''

new = '''def _plan_detail_text(plan):
    benefits_lines = "\\n".join(f"\u2022 {b}" for b in plan.get("benefits", []))
    body = (
        f"{plan['name']} Plan\\n\\n"
        f"Price : {plan['price']}\\n\\n"
        f"Benefits :\\n{benefits_lines}"
    )
    return f"<b>{body}</b>"'''

if old not in content:
    print("NO MATCH — will show current version instead so we can fix it precisely.")
else:
    content = content.replace(old, new)
    with open("handlers.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("Plans display patch applied.")
