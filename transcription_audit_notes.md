# Transcription Audit Notes (re-ASR quality spot-check)

Auditor: Claude Code. Dates: 2026-07-02/03.
Scope: raw `_combined.txt` produced by the giant-chunk rebuild (`rebuild_transcriptions.py`),
BEFORE Taiwan-LLM cleanup + CJK spacing. So "no punctuation" and silence-filler repetition are
expected and are fixed by the later cleanup pass — they are NOT ASR defects.

## Method
Read mid chunks (c4–c8) of each file, judged coherence / homophones / gibberish as a zh-TW reader.

## Overall verdict
Re-ASR quality is **good**. Content is coherent Taiwanese-Mandarin conversation with real substance
(vs the old truncated junk). Channel member names (老王/小六/六探/鳥屎/Leggy) and game/domain terms
(LoL/TPA/C9/AllStar, 魚露/香茅/彗星公主) are recognized correctly. Homophones are rare and
jargon-level. Two benign artifacts appear, both handled by the cleanup pass:
1. Repetition hallucination on silent/music chunks (e.g. 欸×70, 抱歉×45, 啊×90) → cheap_clean collapses.
2. No punctuation → Taiwan-LLM adds it.

## Files checked (17) — all PASS
1. 6tan vlog#10 女朋友沒朋友 (Shoot Log) — cleaned sample earlier; coherent.
2. LNG Gaming：英雄聯盟日常#2 窩們不放棄 (完整版) — coherent; minor game-term homophones.
3. 【LNG】2014/10/12 老洨勃道尼 and 桌遊 - 2/3 — coherent.
4. 【LNG】2015/01/11 被笑妄想症 — coherent (cash-balance story).
5. 【LNG】2014/12/21 關鍵性普羅王大戰 (Part 3) — coherent (haircut/massage talk).
6. 【LNG】2014/11/15 惱怒的情侶行為 - 5/8 — coherent; c6 抱歉×45 filler.
7. 【LNG】2014/10/05 閒聊 + Cubic Castle - 3/3 — coherent (Pizza Hut crust story).
8. 【LNG】2014/08/24 懷舊閒聊 - 2/2 — coherent; c6 啊×90 filler.
9. 【LNG】2015/01/04 等ㄌ~登ㄉㄌㄌ pt2 — coherent (boarding school / fitness).
10. 【LNG】2014/12/21 關鍵性普羅王大戰 (Part 5) — coherent (Vietnamese food; 魚露/香茅 correct).
11. 【LNG】2014/12/21 關鍵性普羅王大戰 (Part 1) — coherent; c4 欸×70 filler.
12. 【LNG】2014/11/08 老電影老歌曲 - 2/2 — mostly coherent; a couple short garbled spots.
13. 【LNG】2014/10/19 閒聊 + Killing Floor + ARAM - 1/3 — coherent.
14. 【LNG】2014/09/28 二次元的菜 - 1/3 — coherent; "沒慣"→likely 沒救 (minor).
15. LNG 日常：2015到2016的跨年不准笑 pt1 — coherent; member names correct.
16. LNG 實況紀錄 2014/07/06 實況存檔 pt01 — coherent (mic volume talk).
17. LNG 實況紀錄 2014/06/15 實況存檔 pt3 — coherent (noisy-neighbor talk).
    (+ also glanced: 實況紀錄 2014/05/11 pt1 — LoL AllStar/TPA/C9 correct; minor 罵道→罵到.)

## Not yet audited
## Files checked — batch 2 (18–30) — all PASS
18. 【LNG】2015/01/04 等ㄌ~登ㄉㄌㄌ pt1 — coherent (audio/mixing talk).
19. 【LNG】2014/12/21 關鍵性普羅王大戰 (Part 15) — coherent; "巴毛" = 八毛 mishear (see below).
20. 【LNG】2014/10/25 Unturned - 2/3 — coherent zombie-survival gameplay.
21. 【LNG】2014/09/07 閒聊 + 戰隊積分 - 1/2 — mostly coherent; one garbled spot ("安朝古堡", Minecraft).
22. LNG 實況紀錄 2014/05/25 實況存檔 — coherent (KTV/karaoke, "不上班" song).
23. LNG Live：爐石戰記 6tan試玩 P6 — coherent; English card text captured.
24. LNG Live：Metro Last Light #4 — coherent gameplay reactions.
25. LNG Live：Metro Last Light #12 — coherent; ENGLISH in-game dialogue transcribed in English (correct).
26. LNG Live：CoD Ghosts #8 — English mission dialogue captured; c10 莊×90 filler.
27. LNG Live：BioHazard6 with Leggy #17 — coherent co-op gameplay.
28. LNG Live：BioHazard6 with Leggy #09 — coherent.
29. LNG WorkShop Youtube 10萬訂閱 — coherent.
30. LNG日常：KTV及時唱噗浪點歌 十年 — short song file, coherent.

