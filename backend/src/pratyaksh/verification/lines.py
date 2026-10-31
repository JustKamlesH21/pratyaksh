"""in_language: what the Voice Agent says, in the Customer's language.

The Verifier composes every line in English from short sentences; Verifier._set_step turns the finished line
into the Customer's language here, sentence by sentence, so a new lead-in needs no new wiring and no second
copy of a flow. A sentence not in the table passes through: a Whisper Phrase is already in its own script, and
answers (knowledge.yaml, the LLM) are already in the language the Caller asked in.

Keep the English keys equal to the sentences in verifier.py: test_lines fails on any line left untranslated.
Written for the Oct 31 finale and not yet read by a native speaker (docs/DESIGN.md asks for that). Hindi says
"मैं" as a man (the Hindi voice is Aman). Latin words the voice says well (payee, SIM) stay Latin.
"""

from __future__ import annotations

from ..voice import _sentences

_NUMBERS = {
    "hi": {1: "एक छोटी बात", 2: "दो छोटी बातें", 3: "तीन छोटी बातें"},
    "kn": {1: "ಒಂದು ಚಿಕ್ಕ ವಿಷಯವನ್ನು", 2: "ಎರಡು ಚಿಕ್ಕ ವಿಷಯಗಳನ್ನು", 3: "ಮೂರು ಚಿಕ್ಕ ವಿಷಯಗಳನ್ನು"},
}

