import asyncio
import join_engine

raw_list = [
    "AnvesanaMarket",  # already added but harmless to include again, will just skip cleanly
    "PromotionsOFM", "ofmworkk", "datingappsnetwork", "ofmboardj", "zazazamkx",
    "OFMManiacs", "ofmserviceswork", "ofmjoino", "orbisgroup2", "OFMTheHub",
    "IGMarket2024", "FVMJobs", "ofmtrade", "redditofmgroup", "ofmadvault",
    "OFMPromote", "pinkvibescommunity", "OFMgrind", "ofmmonopoly",
    "S4SandPromo", "kimsocialMP", "GooMarketplace", "RareHandle",
    "texted", "markeplacetopic", "guremarketplace", "SocialCove", "errormystry",
    "marketplace_forums", "sectorsocial", "pluggerz", "crisgalaxymarket",
    "CreeperForum", "crypto_forums", "buffestmarket", "iinvd", "stockless",
    "aizenmarket", "marketogs", "Nitroraid", "securedmarts", "marketunlimited",
    "vrstudios", "totalsmp", "EscrowpIace",
    "Social_M_Marketplace", "VipexMarket", "TradeMarketHub",
    "CLogyShopGc",
]

unique = list(dict.fromkeys(raw_list))
print(f"{len(raw_list)} entries, {len(unique)} unique after dedup.")

asyncio.run(join_engine.run_join_batch(unique))