### New observations (batch 2)
- **八毛 ↔ 巴毛 mishear confirmed** in real output (Part 15). Fixed biasing prompt to list 八毛 before
  巴毛 (`asr_keywords.py`); cleanup glossary should map 巴毛 → 八毛.
- **English game dialogue** (Metro, CoD) transcribed in English — expected/correct, not an error.
- Silence/gunfire chunks still produce filler runs (莊×90 etc.) → collapsed by cleanup.

## Files checked — batch 3 (15) — all PASS
Tracking file: `scratchpad_audit_done.txt` (exact stems, so batches don't overlap).
- 6tan vlog#11 我的英文很爛 — coherent; member names 六探/鳥屎 correctly recognized.
- 6tan vlog#7 開實況跟當Youtuber — coherent (蔡阿嘎, PTT correct).
- 6tan vlog#9 網路戀情是壞事嗎 — coherent.
- 6tan&Leggy黑白大冒險 #1 c9online, #2 RIFT — coherent bilingual banter.
- LNG Gaming：Evoland #1,#2,#3,#4,#5,#6,#9,#12,#13,#15 — coherent; heavily BILINGUAL (English
  in-game dialogue + Chinese commentary), handled well. Minor garbles: "麗嘎嘎" (#15), "猛哥" (#13).

### Observations (batch 3)
- Member-name recognition working in raw ASR (六探/鳥屎 seen correctly).
- Bilingual game titles (Evoland, c9online) transcribe both languages correctly — not errors.

## Files checked — batch 4 (20) — all PASS
- LNG Gaming：Leggy 第一次開飛機 in BattleField3 — coherent (flying/plane controls).
- LNG Gaming：Metro2033 戰慄深邃 #7,#9,#10,#11,#12,#19,#21,#22,#23,#25,#26,#28,#29 — coherent;
  bilingual (English Metro dialogue + Chinese commentary; even Russian game slang "blin" #28).
- LNG Gaming：Miasmata #04,#05 — coherent (map-drawing survival).
- LNG Gaming：PlanetSide2 迷路×空降×被車撞 — coherent.
- LNG Gaming：RTS愛好者咕嚕#1 — coherent.
- LNG Gaming：SMS Racing 開車車×傳訊訊 — coherent; intro "我是劉燦" likely 六探 self-intro misheard.
- LNG Gaming：Sumotori Dreams 喝醉醉x推人人 — coherent.

### Observation (batch 4)
- Possible handle mishear "劉燦" ← 六探's self-intro; watch for it (candidate for MISHEARD map if recurring).

## Files checked — batch 5 (20) — all PASS
- Surgeon Simulator 2013, Warhammer Online (×2, bilingual), 邊緣禁地2 #1/#3/#4 (Leggy correct),
  LNG Live test, BioHazard6 with Leggy — coherent.
- 英雄聯盟日常#3 有禮貌運動, 跟給酷大師一起玩英雄聯盟 — coherent ("給cool" = guest 給酷 running gag).
- Beyond Two Souls 超能殺機 #3,#4,#6,#7,#10,#11,#13,#14,#18,#19 — coherent; heavily ENGLISH game
  dialogue transcribed correctly. #6 = 嗚×90 silence filler (cleanup collapses).

## Files checked — batch 6 (20) — all PASS
- BioHazard6 with Leggy (×8 more) — coherent co-op; fine detail captured (airsoft "KWC1911CO2版",
  guest nicknames 雅雯/古拉頻道).
- DLC Quest #2,#3,#4 — coherent bilingual.
- Metro Last Light 最後曙光 #1,#2,#3,#6,#7,#10,#13,#14 — coherent; bilingual; streaming-setup chatter.
- LNG Singing：Bruno Mars - When I Was Your Man — English lyrics transcribed correctly.

## Files checked — batch 7 (20) — all PASS
- LNG 實況紀錄 2014/04/13,04/27,05/04,05/18,06/22,08/09(×2) — coherent; members 巴毛(→八毛)/鳥屎/
  Leggy/六探 recognized in raw ASR.
- LNG 日常 跨年不准笑 pt1/pt2 (pt2 = 巴毛套裝×45 filler), 為什麼肋排附的是奶油刀 (巴毛/butter knife),
  其實我真的不知道拍這幹嘛, 噗浪表情模擬 — coherent.
- KTV及時唱噗浪點歌 Call me maybe/印度公園/天后/店斯 — English/Chinese song lyrics captured
  (lyric homophones minor, e.g. 天后 "寂寞芒果").
- LNG Singing：Leggy - Home — JAPANESE lyrics transcribed (幸せは…). LOL拳擊節, 台南行,
  Leggy台實況存檔 2013/11/10 — coherent.

### Observation (batch 7)
- 巴毛 appears frequently in raw output → MISHEARD 巴毛→八毛 (deterministic in cheap_clean) is well justified.
- Multilingual (JP/EN songs, EN game dialogue) transcribed in-language — expected, not errors.

## Files checked — batch 8 (20) — all PASS
- Youtube實況測試; 拼人臉遊戲 #1,#2,#3 (crude 老二 humour, coherent); 隨堂考 - 2/3 (reads quotes fine);
  十萬訂閱鳥屎女裝 - 1/2/5/6 (member 鳥屎 correct; #2 = 嗯嗯嗯 filler); Unturned #1,#3; 閒聊+Trove #3
  (鳥屎 correct); 找安找安 #1,#2 (#2 "Bang bang my my…" song); 關鍵性普羅王大戰 Part 4,6,8,9,10,16
  — all coherent. Minor: "牙術"→亞索/Yasuo (LoL champ, #10).

## Files checked — batch 9 / FINAL (18) — all PASS
- 【LNG】2015/02/01,02/08,02/15,02/22,03/08(八毛當兵趣),03/22(八毛回來牛頭王 pt1-4),03/29,
  04/19(卡祖笛大濕),04/26,05/03 — coherent; **八毛 correctly recognized** in title/content;
  鳥屎/六探 correct. pt3 = Yaw×90 filler.
- Recent streams: 【LNG】2025DEC, 2026JAN, 2026FEB, 2026MAR, 2026APR — coherent. Minor "登體" garble (MAR).

## Files checked — batch 10 (22, 2015 salvaged re-ASR) — all PASS
2015/05/03 pt2, 05/10 pt1/pt2, 05/17, 05/24, 06/06 pt2, 06/20 pt2, 06/28, 07/05, 07/12 pt1/pt2,
07/19, 07/26, 08/02, 08/09, 08/16, 08/22 (×2), 09/05, 09/13, 10/11, 11/08 — all coherent.
- **八毛 correctly recognized** (絞盡腦汁 pt2, You know what I saying) — updated prompt working;
  小六/六探/老王/鳥屎/Leggy also correct.
- Minor: 退伍→"退輪美" garble (食指尿尿); "好想再吃烤餅×13" chant filler (cleanup collapses).
- These were salvaged from PCM-in-MP4 sources + re-ASR'd this session — quality on par with the rest.

## Files checked — batch 11 (3) — all PASS
2015/11/15 急智人大戰, 11/29 公公他偏頭銅, 12/19 超級繞口令大戰 — coherent.

## Files checked — batch 12 (14, 2015-12 + 2016) — all PASS
2015/12/26, 2016 04/17,05/01,05/15,05/22,05/29,06/05,06/19,06/26,07/03,07/10,07/24 pt1/pt2,08/07
— all coherent. Members correct: 八毛 (PokemonGO "我們家八毛…灑花"), 老王, 鳥屎.
- Minor: "蛋玩論破" = Danganronpa/彈丸論破 game-title homophone; 登×80 / 啊×N filler (cleanup collapses).

## Files checked — batch 13 (24, 2016–2017) — all PASS
2016/08/14–2017/01/15 range (勃, 台北不是你的家, 醜照一籮筐, Gmod, 偶鼻喉摳, LOL普羅王, 超級說書人,
雞籃高手, 鳥人, 3D屌力全開, 購物狂, 維基解密, WABIS, 上/下, 老王睡著了 pt2, 燒餅DJ台, 印加寶藏,
Chivalry, 掩飾禿頭, 看看以前的自己). All coherent.
- Members/guests correct: 小六/六探/鳥屎, guests 燒餅/喵小.
- Minor: "雞籃高手"=灌籃高手 (Slam Dunk); filler 牛奶×N / Pam×N (cleanup collapses).

## Files checked — batch 14 (28, 2017) — all PASS
2017/02/12–08/27 range (Tricky Tower, 殘酷二選一, Drawful2, LoL/ARAM, Gang Beasts, Overwatch,
Alien Swarm, 故事接龍, 你畫我猜 ×2, 酷黑雙爸, etc.). All coherent.
- Members nailed: Tricky Tower "我小六八毛鳥屎你要標一下誰是誰" (小六/八毛/鳥屎 all correct); 老王/Leggy;
  guest 中山大謙.
- Minor garbles: "熏暗太怯帥" (title), "重雷腰"; filler 不×N (Tricky Tower).

## Files checked — batch 15 (28, 2017-2018) — all PASS
2017/09/03–2018/12/16 range (版權小精靈, 超級雞馬, 鼠肯斯坦/Overwatch, 英霸電腦, 似顏繪, 台聚存檔,
急智歌王, 春酒, 工商超人, 你畫我猜, 黃牌 上/下, etc.). All coherent.
- Members correct: 小六 (北部台聚 "小六重嗎59公斤"), 八毛 (春酒 "坐八毛位置"), Leggy; guest 湯湯.
- Benign: 安×80 / 卡×90 filler; one "[Error in chunk 6: invalid audio]" marker (cleanup drops it).

## Coverage — rolling (updated as rebuild produces more)
All good (`<=60s`-chunk) `_combined.txt` files spot-checked as of 2026-07-09: 338/338 done files
covered. Good count grown 172→185→209→224→304→338 as rebuild+salvage+refetch produced more.
Tracked in `scratchpad_audit_done.txt`. Remaining ~60 broken (47 need YouTube refetch, 11 local WAV —
mostly recent multi-hour VODs; still processing).

## Files checked — batch 16 (34, 2015-2021 incl. refetched) — all PASS
2015/06/20, 2016/03/13, 2017, 2019 (歡樂KTV 4h, KTV/桌遊/鄉巴佬日本行/去鳥屎家/etc.),
2020 (春酒/傭兵造句/9Key/魯天古野家/etc.), 2021 (隻狼/中樂透/DnD/水波爐/etc.). All coherent.
- Members correct: 小六, 八毛+Leggy (DnD "我跟八毛還有Leggy已經回來了"), 鳥屎.
- Games/terms: 隻狼(Sekiro), 動物森友會, Switch, 水波爐 — correct.
- Note: weird 2020-21 TITLES (喇咬郎BOGI, 金蘇魯3080…) are the channel's actual meme titles, NOT errors.
- Benign: 呵×90 / 不理×N filler; one "[Error in chunk: invalid audio]" marker.
- The 4h+ "monster" VODs (歡樂KTV etc.) transcribed fine end-to-end — confirms no big-file bug.

## Overall verdict (unchanged, 338 files audited)
Re-ASR quality is **good across the board** — coherent zh-TW, correct EN/JP in bilingual segments,
members (小六/六探/鳥屎/Leggy/八毛/老王) + guests recognized. Only benign, cleanup-handled artifacts:
silence/music/gunfire repetition filler, occasional homophones (game/lyric-level), no punctuation
(raw ASR). No systemic defect. Proceed to cleanup after rebuild completes.

## Final verdict
Re-ASR quality is **good across the board**. No systemic defect. Content is coherent Taiwanese-Mandarin
(+ correct English/Japanese in bilingual game/song segments). Channel members (小六/六探/鳥屎/Leggy/
八毛/老王) and game/domain terms are recognized well. All flagged issues fall into two benign,
already-handled buckets:
1. Silence/music/gunfire → repetition filler (嗯×N, 啊×N, Yaw×N, 莊×N) — collapsed by `cheap_clean`.
2. Occasional homophones — rare, jargon/lyric-level; the notable recurring one (巴毛→八毛) is fixed
   deterministically. Others (亞索/牙術, 登體, 麗嘎嘎) are isolated and low-impact.
Punctuation is absent by design (raw ASR) and added by the Taiwan-LLM cleanup pass.

Recommendation: proceed with cleanup (postprocess + CJK spacing) after the full rebuild finishes; no
re-ASR-level fixes needed for the audited files.
