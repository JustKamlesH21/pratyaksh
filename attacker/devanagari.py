"""Write Whisper Phrase words in Devanagari, the script IndicF5 reads.

IndicF5 is trained on Indic-script text: given Latin "park alli four baje interview" it made
0.5 s of noise (Task Match 0/10 on Oct 27), given "पार्क अल्ली फोर बजे इंटरव्यू" it said the
phrase clearly (10/10). The Whisper Phrase vocabulary is fixed (src/pratyaksh/phrases.py),
so a lexicon covers it exactly. Unknown words and words already in an Indic script pass through.
"""

from __future__ import annotations

LEXICON: dict[str, str] = {
    # Kannada and Hindi words in the templates and slots
    "aaytu": "आयतु", "akki": "अक्कि", "alli": "अल्ली", "aloo": "आलू", "baar": "बार", "baje": "बजे",
    "baruttene": "बरुत्तेने", "bele": "बेले", "beligge": "बेलिग्गे", "chai": "चाय", "dosa": "दोसा",
    "eerulli": "ईरुल्ली", "gante": "गंटे", "ge": "गे", "hai": "है", "hannu": "हन्नु", "idli": "इडली",
    "ivattu": "इवत्तु", "kilo": "किलो", "kobari": "कोबरी", "lao": "लाओ", "mane": "मने", "mein": "में",
    "naale": "नाले", "naanu": "नानु", "oota": "ऊटा", "ratri": "रात्रि", "sakkare": "सक्करे",
    "sanje": "संजे", "upma": "उपमा", "vada": "वड़ा", "biryani": "बिरयानी",
    # per-language phrase banks (Oct 27): Hindi, and Kannada written in Devanagari
    "aaj": "आज", "kal": "कल", "subah": "सुबह", "shaam": "शाम", "raat": "रात", "ghar": "घर",
    "cheeni": "चीनी", "chawal": "चावल", "pyaaz": "प्याज़", "tamatar": "टमाटर", "daal": "दाल", "atta": "आटा",
    "sabzi": "सब्ज़ी", "mehmaan": "मेहमान", "dost": "दोस्त", "bachche": "बच्चे", "padosi": "पड़ोसी",
    "rishtedaar": "रिश्तेदार", "khana": "खाना", "paratha": "पराठा", "samosa": "समोसा", "poha": "पोहा",
    "gantege": "गंटेगे", "beku": "बेकु", "maneli": "मनेली", "nimishadalli": "निमिषदल्ली",
    "hain": "हैं", "ghante": "घंटे", "pahunchna": "पहुँचना", "ide": "इदे", "tagondu": "तगोंडु", "baa": "बा",
    "iddare": "इद्दारे", "banni": "बन्नी", "are": "आर", "coming": "कमिंग", "home": "होम", "is": "इज़",
    "today": "टुडे", "tonight": "टुनाइट", "tomorrow": "टुमॉरो",
    # digits as Hindi and Kannada Customers are asked to say them (phrases.speakable)
    "do": "दो", "teen": "तीन", "chaar": "चार", "paanch": "पाँच", "chhah": "छह", "saat": "सात", "aath": "आठ",
    "nau": "नौ", "eradu": "एरडु", "mooru": "मूरु", "naalku": "नाल्कु", "aidu": "ऐदु", "aaru": "आरु", "elu": "एळु",
    "entu": "एंटु", "ombattu": "ओंबत्तु",
    # English words, spelt as an Indian speaker says them
    "alarm": "अलार्म", "auto": "ऑटो", "bell": "बेल", "bus": "बस", "cab": "कैब", "class": "क्लास",
    "coffee": "कॉफ़ी", "college": "कॉलेज", "cousins": "कज़िन्स", "dinner": "डिनर", "flight": "फ्लाइट",
    "friday": "फ्राइडे", "friends": "फ्रेंड्स", "function": "फंक्शन", "guests": "गेस्ट्स",
    "hospital": "हॉस्पिटल", "hotel": "होटल", "interview": "इंटरव्यू", "late": "लेट", "lunch": "लंच",
    "match": "मैच", "meeting": "मीटिंग", "metro": "मेट्रो", "minute": "मिनट", "mobile": "मोबाइल",
    "monday": "मंडे", "neighbours": "नेबर्स", "office": "ऑफिस", "park": "पार्क", "party": "पार्टी",
    "phone": "फ़ोन", "ready": "रेडी", "relatives": "रिलेटिव्स", "ring": "रिंग", "school": "स्कूल",
    "station": "स्टेशन", "students": "स्टूडेंट्स", "sunday": "संडे", "temple": "टेम्पल",
    "tomato": "टोमैटो", "train": "ट्रेन",
    "tuesday": "ट्यूज़डे", "wednesday": "वेडनेसडे", "thursday": "थर्सडे", "saturday": "सैटरडे", "tea": "टी",
    "pizza": "पिज़्ज़ा", "soup": "सूप", "rice": "राइस", "sugar": "शुगर", "onions": "अनियन्स",
    "tomatoes": "टमाटोज़", "potatoes": "पोटैटोज़", "apples": "ऐपल्स", "bananas": "बनानाज़", "flour": "फ्लोर",
    "doorbell": "डोरबेल", "kilos": "किलोज़", "of": "ऑफ़", "in": "इन", "by": "बाय", "at": "ऐट", "the": "द",
    "on": "ऑन", "hours": "आवर्स", "times": "टाइम्स", "minutes": "मिनट्स", "bring": "ब्रिंग", "rang": "रैंग",
    # digit names (phrases.speakable says digits in English)
    "zero": "ज़ीरो", "one": "वन", "two": "टू", "three": "थ्री", "four": "फोर", "five": "फाइव",
    "six": "सिक्स", "seven": "सेवन", "eight": "एट", "nine": "नाइन",
}


def to_devanagari(text: str) -> str:
    """Each word found in LEXICON (case-insensitive) in Devanagari; every other word unchanged."""
    return " ".join(LEXICON.get(w.lower(), w) for w in text.split())
