"""路书日页 AI 诊断 — 按当天 POI 生成差异化文案。"""

from __future__ import annotations

from typing import Any

from anchor.plan_diagnosis import (
    CON_COPY,
    CON_TIPS,
    PlanDayMetrics,
    PlanMetrics,
    _attract_ratio,
    _tran_ratio,
)
from anchor.tag_mapping import has_hardcore_tag, has_low_stamina_tag

# 景点名 → 当日亮点 / 避坑（贴近 seed_poi_data）
POI_ADVICE: dict[str, dict[str, str]] = {
    "故宫博物院": {
        "highlight": "故宫中轴线节奏感强，午门进、神武门出最顺；珍宝馆与钟表馆需另排 1 小时。",
        "caution": "周末预约票紧，建议开馆前 30 分钟到安检口，鞋要耐走。",
    },
    "天坛公园": {
        "highlight": "祈年殿外围拍照最出片，回音壁一带适合慢慢绕，不必硬挤中心机位。",
        "caution": "公园面积大，带长辈可少排一个远景点，留足回酒店缓冲。",
    },
    "颐和园": {
        "highlight": "昆明湖沿线风大但视野开阔，佛香阁登高前可在长廊歇脚补能量。",
        "caution": "北宫门进出坡度多，推婴儿车建议改东宫门路线。",
    },
    "八达岭长城": {
        "highlight": "北线坡度更陡、人更少；索道上下能省下体力留给城墙段。",
        "caution": "台阶落差大，膝盖不适别硬爬全程，备手套扶栏。",
    },
    "南锣鼓巷": {
        "highlight": "主街热闹、胡同深处更安静，适合穿插一家独立小店再回主路。",
        "caution": "高峰时段主街拥挤，想拍照可拐进帽儿胡同等支巷。",
    },
    "什刹海风景区": {
        "highlight": "后海一圈步行轻松，傍晚荷风与酒吧灯影叠在一起，适合慢节奏收尾。",
        "caution": "湖边风大，春秋备薄外套；想坐人力车先问清路线和价格。",
    },
    "798艺术区": {
        "highlight": "工业风厂房与展陈交替，按片区逛比逐馆打卡更省力。",
        "caution": "部分展馆周一闭馆，出发前看当日展讯。",
    },
    "天安门广场": {
        "highlight": "广场视野开阔，与故宫、国家博物馆可同日串联，注意安检与预约规则。",
        "caution": "安检严格，大包少带；升降旗时段人流集中，提前占位。",
    },
    "中山陵景区": {
        "highlight": "博爱坊到祭堂台阶较长，侧道缓坡更友好；音乐台一带适合中途歇脚。",
        "caution": "台阶段对老人不友好，可只走博爱坊至陵门拍照折返。",
    },
    "夫子庙秦淮风光带": {
        "highlight": "日逛庙市、夜看秦淮灯影，水上游船与步行动线可二选一避免重复。",
        "caution": "河边小吃摊先问价再点，高峰时段注意随身物品。",
    },
    "南京博物院": {
        "highlight": "历史馆与民国馆最值得留时，建议进馆先拿导览图排优先级。",
        "caution": "需预约，周末排队入馆久，可自带轻便零食在休息区补能。",
    },
    "玄武湖景区": {
        "highlight": "环湖步道平缓和缓，城墙根下拍照与划船都轻松，适合亲子日。",
        "caution": "湖面风大，别排太满，留 1 小时自由漫步即可。",
    },
    "总统府": {
        "highlight": "中西合璧建筑密集，中轴主线 2 小时能看完，花园适合短暂歇脚。",
        "caution": "夏季室内外交替，备水；出口方向提前看好避免折返。",
    },
    "牛首山文化旅游区": {
        "highlight": "佛顶宫室内震撼，室外步道较长，景区巴士能省一段爬坡。",
        "caution": "整体台阶与步行偏多，带娃建议用推车并避开正午暴晒。",
    },
    "老门东历史街区": {
        "highlight": "比夫子庙更生活气，适合找一家小店坐窗边看巷弄人流。",
        "caution": "石板路不平，高跟鞋慎选；热门小吃可错峰下午三点左右。",
    },
    "栖霞山风景区": {
        "highlight": "红叶季与平日气质不同，栖霞寺一线古意浓，适合摄影慢走。",
        "caution": "山地台阶多，穿防滑鞋；秋冬日落早，别拖太晚下山。",
    },
    "洪崖洞民俗风貌区": {
        "highlight": "吊脚楼与江景叠在一起，傍晚灯光渐起时最好看，建议先上层后顺坡下。",
        "caution": "节假日电梯排队久，穿舒适鞋走楼梯反而更快。",
    },
    "解放碑步行街": {
        "highlight": "城市客厅感强，适合作为当日枢纽，向八一路、较场口方向都好延伸。",
        "caution": "路口多、立体交通复杂，跟导航别盲穿地下通道。",
    },
    "磁器口古镇": {
        "highlight": "主街逛吃 2 小时足够，岔路里的小院和江景更出片。",
        "caution": "首个麻花/火锅摊排队最长，往里走往往更从容。",
    },
    "李子坝轻轨穿楼观景": {
        "highlight": "观景平台停留 20 分钟足够，可与鹅岭二厂串成一条轻量动线。",
        "caution": "平台机位窄，高峰挤；注意轨道安全线，别探身拍照。",
    },
    "长江索道": {
        "highlight": "过江视角独特，建议预约非高峰时段，舱内靠窗站位更值。",
        "caution": "排队时间波动大，风大天候可能停运，留备选交通。",
    },
    "南山一棵树观景台": {
        "highlight": "重庆夜景经典机位，日落后蓝调时刻别错过，带件防风外套。",
        "caution": "上山车多弯急，易晕车者可备药；夜间下山注意保暖。",
    },
    "大足石刻景区": {
        "highlight": "宝顶山摩崖造像密集，跟讲解动线走更看得懂故事。",
        "caution": "距市区远，单程车程长，当天别排第二个重景点。",
    },
    "鹅岭二厂文创园": {
        "highlight": "老厂房改文创，天台与涂鸦墙适合轻松拍照，强度不高。",
        "caution": "坡道多，与李子坝同日要控制总步行量。",
    },
    "天山天池风景区": {
        "highlight": "高山湖泊空气通透，区间车+环湖轻徒步组合最省力。",
        "caution": "海拔与温差大，防晒和薄羽绒都要带。",
    },
    "新疆国际大巴扎": {
        "highlight": "民族建筑与市集氛围浓，适合买干果、看歌舞，傍晚更热闹。",
        "caution": "市集比价再下手，背包前背防拥挤蹭碰。",
    },
    "新疆维吾尔自治区博物馆": {
        "highlight": "干尸馆与新疆历史展是核心，建议预留 2 小时安静看展。",
        "caution": "需预约，周一闭馆；馆内温度低，备薄外套。",
    },
    "红山公园": {
        "highlight": "城市制高点俯瞰乌鲁木齐全景，强度低，适合作为抵达首日缓冲。",
        "caution": "台阶虽不多，夏季暴晒，上午或傍晚去更舒服。",
    },
    "葡萄沟风景区": {
        "highlight": "沟内凉爽、葡萄架下步行轻松，适合亲子与长辈。",
        "caution": "与市区有温差，备长袖；品尝现摘注意清洗。",
    },
    "喀纳斯景区": {
        "highlight": "三湾（神仙湾、月亮湾、卧龙湾）顺序浏览最顺，区间车衔接成熟。",
        "caution": "区间车程长，当天以 1–2 个精华点为主，别贪多。",
    },
    "天山大峡谷": {
        "highlight": "红层峡谷与森林反差大，步行道维护好，拍照点集中。",
        "caution": "景区范围大，穿防滑鞋；冬季部分路段封闭需提前查。",
    },
    "禾木村": {
        "highlight": "晨雾与木屋炊烟是招牌，建议住一晚或赶早班车进村的摄影时段。",
        "caution": "早晚温差极大，观晨雾多等 1 小时，备暖饮和手套。",
    },
}

