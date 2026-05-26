"""
asr_keywords.py — LNG Gaming channel vocabulary for Whisper initial_prompt.

Whisper uses this as decoder context before generation, biasing recognition
toward channel-specific terms without forcing them.
"""

MEMBERS = [
    # Core LNG Gaming members (handles used on stream)
    "小六", "六探",          # Xiao Liu / Six
    "鳥屎",                  # Niao Shi
    "Leggy",                 # Leggy
    "巴毛", "八毛",           # Ba Mao
    "老王",                  # Lao Wang
    "大毛",                  # Da Mao
    "展邱",                  # Zhan Qiu
    "梁兄",                  # Liang Xiong
    "乃哥",                  # Nai Ge
    "阿旺",                  # A Wang
    "托老師",                # Tuo Laoshi
    "素雲",                  # Su Yun
    "天神",                  # Tian Shen
    "Fick", "FIG",           # Fick / FIG
    "Pasta", "Yakisoba",     # mentioned in older streams
]

BRAND = ["LNG", "LNG Gaming", "LNG Workshop", "廢物工作室"]

GAMES = [
    "英雄聯盟", "LoL",
    "暗黑破壞神", "Diablo",
    "快打旋風", "街頭霸王",
    "派對動物", "Party Animals",
    "Teamfight Tactics", "TFT", "雲頂之弈",
    "Valorant", "VALO",
    "魔獸世界", "WoW",
    "PlanetSide 2",
    "Miasmata",
    "Metro 2033",
    "Evoland",
    "Gang Beasts",
    "Chivalry",
    "BattleField", "戰地風雲",
    "我的世界", "Minecraft",
]

PLATFORMS = ["Twitch", "YouTube", "IG", "Discord"]

# Taiwanese internet / streamer slang that ASR commonly mishears
SLANG = [
    "工商", "抖內", "斗內",   # sponsorship / donations
    "實況", "開台", "關台",   # streaming terms
    "觀眾", "聊天室",          # audience / chat
    "訂閱", "超級留言",        # subscribe / super chat
    "黑白",                    # casual expression
]

# Build the initial_prompt string — natural-sounding so Whisper uses it as context.
# Keep under ~224 tokens; Whisper's prompt window is limited.
INITIAL_PROMPT = (
    "LNG Gaming頻道直播內容，台灣華語。"
    "頻道成員：" + "、".join(MEMBERS[:12]) + "等。"
    "常見遊戲：英雄聯盟、快打旋風、暗黑破壞神、派對動物、TFT、Valorant。"
    "平台：Twitch、YouTube。"
)
