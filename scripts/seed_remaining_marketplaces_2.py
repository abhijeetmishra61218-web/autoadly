import asyncio
import join_engine

remaining = [
    "IGMarket2024", "FVMJobs", "ofmtrade", "redditofmgroup", "ofmadvault",
    "OFMPromote", "pinkvibescommunity", "OFMgrind", "ofmmonopoly",
    "S4SandPromo", "kimsocialMP", "GooMarketplace", "RareHandle",
    "texted", "markeplacetopic", "guremarketplace", "SocialCove", "errormystry",
    "marketplace_forums", "sectorsocial", "pluggerz", "crisgalaxymarket",
    "CreeperForum", "crypto_forums", "buffestmarket", "stockless",
    "aizenmarket", "marketogs", "Nitroraid", "securedmarts", "marketunlimited",
    "vrstudios", "totalsmp", "EscrowpIace",
    "Social_M_Marketplace", "VipexMarket", "TradeMarketHub",
    "CLogyShopGc",
]

print(f"{len(remaining)} marketplace(s) remaining to join.")
asyncio.run(join_engine.run_join_batch(remaining))
