# -*- coding: utf-8 -*-
"""
操作系统字体白名单与通用字体族映射规范 (Font Enumeration & Text Metrics Defense)
用于从 Chromium / Blink 内核层拦截并消除跨系统字体探测泄露，实现真实系统的字体特征对齐。
"""

from typing import Dict, Any, List

MAC_FONT_ALLOWLIST: List[str] = [
    "Academy Engraved LET", "Al Bayan", "Al Nile", "Al Tarikh", "American Typewriter",
    "Andale Mono", "Apple Braille", "Apple Chancery", "Apple Color Emoji", "Apple SD Gothic Neo",
    "Apple Symbols", "AppleGothic", "AppleMyungjo", "Arial", "Arial Black",
    "Arial Hebrew", "Arial Hebrew Scholar", "Arial Narrow", "Arial Rounded MT Bold", "Arial Unicode MS",
    "Avenir", "Avenir Next", "Avenir Next Condensed", "Ayuthaya", "Baghdad",
    "Bangla MN", "Bangla Sangam MN", "Baskerville", "Beirut", "Big Caslon",
    "Bodoni 72", "Bodoni 72 Oldstyle", "Bodoni 72 Smallcaps", "Bodoni Ornaments", "Bradley Hand",
    "Brush Script MT", "Chalkboard", "Chalkboard SE", "Chalkduster", "Charter",
    "Cochin", "Comic Sans MS", "Copperplate", "Corsiva Hebrew", "Courier New",
    "DIN Alternate", "DIN Condensed", "Damascus", "DecoType Naskh", "Devanagari MT",
    "Devanagari Sangam MN", "Didot", "Diwan Kufi", "Diwan Thuluth", "Euphemia UCAS",
    "Farah", "Farisi", "Futura", "GB18030 Bitmap", "Galvji",
    "Geeza Pro", "Geneva", "Georgia", "Gill Sans", "Grantha Sangam MN",
    "Gujarati MT", "Gujarati Sangam MN", "Gurmukhi MN", "Gurmukhi MT", "Gurmukhi Sangam MN",
    "Heiti SC", "Heiti TC", "Helvetica", "Helvetica Neue", "Herculanum",
    "Hiragino Maru Gothic ProN", "Hiragino Mincho ProN", "Hiragino Sans", "Hiragino Sans GB", "Hoefler Text",
    "ITF Devanagari", "ITF Devanagari Marathi", "Impact", "InaiMathi", "Kailasa",
    "Kannada MN", "Kannada Sangam MN", "Kefa III", "Khmer MN", "Khmer Sangam MN",
    "Kohinoor Bangla", "Kohinoor Devanagari", "Kohinoor Gujarati", "Kohinoor Telugu", "Kokonor",
    "Krungthep", "KufiStandardGK", "Lao MN", "Lao Sangam MN", "Lucida Grande",
    "Luminari", "Malayalam MN", "Malayalam Sangam MN", "Marker Felt", "Menlo",
    "Microsoft Sans Serif", "Mishafi", "Mishafi Gold", "Monaco", "Mshtakan",
    "Mukta Mahee", "Muna", "Myanmar MN", "Myanmar Sangam MN", "Nadeem",
    "Nanum Gothic", "Nanum Myeongjo", "New Peninim MT", "Noteworthy", "Noto Nastaliq Urdu",
    "Noto Sans Batak", "Noto Sans Kannada", "Noto Sans Myanmar", "Noto Sans NKo", "Noto Sans Oriya",
    "Noto Sans Syriac", "Noto Sans Tagalog", "Noto Serif Myanmar", "Optima", "Oriya MN",
    "Oriya Sangam MN", "Osaka", "PT Mono", "PT Sans", "PT Sans Caption",
    "PT Sans Narrow", "PT Serif", "PT Serif Caption", "Palatino", "Papyrus",
    "Party LET", "Phosphate", "PingFang HK", "PingFang MO", "PingFang SC",
    "PingFang TC", "Plantagenet Cherokee", "Raanana", "Rockwell", "STFangsong",
    "STIX Two Math", "STIX Two Text", "STSong", "Sana", "Sathu",
    "Savoye LET", "Shree Devanagari 714", "SignPainter", "Silom", "Sinhala MN",
    "Sinhala Sangam MN", "Skia", "Snell Roundhand", "Songti SC", "Songti TC",
    "Sukhumvit Set", "Symbol", "Tahoma", "Tamil MN", "Tamil Sangam MN",
    "Telugu MN", "Telugu Sangam MN", "Thonburi", "Times New Roman", "Trattatello",
    "Trebuchet MS", "Verdana", "Waseem", "Webdings", "Wingdings",
    "Wingdings 2", "Wingdings 3", "Zapf Dingbats", "Zapfino"
]

