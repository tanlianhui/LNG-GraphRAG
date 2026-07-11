"""
asr_keywords.py — LNG Gaming channel vocabulary for Whisper initial_prompt.

Whisper uses this as decoder context before generation, biasing recognition
toward channel-specific terms without forcing them.
"""

# The 6 CONSTANT members (appear in almost every stream). Bias hardest toward these.
CONSTANT_MEMBERS = ["小六", "六探", "鳥屎", "Leggy", "八毛", "老王"]

# Names that come up occasionally (guests / less-frequent handles). Rare.
GUEST_MEMBERS = ["展邱", "奶哥", "悅悅", "顏顏", "蕾蕾", "探探", "天神"]

# Known ASR mishears → correct handle (for the cleanup glossary, NOT the ASR prompt,
# so we don't bias toward the wrong spelling). 八毛 is frequently heard as 巴毛.
MISHEARD = {"巴毛": "八毛"}

MEMBERS = CONSTANT_MEMBERS + GUEST_MEMBERS

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
# Keep under ~224 tokens; Whisper's prompt window is limited. A fuller, natural
# Traditional-Chinese sentence biases recognition better than a bare keyword list.
# 6 constant members lead (strongest bias); guests mentioned as occasional.
INITIAL_PROMPT = (
    "以下是LNG Gaming頻道的台灣華語遊戲直播內容，對話夾雜英文與台語。"
    "固定成員有" + "、".join(CONSTANT_MEMBERS) + "。"
    "偶爾會提到" + "、".join(GUEST_MEMBERS) + "。"
    "常玩的遊戲包括英雄聯盟、快打旋風、暗黑破壞神、派對動物、雲頂之弈、"
    "Valorant、魔獸世界、Metro 2033、Evoland。"
)