TIER_FALLBACK: dict[str, str] = {
    "特级": "{name}属于大步幅景区，建议索道/区间车能坐就坐，把体力留给核心一段。",
    "高级": "{name}展陈或古镇范围大，先定 1 个必看子区域，避免馆内硬逛到闭馆。",
    "中级": "{name}适合城市慢逛拍照，2 小时左右节奏最舒服。",
    "低级": "{name}强度不高，适合穿插在重景点之间当缓冲站。",
}

MEAL_NOTE: dict[str, str] = {
    "火锅": "火锅建议错峰，先点少后加菜，毛肚七上八下别煮老。",
    "小面": "小面选干溜或带汤看口味，加煎蛋就很有本地感。",
    "烤鸭": "烤鸭片皮先吃，鸭架汤留到最后暖胃。",
    "南京小吃": "鸭血粉丝汤趁热，别与太多冷食混着吃。",
    "金陵菜": "金陵菜偏甜鲜，点菜先问招牌再追加。",
    "新疆菜": "大盘鸡配皮带面最完整，分量大可两人Share。",
    "烧烤": "烤串现烤现吃，别一次点太多容易凉。",
    "馕/小吃": "馕现买现吃最香，配热茶比冷饮更搭。",
}

TAG_OPENING: dict[str, str] = {
    "default": "今日动线",
    "亲子游出行": "带娃的一天",
    "带长辈出行": "陪长辈的一天",
    "年轻情侣/朋友": "轻松结伴的一天",
    "大学生/年轻毕业生": "高能打卡的一天",
}


