from __future__ import annotations


PRODUCT_KEYWORD_TRANSLATIONS = {
    "手机": "手机",
    "智能手机": "手机",
    "电话": "手机",
    "iphone": "iPhone",
    "华为": "华为",
    "小米": "小米",
    "oppo": "OPPO",
    "vivo": "vivo",
    "电脑": "电脑",
    "笔记本": "笔记本",
    "笔记本电脑": "笔记本",
    "macbook": "MacBook",
    "thinkpad": "ThinkPad",
    "耳机": "耳机",
    "airpods": "AirPods",
    "索尼": "索尼",
    "头戴耳机": "耳机",
    "运动鞋": "运动鞋",
    "运动": "运动鞋",
    "跑鞋": "运动鞋",
    "鞋": "运动鞋",
    "冲锋衣": "冲锋衣",
    "羽绒服": "羽绒服",
    "水壶": "水壶",
    "电水壶": "水壶",
    "杯子": "杯子",
    "马克杯": "马克杯",
    "t恤": "T恤",
    "体恤": "T恤",
    "哑铃": "哑铃",
    "健身": "健身",
    "瑜伽垫": "瑜伽垫",
    "书": "书",
    "键盘": "键盘",
    "鼠标": "鼠标",
    "相机": "相机",
    "手表": "手表",
}


def translate_product_keyword(keyword: str | None) -> str:
    if not keyword:
        return ""
    text = keyword.strip()
    lowered = text.lower()
    for chinese, english in PRODUCT_KEYWORD_TRANSLATIONS.items():
        if chinese.lower() in lowered:
            return english
    return lowered


def extract_product_keyword(text: str) -> str:
    lowered = text.lower()
    for chinese, english in PRODUCT_KEYWORD_TRANSLATIONS.items():
        if chinese.lower() in lowered:
            return english
    for english in sorted(set(PRODUCT_KEYWORD_TRANSLATIONS.values()), key=len, reverse=True):
        if english.lower() in lowered:
            return english
    return ""