WIN_FONT_ALLOWLIST: List[str] = [
    "Arial", "Arial Black", "Bahnschrift", "Calibri", "Calibri Light",
    "Cambria", "Cambria Math", "Candara", "Comic Sans MS", "Consolas",
    "Constantia", "Corbel", "Corbel Light", "Courier New", "Ebrima",
    "Franklin Gothic Medium", "Gabriola", "Gadugi", "Georgia", "Impact",
    "Ink Free", "Javanese Text", "Leelawadee UI", "Leelawadee UI Semilight", "Lucida Console",
    "Lucida Sans Unicode", "MS Gothic", "MS PGothic", "MS UI Gothic", "MV Boli",
    "Malgun Gothic", "Malgun Gothic Semilight", "Marlett", "Microsoft Himalaya", "Microsoft JhengHei",
    "Microsoft JhengHei Light", "Microsoft JhengHei UI", "Microsoft JhengHei UI Light", "Microsoft New Tai Lue", "Microsoft PhagsPa",
    "Microsoft Sans Serif", "Microsoft Tai Le", "Microsoft YaHei", "Microsoft YaHei Light", "Microsoft YaHei UI",
    "Microsoft YaHei UI Light", "Microsoft Yi Baiti", "MingLiU-ExtB", "MingLiU_HKSCS-ExtB", "Mongolian Baiti",
    "Myanmar Text", "NSimSun", "Nirmala UI", "Nirmala UI Semilight", "PMingLiU-ExtB",
    "Palatino Linotype", "Sans Serif Collection", "Segoe Fluent Icons", "Segoe MDL2 Assets", "Segoe Print",
    "Segoe Script", "Segoe UI", "Segoe UI Black", "Segoe UI Emoji", "Segoe UI Historic",
    "Segoe UI Light", "Segoe UI Semibold", "Segoe UI Semilight", "Segoe UI Symbol", "Segoe UI Variable Display",
    "Segoe UI Variable Small", "Segoe UI Variable Text", "SimSun", "SimSun-ExtB", "SimSun-ExtG",
    "Sitka Banner", "Sitka Display", "Sitka Heading", "Sitka Small", "Sitka Subheading",
    "Sitka Text", "Sylfaen", "Symbol", "Tahoma", "Times New Roman",
    "Trebuchet MS", "Verdana", "Webdings", "Wingdings", "Yu Gothic",
    "Yu Gothic Light", "Yu Gothic Medium", "Yu Gothic UI", "Yu Gothic UI Light", "Yu Gothic UI Semibold",
    "Yu Gothic UI Semilight"
]

LINUX_FONT_ALLOWLIST: List[str] = [
    "Arial", "Courier", "Courier New", "DejaVu Sans", "DejaVu Sans Mono",
    "DejaVu Serif", "Helvetica", "Liberation Mono", "Liberation Sans",
    "Liberation Serif", "Noto Sans", "Noto Serif", "Times New Roman", "Ubuntu",
    "Ubuntu Condensed", "Ubuntu Mono", "Cantarell"
]

GENERIC_FAMILY_MAPS: Dict[str, Dict[str, str]] = {
    "macos": {
        "cursive": "Apple Chancery",
        "fantasy": "Papyrus",
        "monospace": "Menlo",
        "sans-serif": "Helvetica",
        "serif": "Times"
    },
    "windows": {
        "cursive": "Comic Sans MS",
        "fantasy": "Impact",
        "monospace": "Consolas",
        "sans-serif": "Arial",
        "serif": "Times New Roman"
    },
    "linux": {
        "cursive": "Comic Neue",
        "fantasy": "Impact",
        "monospace": "DejaVu Sans Mono",
        "sans-serif": "DejaVu Sans",
        "serif": "DejaVu Serif"
    }
}


def get_font_profile(os_platform: str) -> Dict[str, Any]:
    """根据操作系统生成对应的字体过滤规则与通用字体映射"""
    key = (os_platform or "windows").lower()
    if "mac" in key or "ios" in key:
        return {
            "generic_family_map": GENERIC_FAMILY_MAPS["macos"],
            "enumeration_allowlist": MAC_FONT_ALLOWLIST
        }
    elif "linux" in key or "android" in key:
        return {
            "generic_family_map": GENERIC_FAMILY_MAPS["linux"],
            "enumeration_allowlist": LINUX_FONT_ALLOWLIST
        }
    else:
        return {
            "generic_family_map": GENERIC_FAMILY_MAPS["windows"],
            "enumeration_allowlist": WIN_FONT_ALLOWLIST
        }