def _primary_tag(tags: list[str]) -> str:
    for t in tags:
        if t in TAG_OPENING:
            return t
    return "default"


def _play_nodes(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [n for n in timeline if n.get("type") == "玩"]


def _eat_nodes(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [n for n in timeline if n.get("type") == "吃"]


def _poi_highlight(play: dict[str, Any], destination: str) -> str:
    name = str(play.get("name") or "今日景点")
    if name in POI_ADVICE:
        return POI_ADVICE[name]["highlight"]
    tier = str(play.get("tier") or "中级")
    template = TIER_FALLBACK.get(tier, TIER_FALLBACK["中级"])
    return template.format(name=name, destination=destination)


def _poi_caution(play: dict[str, Any]) -> str | None:
    name = str(play.get("name") or "")
    if name in POI_ADVICE:
        return POI_ADVICE[name]["caution"]
    tier = str(play.get("tier") or "中级")
    if tier in ("特级", "高级"):
        return f"{name}步行量偏大，中间找阴凉处歇 15 分钟再出发。"
    return None


def _meal_sentence(eat: dict[str, Any]) -> str | None:
    cuisine = str(eat.get("cuisine") or eat.get("cuisine_type") or "")
    for key, tip in MEAL_NOTE.items():
        if key in cuisine or key in str(eat.get("name") or ""):
            return f"用餐安排在「{eat['name']}」，{tip}"
    name = eat.get("name")
    if name:
        return f"中午/晚上可在「{name}」解决一餐，错峰入座更从容。"
    return None


# 缺陷判定阈值（基于真实车程分钟 / 单段公里 / 折返几何）
LONG_TRANSFER_KM = 40.0   # 单段 >= 40km 视为跨城一日游
HEAVY_TRAN_MIN = 150.0    # 市内通勤总分钟达到此值才算「通勤偏多」
RELAX_RATIO = 0.70
DEDUP_PENALTY = 60.0      # 同一规则跨天重复时的降权，促使各天缺陷/亮点不同


def _earth_km(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    import math

    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _day_geometry(timeline: list[dict[str, Any]]) -> dict[str, float | bool]:
    """从当天 timeline 提取动线几何：最长单段、总里程、车程分钟、跨度、是否折返。"""
    legs: list[float] = []
    minutes = 0.0
    pts: list[tuple[float, float]] = []
    for n in timeline:
        leg = n.get("leg_distance_km")
        if leg is not None:
            legs.append(float(leg))
        minutes += float(n.get("tran_minutes") or 0)
        lng, lat = n.get("lng"), n.get("lat")
        if lng is not None and lat is not None:
            pts.append((float(lng), float(lat)))

    max_leg = max(legs) if legs else 0.0
    sum_legs = sum(legs)
    span = 0.0
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            span = max(span, _earth_km(pts[i][0], pts[i][1], pts[j][0], pts[j][1]))
    # 实走里程明显大于首尾跨度 → 中途折返绕路
    backtrack = (
        len(pts) >= 3
        and span > 1.0
        and sum_legs > span * 1.7
        and (sum_legs - span) > 4.0
    )
    return {
        "max_leg": max_leg,
        "sum_legs": sum_legs,
        "minutes": minutes,
        "span": span,
        "backtrack": backtrack,
    }


def _candidate_cons(
    geo: dict[str, Any],
    day: PlanDayMetrics,
    metrics: PlanMetrics,
    lead_play: dict[str, Any] | None,
) -> list[tuple[float, dict[str, Any]]]:
    """生成当天所有可能的缺陷候选 (分数, 文案)，分数越高越该提醒。"""
    cands: list[tuple[float, dict[str, Any]]] = []
    low = has_low_stamina_tag(metrics.tags)
    fatigue_max = metrics.fatigue_max or 100.0
    name = str((lead_play or {}).get("name") or "今日景点")
    max_leg = float(geo["max_leg"])
    minutes = float(geo["minutes"])

    if max_leg >= LONG_TRANSFER_KM:
        km = int(round(max_leg))
        cands.append((
            120.0 + max_leg + (25.0 if low else 0.0),
            {
                "rule_key": "long_transfer",
                "category": "con",
                "standard_text": CON_COPY["long_transfer"].format(km=km),
                "preset_tip": CON_TIPS["long_transfer"],
            },
        ))

    if low and _attract_ratio(day) >= 0.45:
        cands.append((
            85.0,
            {
                "rule_key": "heavy_attract",
                "category": "con",
                "standard_text": f"【{name}耗能偏高】：{CON_COPY['heavy_attract'].split('】：', 1)[-1]}",
                "preset_tip": CON_TIPS["heavy_attract"],
            },
        ))

    # 折返只在「无跨城长段」时才提醒：有长段时主问题是跨城车程，折返只是噪声
    if bool(geo["backtrack"]) and max_leg < LONG_TRANSFER_KM:
        extra = float(geo["sum_legs"]) - float(geo["span"])
        cands.append((
            75.0 + min(extra, 15.0),
            {
                "rule_key": "backtrack",
                "category": "con",
                "standard_text": CON_COPY["backtrack"],
                "preset_tip": CON_TIPS["backtrack"],
            },
        ))

    if minutes >= HEAVY_TRAN_MIN and max_leg < LONG_TRANSFER_KM:
        cands.append((
            65.0 + (minutes - HEAVY_TRAN_MIN) / 3.0,
            {
                "rule_key": "heavy_tran",
                "category": "con",
                "standard_text": CON_COPY["heavy_tran"],
                "preset_tip": CON_TIPS["heavy_tran"],
            },
        ))

    if day.fatigue_index > fatigue_max:
        cands.append((
            55.0 + (day.fatigue_index - fatigue_max) / 5.0,
            {
                "rule_key": "fatigue_over",
                "category": "con",
                "standard_text": CON_COPY["fatigue_over"],
                "preset_tip": CON_TIPS["fatigue_over"],
            },
        ))

    for poi in day.must_visit_pois:
        if poi.is_must_visit and poi.matching_score < 60:
            cands.append((
                45.0,
                {
                    "rule_key": "low_matching_must",
                    "category": "con",
                    "standard_text": CON_COPY["low_matching_must"],
                    "preset_tip": CON_TIPS["low_matching_must"],
                },
            ))
            break

    return cands


def _candidate_pros(
    geo: dict[str, Any],
    day: PlanDayMetrics,
    metrics: PlanMetrics,
    lead_play: dict[str, Any] | None,
) -> list[tuple[float, str, str]]:
    """生成当天亮点候选 (分数, rule_key, 头衔短句)。"""
    cands: list[tuple[float, str, str]] = []
    fatigue_max = metrics.fatigue_max or 100.0
    name = str((lead_play or {}).get("name") or "")
    tier = str((lead_play or {}).get("tier") or "")
    max_leg = float(geo["max_leg"])

    if max_leg <= 8.0 and not bool(geo["backtrack"]) and float(geo["span"]) <= 12.0:
        cands.append((80.0, "well_clustered", "【顺路不绕】今日各点都在同一片区，几乎没有回头路，时间都留给玩。"))

    if name and name in POI_ADVICE:
        hl = POI_ADVICE[name]["highlight"]
        if any(k in hl for k in ("傍晚", "夜景", "灯", "日落", "蓝调")):
            cands.append((70.0, "golden_hour", f"【黄昏机位】「{name}」临近傍晚最出片，记得卡好日落时段。"))

    if name and tier in ("特级", "高级"):
        cands.append((62.0, "signature_anchor", f"【主场拉满】「{name}」是今天的重头戏，值得多留点时间慢慢逛。"))

    if day.fatigue_index <= fatigue_max * RELAX_RATIO:
        cands.append((55.0, "relaxed_pace", "【高电量松弛】今日整体能耗压得低，逛完还有余力。"))

    return cands


def _pick_best(
    cands: list[tuple[float, dict[str, Any]]],
    used: dict[str, int],
) -> dict[str, Any] | None:
    """按分数选最该提醒的一条；跨天已用过的规则降权，促成各天差异。"""
    if not cands:
        return None
    best_item: dict[str, Any] | None = None
    best_adj = float("-inf")
    for score, item in cands:
        adj = score - used.get(item["rule_key"], 0) * DEDUP_PENALTY
        if adj > best_adj:
            best_adj = adj
            best_item = item
    if best_item is not None:
        used[best_item["rule_key"]] = used.get(best_item["rule_key"], 0) + 1
    return best_item


def build_day_diagnosis(
    *,
    day_index: int,
    total_days: int,
    destination: str,
    tags: list[str],
    anchor: str,
    timeline: list[dict[str, Any]],
    day_metrics: PlanDayMetrics,
    metrics: PlanMetrics,
    state: dict[str, dict[str, int]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """生成单日 pros/cons，文案绑定当天 timeline POI，并跨天去重。"""
    used_cons = (state or {}).get("cons", {})
    used_pros = (state or {}).get("pros", {})

    plays = _play_nodes(timeline)
    eats = _eat_nodes(timeline)
    tag_key = _primary_tag(tags)
    opening = TAG_OPENING.get(tag_key, TAG_OPENING["default"])

    if not timeline:
        return {
            "pros": [
                {
                    "rule_key": "empty_day",
                    "category": "pro",
                    "standard_text": "【行程待补充】：当天动线仍在优化，可先按整体节奏预留弹性时间。",
                }
            ],
            "cons": [],
        }

    lead_play = plays[0] if plays else None
    second_play = plays[1] if len(plays) > 1 else None
    lead_name = lead_play["name"] if lead_play else timeline[0]["name"]
    geo = _day_geometry(timeline)

    parts: list[str] = []

    # 亮点头衔：从真实信号里挑一条，跨天不同
    pro_cands = _candidate_pros(geo, day_metrics, metrics, lead_play)
    headline = ""
    if pro_cands:
        best_adj = float("-inf")
        best_key = ""
        for score, key, text in pro_cands:
            adj = score - used_pros.get(key, 0) * DEDUP_PENALTY
            if adj > best_adj:
                best_adj, best_key, headline = adj, key, text
        if best_key:
            used_pros[best_key] = used_pros.get(best_key, 0) + 1
    if headline:
        parts.append(headline)

    if day_index == 1:
        parts.append(f"【{opening}·序章】从「{lead_name}」拉开{destination}行程，先熟悉动线再加速。")
    elif day_index == total_days:
        parts.append(f"【{opening}·收官】「{lead_name}」适合作为最后一站的记忆点，别排太满。")
    else:
        parts.append(f"【{opening}·第 {day_index} 天】核心放在「{lead_name}」。")

    if lead_play:
        parts.append(_poi_highlight(lead_play, destination))
    if second_play:
        parts.append(f"下午可衔接「{second_play['name']}」，与上午风格形成互补。")

    if eats:
        meal = _meal_sentence(eats[0])
        if meal:
            parts.append(meal)

    if has_hardcore_tag(tags) and lead_play and str(lead_play.get("tier")) == "特级":
        parts.append("今日强度不低，但动线已尽量顺路，适合你们这种爱走满的玩法。")
    elif has_low_stamina_tag(tags):
        parts.append("整体节奏已偏松，随时可在餐厅或酒店附近临时减点。")

    pro_text = " ".join(parts)
    pros = [{"rule_key": "day_poi_highlight", "category": "pro", "standard_text": pro_text}]

    # 缺陷：候选打分 + 跨天去重选最相关一条
    con_cands = _candidate_cons(geo, day_metrics, metrics, lead_play)
    best_con = _pick_best(con_cands, used_cons)
    cons = [best_con] if best_con else []

    # 无硬伤的一天不硬凑，回退成与 pro 不同角度的轻提醒
    if not cons and lead_play:
        soft = _poi_caution(lead_play)
        if soft:
            cons = [
                {
                    "rule_key": "poi_soft_tip",
                    "category": "con",
                    "standard_text": f"【{lead_name}小提示】：{soft}",
                    "preset_tip": "随身带水与湿巾，比临时找便利店省心。",
                }
            ]

    return {"pros": pros[:1], "cons": cons[:1]}


def attach_day_diagnoses(
    day_plans: list[dict[str, Any]],
    metrics: PlanMetrics,
) -> None:
    """就地写入每日 pros/cons（按当天 POI 生成，跨天去重避免千篇一律）。"""
    day_metric_map = {d.day_index: d for d in metrics.day_metrics}
    state: dict[str, dict[str, int]] = {"cons": {}, "pros": {}}

    for day in sorted(day_plans, key=lambda d: d["day_index"]):
        idx = day["day_index"]
        dm = day_metric_map.get(idx)
        if not dm:
            continue
        block = build_day_diagnosis(
            day_index=idx,
            total_days=metrics.days,
            destination=metrics.destination,
            tags=metrics.tags,
            anchor=metrics.anchor,
            timeline=day.get("timeline") or [],
            day_metrics=dm,
            metrics=metrics,
            state=state,
        )
        day["pros"] = block["pros"]
        day["cons"] = block["cons"]