_LINES: dict[str, dict[str, str]] = {
    # Greeting and getting the Request
    "Namaskara, you have reached your bank's secure line.": {
        "hi": "नमस्ते, आप अपने बैंक की सुरक्षित लाइन पर हैं।",
        "kn": "ನಮಸ್ಕಾರ, ನೀವು ನಿಮ್ಮ ಬ್ಯಾಂಕಿನ ಸುರಕ್ಷಿತ ಲೈನ್‌ಗೆ ಕರೆ ಮಾಡಿದ್ದೀರಿ.",
    },
    "You can ask to check your balance, add a payee, change your SIM or password, or transfer money.": {
        "hi": "आप बैलेंस देख सकते हैं, नया payee जोड़ सकते हैं, SIM या पासवर्ड बदल सकते हैं, या पैसे ट्रांसफ़र कर सकते हैं।",
        "kn": "ನೀವು ಬ್ಯಾಲೆನ್ಸ್ ನೋಡಬಹುದು, ಹೊಸ payee ಸೇರಿಸಬಹುದು, SIM ಅಥವಾ ಪಾಸ್‌ವರ್ಡ್ ಬದಲಾಯಿಸಬಹುದು, ಅಥವಾ ಹಣ ವರ್ಗಾಯಿಸಬಹುದು.",
    },
    "How can I help you today?": {"hi": "आज मैं आपकी कैसे मदद कर सकता हूँ?", "kn": "ಇಂದು ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?"},
    "Sorry, I didn't catch that.": {"hi": "माफ़ कीजिए, मैं समझ नहीं पाया।", "kn": "ಕ್ಷಮಿಸಿ, ನನಗೆ ಅರ್ಥವಾಗಲಿಲ್ಲ."},
    "You can ask me a question, or ask to check your balance, add a payee, change your SIM or password, "
    "transfer money, or make another change to your account.": {
        "hi": "आप मुझसे कोई सवाल पूछ सकते हैं, या बैलेंस देखने, नया payee जोड़ने, SIM या पासवर्ड बदलने, पैसे ट्रांसफ़र करने, "
              "या खाते में कोई और बदलाव करने के लिए कह सकते हैं।",
        "kn": "ನೀವು ನನಗೆ ಪ್ರಶ್ನೆ ಕೇಳಬಹುದು, ಅಥವಾ ಬ್ಯಾಲೆನ್ಸ್ ನೋಡಲು, ಹೊಸ payee ಸೇರಿಸಲು, SIM ಅಥವಾ ಪಾಸ್‌ವರ್ಡ್ ಬದಲಾಯಿಸಲು, "
              "ಹಣ ವರ್ಗಾಯಿಸಲು, ಅಥವಾ ಖಾತೆಯಲ್ಲಿ ಬೇರೆ ಬದಲಾವಣೆ ಮಾಡಲು ಕೇಳಬಹುದು.",
    },
    "Sure, I can send it to your bank app.": {
        "hi": "ज़रूर, मैं इसे आपके बैंक ऐप पर भेज सकता हूँ।", "kn": "ಖಂಡಿತ, ಅದನ್ನು ನಿಮ್ಮ ಬ್ಯಾಂಕ್ ಆ್ಯಪ್‌ಗೆ ಕಳುಹಿಸಬಹುದು.",
    },
    "Which request is it: a payee, a SIM or password change, a transfer, or another account change?": {
        "hi": "कौन-सा अनुरोध है: payee, SIM या पासवर्ड बदलना, ट्रांसफ़र, या खाते का कोई और बदलाव?",
        "kn": "ಯಾವ ವಿನಂತಿ: payee, SIM ಅಥವಾ ಪಾಸ್‌ವರ್ಡ್ ಬದಲಾವಣೆ, ಹಣ ವರ್ಗಾವಣೆ, ಅಥವಾ ಖಾತೆಯ ಬೇರೆ ಬದಲಾವಣೆ?",
    },
    # The Request understood
    "Sure, I can help you check your balance.": {
        "hi": "ज़रूर, मैं बैलेंस देखने में आपकी मदद कर सकता हूँ।", "kn": "ಖಂಡಿತ, ಬ್ಯಾಲೆನ್ಸ್ ನೋಡಲು ನಾನು ಸಹಾಯ ಮಾಡಬಲ್ಲೆ.",
    },
    "Sure, I can help you add a new payee.": {
        "hi": "ज़रूर, मैं नया payee जोड़ने में आपकी मदद कर सकता हूँ।", "kn": "ಖಂಡಿತ, ಹೊಸ payee ಸೇರಿಸಲು ನಾನು ಸಹಾಯ ಮಾಡಬಲ್ಲೆ.",
    },
    "Sure, I can help you change your SIM or reset your password.": {
        "hi": "ज़रूर, मैं SIM बदलने या पासवर्ड रीसेट करने में आपकी मदद कर सकता हूँ।",
        "kn": "ಖಂಡಿತ, SIM ಬದಲಾಯಿಸಲು ಅಥವಾ ಪಾಸ್‌ವರ್ಡ್ ಮರುಹೊಂದಿಸಲು ನಾನು ಸಹಾಯ ಮಾಡಬಲ್ಲೆ.",
    },
    "Sure, I can help you make a high-value transfer.": {
        "hi": "ज़रूर, मैं बड़ी रकम ट्रांसफ़र करने में आपकी मदद कर सकता हूँ।",
        "kn": "ಖಂಡಿತ, ದೊಡ್ಡ ಮೊತ್ತದ ಹಣ ವರ್ಗಾಯಿಸಲು ನಾನು ಸಹಾಯ ಮಾಡಬಲ್ಲೆ.",
    },
    "Sure, I can help you make that change to your account.": {
        "hi": "ज़रूर, मैं आपके खाते में यह बदलाव करने में आपकी मदद कर सकता हूँ।",
        "kn": "ಖಂಡಿತ, ನಿಮ್ಮ ಖಾತೆಯಲ್ಲಿ ಆ ಬದಲಾವಣೆ ಮಾಡಲು ನಾನು ಸಹಾಯ ಮಾಡಬಲ್ಲೆ.",
    },
    "Your balance has been sent to the bank app on your registered phone.": {
        "hi": "आपका बैलेंस आपके रजिस्टर्ड फ़ोन के बैंक ऐप पर भेज दिया गया है।",
        "kn": "ನಿಮ್ಮ ಬ್ಯಾಲೆನ್ಸ್ ಅನ್ನು ನಿಮ್ಮ ನೋಂದಾಯಿತ ಫೋನಿನ ಬ್ಯಾಂಕ್ ಆ್ಯಪ್‌ಗೆ ಕಳುಹಿಸಲಾಗಿದೆ.",
    },
    "That's done.": {"hi": "हो गया।", "kn": "ಆಯಿತು."},
    # Challenges
    "Please whisper these words.": {"hi": "कृपया ये शब्द फुसफुसाकर बोलिए।", "kn": "ದಯವಿಟ್ಟು ಈ ಪದಗಳನ್ನು ಪಿಸುಗುಟ್ಟಿ ಹೇಳಿ."},
    "I've sent a six-digit code to the bank app on your registered phone.": {
        "hi": "मैंने आपके रजिस्टर्ड फ़ोन के बैंक ऐप पर छह अंकों का कोड भेजा है।",
        "kn": "ನಿಮ್ಮ ನೋಂದಾಯಿತ ಫೋನಿನ ಬ್ಯಾಂಕ್ ಆ್ಯಪ್‌ಗೆ ಆರು ಅಂಕಿಯ ಕೋಡ್ ಕಳುಹಿಸಿದ್ದೇನೆ.",
    },
    "Please read it out.": {"hi": "कृपया उसे पढ़कर सुनाइए।", "kn": "ದಯವಿಟ್ಟು ಅದನ್ನು ಓದಿ ಹೇಳಿ."},
    "When you're ready, please read out the six-digit code from your bank app.": {
        "hi": "जब तैयार हों, कृपया अपने बैंक ऐप से छह अंकों का कोड पढ़कर सुनाइए।",
        "kn": "ಸಿದ್ಧವಾದಾಗ, ದಯವಿಟ್ಟು ನಿಮ್ಮ ಬ್ಯಾಂಕ್ ಆ್ಯಪ್‌ನಲ್ಲಿರುವ ಆರು ಅಂಕಿಯ ಕೋಡ್ ಓದಿ ಹೇಳಿ.",
    },
    "That didn't match.": {"hi": "यह मेल नहीं खाया।", "kn": "ಅದು ಹೊಂದಿಕೆಯಾಗಲಿಲ್ಲ."},
    "Please read the six digits from your bank app again, slowly.": {
        "hi": "कृपया अपने बैंक ऐप से छह अंक फिर से, धीरे-धीरे पढ़िए।",
        "kn": "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಬ್ಯಾಂಕ್ ಆ್ಯಪ್‌ನ ಆರು ಅಂಕಿಗಳನ್ನು ಮತ್ತೆ ನಿಧಾನವಾಗಿ ಓದಿ.",
    },
    "That code had just expired, so I've sent a new one to your bank app.": {
        "hi": "वह कोड अभी-अभी समाप्त हो गया था, इसलिए मैंने आपके बैंक ऐप पर नया कोड भेजा है।",
        "kn": "ಆ ಕೋಡ್‌ನ ಅವಧಿ ಈಗಷ್ಟೇ ಮುಗಿಯಿತು, ಆದ್ದರಿಂದ ನಿಮ್ಮ ಬ್ಯಾಂಕ್ ಆ್ಯಪ್‌ಗೆ ಹೊಸ ಕೋಡ್ ಕಳುಹಿಸಿದ್ದೇನೆ.",
    },
    "Please read out the new six-digit code.": {
        "hi": "कृपया छह अंकों का नया कोड पढ़कर सुनाइए।", "kn": "ದಯವಿಟ್ಟು ಹೊಸ ಆರು ಅಂಕಿಯ ಕೋಡ್ ಓದಿ ಹೇಳಿ.",
    },
    "Thank you.": {"hi": "धन्यवाद।", "kn": "ಧನ್ಯವಾದಗಳು."},
    "I need one more check.": {"hi": "मुझे एक और जाँच करनी है।", "kn": "ನನಗೆ ಇನ್ನೊಂದು ಪರಿಶೀಲನೆ ಬೇಕು."},
    # Side turns
    "Sorry, I didn't hear you.": {"hi": "माफ़ कीजिए, मुझे आपकी आवाज़ नहीं सुनाई दी।", "kn": "ಕ್ಷಮಿಸಿ, ನಿಮ್ಮ ಧ್ವನಿ ಕೇಳಿಸಲಿಲ್ಲ."},
    "Sorry, I had trouble hearing that.": {"hi": "माफ़ कीजिए, मुझे ठीक से सुनाई नहीं दिया।", "kn": "ಕ್ಷಮಿಸಿ, ನನಗೆ ಸರಿಯಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ."},
    "Of course.": {"hi": "बिल्कुल।", "kn": "ಖಂಡಿತ."},
    "Sure.": {"hi": "ज़रूर।", "kn": "ಖಂಡಿತ."},
    "Is there anything else I can help you with?": {
        "hi": "क्या मैं आपकी और कोई मदद कर सकता हूँ?", "kn": "ನಾನು ನಿಮಗೆ ಇನ್ನೇನಾದರೂ ಸಹಾಯ ಮಾಡಬಹುದೇ?",
    },
    "Sure, take your time.": {"hi": "ज़रूर, आराम से।", "kn": "ಪರವಾಗಿಲ್ಲ, ನಿಧಾನವಾಗಿ ಮಾಡಿ."},
    "Tell me when you're ready.": {"hi": "जब तैयार हों, बता दीजिए।", "kn": "ಸಿದ್ಧವಾದಾಗ ಹೇಳಿ."},
    "One moment, please.": {"hi": "एक क्षण रुकिए।", "kn": "ಒಂದು ಕ್ಷಣ ಇರಿ."},
    # App Approval
    "I've sent an approval request to the bank app on your registered phone.": {
        "hi": "मैंने आपके रजिस्टर्ड फ़ोन के बैंक ऐप पर मंज़ूरी का अनुरोध भेजा है।",
        "kn": "ನಿಮ್ಮ ನೋಂದಾಯಿತ ಫೋನಿನ ಬ್ಯಾಂಕ್ ಆ್ಯಪ್‌ಗೆ ಅನುಮೋದನೆ ವಿನಂತಿ ಕಳುಹಿಸಿದ್ದೇನೆ.",
    },
    "Please approve it there.": {"hi": "कृपया वहाँ उसे मंज़ूर कीजिए।", "kn": "ದಯವಿಟ್ಟು ಅಲ್ಲಿ ಅದನ್ನು ಅನುಮೋದಿಸಿ."},
    "No problem.": {"hi": "कोई बात नहीं।", "kn": "ಪರವಾಗಿಲ್ಲ."},
    "That code expired again.": {"hi": "वह कोड फिर से समाप्त हो गया।", "kn": "ಆ ಕೋಡ್‌ನ ಅವಧಿ ಮತ್ತೆ ಮುಗಿಯಿತು."},
    "I need one more confirmation.": {"hi": "मुझे एक और पुष्टि चाहिए।", "kn": "ನನಗೆ ಇನ್ನೊಂದು ದೃಢೀಕರಣ ಬೇಕು."},
    "You asked to use the app.": {"hi": "आपने ऐप इस्तेमाल करने को कहा था।", "kn": "ನೀವು ಆ್ಯಪ್ ಬಳಸಲು ಕೇಳಿದ್ದೀರಿ."},
    "You approved this request in your bank app.": {
        "hi": "आपने अपने बैंक ऐप में यह अनुरोध मंज़ूर किया।", "kn": "ನಿಮ್ಮ ಬ್ಯಾಂಕ್ ಆ್ಯಪ್‌ನಲ್ಲಿ ನೀವು ಈ ವಿನಂತಿಯನ್ನು ಅನುಮೋದಿಸಿದ್ದೀರಿ.",
    },
    "You declined this request in your bank app, so it has been stopped.": {
        "hi": "आपने अपने बैंक ऐप में यह अनुरोध अस्वीकार किया, इसलिए इसे रोक दिया गया है।",
        "kn": "ನಿಮ್ಮ ಬ್ಯಾಂಕ್ ಆ್ಯಪ್‌ನಲ್ಲಿ ನೀವು ಈ ವಿನಂತಿಯನ್ನು ನಿರಾಕರಿಸಿದ್ದೀರಿ, ಆದ್ದರಿಂದ ಅದನ್ನು ನಿಲ್ಲಿಸಲಾಗಿದೆ.",
    },
    "The approval request expired.": {"hi": "मंज़ूरी का अनुरोध समाप्त हो गया।", "kn": "ಅನುಮೋದನೆ ವಿನಂತಿಯ ಅವಧಿ ಮುಗಿಯಿತು."},
    "For your safety nothing was changed.": {
        "hi": "आपकी सुरक्षा के लिए कुछ भी नहीं बदला गया।", "kn": "ನಿಮ್ಮ ಸುರಕ್ಷತೆಗಾಗಿ ಏನನ್ನೂ ಬದಲಾಯಿಸಿಲ್ಲ.",
    },
    # Endings
    "We could not verify this call, so for your safety the request has been stopped.": {
        "hi": "हम इस कॉल की पुष्टि नहीं कर सके, इसलिए आपकी सुरक्षा के लिए यह अनुरोध रोक दिया गया है।",
        "kn": "ಈ ಕರೆಯನ್ನು ಪರಿಶೀಲಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ, ಆದ್ದರಿಂದ ನಿಮ್ಮ ಸುರಕ್ಷತೆಗಾಗಿ ವಿನಂತಿಯನ್ನು ನಿಲ್ಲಿಸಲಾಗಿದೆ.",
    },
    "Please use the bank app or visit your branch.": {
        "hi": "कृपया बैंक ऐप इस्तेमाल कीजिए या अपनी शाखा में जाइए।", "kn": "ದಯವಿಟ್ಟು ಬ್ಯಾಂಕ್ ಆ್ಯಪ್ ಬಳಸಿ ಅಥವಾ ನಿಮ್ಮ ಶಾಖೆಗೆ ಭೇಟಿ ನೀಡಿ.",
    },
    "Goodbye.": {"hi": "नमस्कार।", "kn": "ನಮಸ್ಕಾರ."},
    "Thank you, you're verified and your request is done.": {
        "hi": "धन्यवाद, आपकी पुष्टि हो गई है और आपका अनुरोध पूरा हो गया है।",
        "kn": "ಧನ್ಯವಾದಗಳು, ನಿಮ್ಮ ಪರಿಶೀಲನೆ ಆಗಿದೆ ಮತ್ತು ನಿಮ್ಮ ವಿನಂತಿ ಪೂರ್ಣಗೊಂಡಿದೆ.",
    },
    "Thank you, you're verified.": {"hi": "धन्यवाद, आपकी पुष्टि हो गई है।", "kn": "ಧನ್ಯವಾದಗಳು, ನಿಮ್ಮ ಪರಿಶೀಲನೆ ಆಗಿದೆ."},
    "Because this is a high-value request, a bank officer will confirm it shortly.": {
        "hi": "यह बड़ी रकम का अनुरोध है, इसलिए बैंक अधिकारी जल्द ही इसकी पुष्टि करेंगे।",
        "kn": "ಇದು ದೊಡ್ಡ ಮೊತ್ತದ ವಿನಂತಿ, ಆದ್ದರಿಂದ ಬ್ಯಾಂಕ್ ಅಧಿಕಾರಿ ಶೀಘ್ರದಲ್ಲೇ ಇದನ್ನು ದೃಢೀಕರಿಸುತ್ತಾರೆ.",
    },
    "A bank officer will confirm it shortly.": {
        "hi": "बैंक अधिकारी जल्द ही इसकी पुष्टि करेंगे।", "kn": "ಬ್ಯಾಂಕ್ ಅಧಿಕಾರಿ ಶೀಘ್ರದಲ್ಲೇ ಇದನ್ನು ದೃಢೀಕರಿಸುತ್ತಾರೆ.",
    },
    "Your SIM change is approved.": {"hi": "आपका SIM बदलने का अनुरोध मंज़ूर हो गया है।", "kn": "ನಿಮ್ಮ SIM ಬದಲಾವಣೆ ಅನುಮೋದನೆಯಾಗಿದೆ."},
    "I've sent the next steps to your bank app.": {
        "hi": "मैंने आगे के कदम आपके बैंक ऐप पर भेज दिए हैं।", "kn": "ಮುಂದಿನ ಹಂತಗಳನ್ನು ನಿಮ್ಮ ಬ್ಯಾಂಕ್ ಆ್ಯಪ್‌ಗೆ ಕಳುಹಿಸಿದ್ದೇನೆ.",
    },
    "I've sent a password reset to your bank app.": {
        "hi": "मैंने पासवर्ड रीसेट आपके बैंक ऐप पर भेज दिया है।", "kn": "ಪಾಸ್‌ವರ್ಡ್ ಮರುಹೊಂದಿಸುವಿಕೆಯನ್ನು ನಿಮ್ಮ ಬ್ಯಾಂಕ್ ಆ್ಯಪ್‌ಗೆ ಕಳುಹಿಸಿದ್ದೇನೆ.",
    },
    "Please set your new password there within fifteen minutes.": {
        "hi": "कृपया पंद्रह मिनट के अंदर वहाँ अपना नया पासवर्ड बनाइए।", "kn": "ದಯವಿಟ್ಟು ಹದಿನೈದು ನಿಮಿಷಗಳಲ್ಲಿ ಅಲ್ಲಿ ಹೊಸ ಪಾಸ್‌ವರ್ಡ್ ಹೊಂದಿಸಿ.",
    },
    "Thank you for calling.": {"hi": "कॉल करने के लिए धन्यवाद।", "kn": "ಕರೆ ಮಾಡಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು."},
    # Hand-over
    "I'll connect you to a bank officer now.": {
        "hi": "मैं अभी आपको बैंक अधिकारी से जोड़ रहा हूँ।", "kn": "ನಾನು ಈಗ ನಿಮ್ಮನ್ನು ಬ್ಯಾಂಕ್ ಅಧಿಕಾರಿಗೆ ಸಂಪರ್ಕಿಸುತ್ತೇನೆ.",
    },
    "They will verify you again before making any change.": {
        "hi": "कोई भी बदलाव करने से पहले वे आपकी दोबारा पुष्टि करेंगे।",
        "kn": "ಯಾವುದೇ ಬದಲಾವಣೆ ಮಾಡುವ ಮೊದಲು ಅವರು ನಿಮ್ಮನ್ನು ಮತ್ತೆ ಪರಿಶೀಲಿಸುತ್ತಾರೆ.",
    },
    "Please stay on the line.": {"hi": "कृपया लाइन पर बने रहिए।", "kn": "ದಯವಿಟ್ಟು ಲೈನ್‌ನಲ್ಲಿ ಇರಿ."},
    "I'm having trouble on this line.": {"hi": "इस लाइन पर मुझे दिक़्क़त हो रही है।", "kn": "ಈ ಲೈನ್‌ನಲ್ಲಿ ನನಗೆ ತೊಂದರೆ ಆಗುತ್ತಿದೆ."},
    "I'm sorry, I couldn't understand.": {"hi": "माफ़ कीजिए, मैं समझ नहीं पाया।", "kn": "ಕ್ಷಮಿಸಿ, ನನಗೆ ಅರ್ಥವಾಗಲಿಲ್ಲ."},
    "You have a few questions, so I'll connect you to a bank officer now.": {
        "hi": "आपके कुछ सवाल हैं, इसलिए मैं अभी आपको बैंक अधिकारी से जोड़ रहा हूँ।",
        "kn": "ನಿಮಗೆ ಕೆಲವು ಪ್ರಶ್ನೆಗಳಿವೆ, ಆದ್ದರಿಂದ ನಾನು ಈಗ ನಿಮ್ಮನ್ನು ಬ್ಯಾಂಕ್ ಅಧಿಕಾರಿಗೆ ಸಂಪರ್ಕಿಸುತ್ತೇನೆ.",
    },
}

_THINGS = "For your security I'll ask you {} quick {}."
for _n, _noun in ((1, "thing"), (2, "things"), (3, "things")):
    _LINES[_THINGS.format(_n, _noun)] = {
        "hi": f"आपकी सुरक्षा के लिए मैं आपसे {_NUMBERS['hi'][_n]} पूछूँगा।",
        "kn": f"ನಿಮ್ಮ ಸುರಕ್ಷತೆಗಾಗಿ ನಾನು ನಿಮಗೆ {_NUMBERS['kn'][_n]} ಕೇಳುತ್ತೇನೆ.",
    }


def in_language(text: str, language: str | None) -> str:
    """`text` in `language`, one sentence at a time. English, or a language with no lines, passes through."""
    if language not in ("hi", "kn"):
        return text
    return " ".join(_LINES.get(sentence, {}).get(language, sentence) for sentence in _sentences(text))


def untranslated(text: str, language: str) -> list[str]:
    """The sentences of an English line that have no translation (test_lines)."""
    return [sentence for sentence in _sentences(text) if language not in _LINES.get(sentence, {})]
