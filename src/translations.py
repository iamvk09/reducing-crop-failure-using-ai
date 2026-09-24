"""Farmer-facing translations for the Streamlit dashboard.

Model features and dataset values remain in English; this module only changes how
they are presented to a person using the dashboard.
"""

LANGUAGES = {
    "English": "English",
    "Hindi": "हिन्दी",
    "Marathi": "मराठी",
    "Bengali": "বাংলা",
    "Telugu": "తెలుగు",
    "Tamil": "தமிழ்",
    "Kannada": "ಕನ್ನಡ",
    "Gujarati": "ગુજરાતી",
}

TEXT = {
    "English": {
        "app_title": "Crop Safety Guide", "app_caption": "A simple guide to understand crop risk and plan the next field step.",
        "choose_field": "Choose your field", "choose_caption": "Use these details to see the guidance for your crop.",
        "language": "Language", "district": "District", "year": "Year", "season": "Season", "crop": "Crop",
        "expert_heading": "For agriculture experts", "expert_toggle": "Open technical model details",
        "expert_caption": "This section explains how the AI model works. It is not needed to use the crop guidance.",
        "soil_irrigation": "Soil: {soil} · Irrigation: {irrigation}", "what_means": "What this means:",
        "crop_risk": "Crop risk", "your_crop": "Your crop", "better_crop": "Better crop option", "yield": "Expected yield index",
        "safer_options": "Safer crop options", "options_caption": "Options are ordered from lower to higher predicted risk for this district and season.",
        "tab_field": "My field", "tab_compare": "Compare crops", "tab_weather": "Plan for changing weather", "tab_map": "District map",
        "next_steps": "Your next field steps", "risk_comparison": "Crop risk comparison", "conditions": "Current field conditions",
        "glance": "At a glance", "suggested_crop": "Suggested crop option", "risk_level": "Current risk level",
        "compare_title": "Compare crop options", "compare_caption": "Lower risk can indicate a more suitable option for the selected district, season, and year.",
        "expert_tools": "Expert tools", "expert_note": "Technical diagnostics are separated from farmer guidance. They help experts validate and study the model; they do not change the recommendation shown above.",
        "weather_title": "Possible weather changes", "weather_caption": "These examples show how changing conditions may affect crop risk.",
        "custom_title": "Try your own situation", "custom_caption": "Move a slider only if you understand the local condition you want to compare.",
        "scenario_name": "Scenario name", "field_change": "My field change", "current_risk": "Current risk", "risk_after": "Risk after change", "changed_values": "Changed field values",
        "map_title": "Crop risk across districts", "list_title": "District risk list", "weather_examples": "View available weather examples",
        "high": "High Risk", "medium": "Medium Risk", "low": "Low Risk",
        "advice_high": "Check the field frequently and avoid making a large new input purchase until conditions improve.",
        "advice_medium": "Monitor the crop closely this week and keep irrigation or drainage ready.",
        "advice_low": "Conditions look comparatively favourable. Continue regular field checks.",
        "advice_water": "Watch soil moisture; irrigate only according to local crop guidance and water availability.",
        "advice_pest": "Inspect leaves and stems for pests. Contact a local agriculture officer before using any treatment.",
        "advice_crop": "For the next planting decision, {crop} may be a better fit for this district and season.",
    },
    "Hindi": {
        "app_title": "फसल सुरक्षा मार्गदर्शिका", "app_caption": "फसल का जोखिम समझें और खेत के अगले कदम की योजना बनाएं।", "choose_field": "अपना खेत चुनें", "choose_caption": "अपनी फसल के लिए सलाह देखने हेतु विवरण चुनें।", "language": "भाषा", "district": "ज़िला", "year": "वर्ष", "season": "मौसम", "crop": "फसल", "expert_heading": "कृषि विशेषज्ञों के लिए", "expert_toggle": "तकनीकी मॉडल विवरण खोलें", "expert_caption": "यह AI मॉडल की जानकारी है; फसल सलाह के लिए यह आवश्यक नहीं है।", "soil_irrigation": "मिट्टी: {soil} · सिंचाई: {irrigation}", "what_means": "इसका अर्थ:", "crop_risk": "फसल जोखिम", "your_crop": "आपकी फसल", "better_crop": "बेहतर फसल विकल्प", "yield": "अनुमानित उपज सूचकांक", "safer_options": "कम जोखिम वाले विकल्प", "options_caption": "विकल्प इस ज़िले और मौसम के लिए कम से अधिक अनुमानित जोखिम के क्रम में हैं।", "tab_field": "मेरा खेत", "tab_compare": "फसल तुलना", "tab_weather": "मौसम बदलाव की योजना", "tab_map": "ज़िला मानचित्र", "next_steps": "खेत के अगले कदम", "risk_comparison": "फसल जोखिम तुलना", "conditions": "वर्तमान खेत की स्थिति", "glance": "एक नज़र में", "suggested_crop": "सुझाया गया फसल विकल्प", "risk_level": "वर्तमान जोखिम स्तर", "compare_title": "फसल विकल्पों की तुलना", "compare_caption": "कम जोखिम इस ज़िले, मौसम और वर्ष के लिए अधिक उपयुक्त विकल्प दर्शा सकता है।", "expert_tools": "विशेषज्ञ उपकरण", "expert_note": "तकनीकी जानकारी किसान सलाह से अलग रखी गई है; इससे ऊपर की सलाह नहीं बदलती।", "weather_title": "मौसम में संभावित बदलाव", "weather_caption": "ये उदाहरण दिखाते हैं कि बदलती स्थितियाँ जोखिम को कैसे प्रभावित कर सकती हैं।", "custom_title": "अपनी स्थिति आज़माएं", "custom_caption": "स्लाइडर केवल स्थानीय स्थिति समझकर बदलें।", "scenario_name": "स्थिति का नाम", "field_change": "मेरे खेत का बदलाव", "current_risk": "वर्तमान जोखिम", "risk_after": "बदलाव के बाद जोखिम", "changed_values": "बदले हुए खेत मान", "map_title": "ज़िलों में फसल जोखिम", "list_title": "ज़िला जोखिम सूची", "weather_examples": "मौसम के उदाहरण देखें", "high": "उच्च जोखिम", "medium": "मध्यम जोखिम", "low": "कम जोखिम", "advice_high": "खेत को बार-बार देखें और स्थिति सुधरने तक बड़ा नया खर्च करने से बचें।", "advice_medium": "इस सप्ताह फसल की निगरानी रखें और सिंचाई या जल निकास तैयार रखें।", "advice_low": "स्थिति अपेक्षाकृत अनुकूल है। नियमित खेत निरीक्षण जारी रखें।", "advice_water": "मिट्टी की नमी पर नज़र रखें; स्थानीय सलाह और पानी की उपलब्धता के अनुसार ही सिंचाई करें।", "advice_pest": "पत्तियों और तनों में कीट देखें। उपचार से पहले स्थानीय कृषि अधिकारी से संपर्क करें।", "advice_crop": "अगली बुआई के लिए {crop} इस ज़िले और मौसम में अधिक उपयुक्त हो सकती है।"},
}

# Until each language is independently reviewed, English is a safe fallback for
# less common strings. The farmer-critical labels and guidance are translated.
TEXT.update({language: {**TEXT["English"], **translations} for language, translations in {
    "Marathi": {"app_title": "पीक सुरक्षा मार्गदर्शक", "language": "भाषा", "choose_field": "तुमचे शेत निवडा", "crop_risk": "पिकाचा धोका", "your_crop": "तुमचे पीक", "better_crop": "चांगला पीक पर्याय", "high": "जास्त धोका", "medium": "मध्यम धोका", "low": "कमी धोका", "tab_field": "माझे शेत", "tab_compare": "पिकांची तुलना", "advice_high": "शेताची वारंवार पाहणी करा आणि परिस्थिती सुधारेपर्यंत मोठा नवीन खर्च टाळा।", "advice_medium": "या आठवड्यात पिकावर लक्ष ठेवा आणि सिंचन किंवा निचऱ्याची तयारी ठेवा।", "advice_low": "स्थिती तुलनेने अनुकूल आहे. नियमित शेत पाहणी सुरू ठेवा।"},
    "Bengali": {"app_title": "ফসল সুরক্ষা নির্দেশিকা", "language": "ভাষা", "choose_field": "আপনার ক্ষেত বেছে নিন", "crop_risk": "ফসলের ঝুঁকি", "your_crop": "আপনার ফসল", "better_crop": "ভালো ফসলের বিকল্প", "high": "উচ্চ ঝুঁকি", "medium": "মাঝারি ঝুঁকি", "low": "কম ঝুঁকি", "tab_field": "আমার ক্ষেত", "tab_compare": "ফসল তুলনা", "advice_high": "মাঠ ঘন ঘন দেখুন এবং পরিস্থিতির উন্নতি না হওয়া পর্যন্ত বড় নতুন খরচ এড়িয়ে চলুন।", "advice_medium": "এই সপ্তাহে ফসল নজরে রাখুন এবং সেচ বা জলনিকাশের প্রস্তুতি রাখুন।", "advice_low": "পরিস্থিতি তুলনামূলকভাবে অনুকূল। নিয়মিত ক্ষেত পরিদর্শন চালিয়ে যান।"},
    "Telugu": {"app_title": "పంట భద్రత మార్గదర్శిని", "language": "భాష", "choose_field": "మీ పొలాన్ని ఎంచుకోండి", "crop_risk": "పంట ప్రమాదం", "your_crop": "మీ పంట", "better_crop": "మెరుగైన పంట ఎంపిక", "high": "అధిక ప్రమాదం", "medium": "మధ్యస్థ ప్రమాదం", "low": "తక్కువ ప్రమాదం", "tab_field": "నా పొలం", "tab_compare": "పంటల పోలిక", "advice_high": "పొలాన్ని తరచుగా పరిశీలించండి; పరిస్థితి మెరుగుపడే వరకు పెద్ద కొత్త ఖర్చును నివారించండి।", "advice_medium": "ఈ వారం పంటను గమనించండి; నీటిపారుదల లేదా నీటి నికాసుకు సిద్ధంగా ఉండండి।", "advice_low": "పరిస్థితులు సాపేక్షంగా అనుకూలంగా ఉన్నాయి. క్రమం తప్పకుండా పొలాన్ని పరిశీలించండి।"},
    "Tamil": {"app_title": "பயிர் பாதுகாப்பு வழிகாட்டி", "language": "மொழி", "choose_field": "உங்கள் வயலைத் தேர்ந்தெடுக்கவும்", "crop_risk": "பயிர் அபாயம்", "your_crop": "உங்கள் பயிர்", "better_crop": "சிறந்த பயிர் தேர்வு", "high": "அதிக அபாயம்", "medium": "நடுத்தர அபாயம்", "low": "குறைந்த அபாயம்", "tab_field": "என் வயல்", "tab_compare": "பயிர் ஒப்பீடு", "advice_high": "வயலை அடிக்கடி பாருங்கள்; நிலைமை மேம்படும் வரை பெரிய புதிய செலவைத் தவிர்க்கவும்।", "advice_medium": "இந்த வாரம் பயிரைக் கண்காணித்து, பாசனம் அல்லது வடிகாலுக்குத் தயாராக இருங்கள்।", "advice_low": "நிலைமை ஒப்பீட்டளவில் சாதகமாக உள்ளது. வழக்கமான வயல் கண்காணிப்பைத் தொடரவும்।"},
    "Kannada": {"app_title": "ಬೆಳೆ ಸುರಕ್ಷತಾ ಮಾರ್ಗದರ್ಶಿ", "language": "ಭಾಷೆ", "choose_field": "ನಿಮ್ಮ ಹೊಲವನ್ನು ಆಯ್ಕೆಮಾಡಿ", "crop_risk": "ಬೆಳೆ ಅಪಾಯ", "your_crop": "ನಿಮ್ಮ ಬೆಳೆ", "better_crop": "ಉತ್ತಮ ಬೆಳೆ ಆಯ್ಕೆ", "high": "ಹೆಚ್ಚಿನ ಅಪಾಯ", "medium": "ಮಧ್ಯಮ ಅಪಾಯ", "low": "ಕಡಿಮೆ ಅಪಾಯ", "tab_field": "ನನ್ನ ಹೊಲ", "tab_compare": "ಬೆಳೆ ಹೋಲಿಕೆ", "advice_high": "ಹೊಲವನ್ನು ಆಗಾಗ ಪರಿಶೀಲಿಸಿ; ಪರಿಸ್ಥಿತಿ ಸುಧಾರಿಸುವವರೆಗೆ ದೊಡ್ಡ ಹೊಸ ಖರ್ಚು ತಪ್ಪಿಸಿ।", "advice_medium": "ಈ ವಾರ ಬೆಳೆಯನ್ನು ಗಮನಿಸಿ; ನೀರಾವರಿ ಅಥವಾ ನೀರು ಹೊರಹಾಕಲು ಸಿದ್ಧರಿರಿ।", "advice_low": "ಪರಿಸ್ಥಿತಿ ತುಲನಾತ್ಮಕವಾಗಿ ಅನುಕೂಲಕರವಾಗಿದೆ. ನಿಯಮಿತ ಹೊಲ ಪರಿಶೀಲನೆ ಮುಂದುವರಿಸಿ।"},
    "Gujarati": {"app_title": "પાક સુરક્ષા માર્ગદર્શિકા", "language": "ભાષા", "choose_field": "તમારું ખેતર પસંદ કરો", "crop_risk": "પાકનું જોખમ", "your_crop": "તમારો પાક", "better_crop": "વધુ સારો પાક વિકલ્પ", "high": "વધુ જોખમ", "medium": "મધ્યમ જોખમ", "low": "ઓછું જોખમ", "tab_field": "મારું ખેતર", "tab_compare": "પાકની સરખામણી", "advice_high": "ખેતરની વારંવાર તપાસ કરો અને સ્થિતિ સુધરે ત્યાં સુધી મોટો નવો ખર્ચ ટાળો।", "advice_medium": "આ અઠવાડિયે પાક પર નજર રાખો અને સિંચાઈ કે પાણીના નિકાલની તૈયારી રાખો।", "advice_low": "સ્થિતિ તુલનાત્મક રીતે અનુકૂળ છે. ખેતરની નિયમિત તપાસ ચાલુ રાખો।"},
}.items()})


def translate(language, key, **values):
    """Return a translated UI string, falling back to English when needed."""
    template = TEXT.get(language, TEXT["English"]).get(key, TEXT["English"].get(key, key))
    return template.format(**values)


VALUE_TRANSLATIONS = {
    "Hindi": {"Rice": "धान", "Wheat": "गेहूँ", "Maize": "मक्का", "Cotton": "कपास", "Soybean": "सोयाबीन", "Millet": "बाजरा", "Groundnut": "मूंगफली", "Chickpea": "चना", "Mustard": "सरसों", "Kharif": "खरीफ", "Rabi": "रबी", "Summer": "गर्मी", "High": "उच्च", "Medium": "मध्यम", "Low": "कम", "Rainfall": "बारिश", "Temperature": "तापमान", "Humidity": "नमी", "SoilMoisture": "मिट्टी की नमी", "NDVI_Flowering": "फसल की हरियाली", "WaterStress": "पानी की कमी"},
    "Marathi": {"Rice": "तांदूळ", "Wheat": "गहू", "Maize": "मका", "Cotton": "कापूस", "Soybean": "सोयाबीन", "Millet": "बाजरी", "Groundnut": "भुईमूग", "Chickpea": "हरभरा", "Mustard": "मोहरी", "Kharif": "खरीप", "Rabi": "रब्बी", "High": "जास्त", "Medium": "मध्यम", "Low": "कमी"},
    "Bengali": {"Rice": "ধান", "Wheat": "গম", "Maize": "ভুট্টা", "Cotton": "তুলা", "Soybean": "সয়াবিন", "Millet": "বাজরা", "Groundnut": "চিনাবাদাম", "Chickpea": "ছোলা", "Mustard": "সরিষা", "Kharif": "খরিফ", "Rabi": "রবি", "High": "উচ্চ", "Medium": "মাঝারি", "Low": "কম"},
    "Telugu": {"Rice": "వరి", "Wheat": "గోధుమ", "Maize": "మొక్కజొన్న", "Cotton": "పత్తి", "Soybean": "సోయాబీన్", "Millet": "జొన్న", "Groundnut": "వేరుశెనగ", "Chickpea": "సెనగ", "Mustard": "ఆవాలు", "Kharif": "ఖరీఫ్", "Rabi": "రబీ", "High": "అధిక", "Medium": "మధ్యస్థ", "Low": "తక్కువ"},
    "Tamil": {"Rice": "நெல்", "Wheat": "கோதுமை", "Maize": "மக்காச்சோளம்", "Cotton": "பருத்தி", "Soybean": "சோயாபீன்", "Millet": "கம்பு", "Groundnut": "நிலக்கடலை", "Chickpea": "கடலை", "Mustard": "கடுகு", "Kharif": "கரீஃப்", "Rabi": "ரபி", "High": "அதிக", "Medium": "நடுத்தர", "Low": "குறைந்த"},
    "Kannada": {"Rice": "ಭತ್ತ", "Wheat": "ಗೋಧಿ", "Maize": "ಮೆಕ್ಕೆಜೋಳ", "Cotton": "ಹತ್ತಿ", "Soybean": "ಸೋಯಾಬೀನ್", "Millet": "ಸಜ್ಜೆ", "Groundnut": "ಕಡಲೆಕಾಯಿ", "Chickpea": "ಕಡಲೆ", "Mustard": "ಸಾಸಿವೆ", "Kharif": "ಖರೀಫ್", "Rabi": "ರಬಿ", "High": "ಹೆಚ್ಚಿನ", "Medium": "ಮಧ್ಯಮ", "Low": "ಕಡಿಮೆ"},
    "Gujarati": {"Rice": "ચોખા", "Wheat": "ઘઉં", "Maize": "મકાઈ", "Cotton": "કપાસ", "Soybean": "સોયાબીન", "Millet": "બાજરી", "Groundnut": "મગફળી", "Chickpea": "ચણા", "Mustard": "રાઈ", "Kharif": "ખરીફ", "Rabi": "રબી", "High": "વધુ", "Medium": "મધ્યમ", "Low": "ઓછું"},
}

FEATURE_TRANSLATIONS = {
    "Hindi": {"Rainfall": "बारिश", "Temperature": "तापमान", "Humidity": "नमी", "SoilMoisture": "मिट्टी की नमी", "NDVI_Flowering": "फसल की हरियाली", "WaterStress": "पानी की कमी", "PestRisk": "कीट जोखिम"},
    "Marathi": {"Rainfall": "पाऊस", "Temperature": "तापमान", "Humidity": "आर्द्रता", "SoilMoisture": "मातीतील ओलावा", "NDVI_Flowering": "पिकाची हिरवळ", "WaterStress": "पाण्याचा ताण", "PestRisk": "कीड धोका"},
    "Bengali": {"Rainfall": "বৃষ্টিপাত", "Temperature": "তাপমাত্রা", "Humidity": "আর্দ্রতা", "SoilMoisture": "মাটির আর্দ্রতা", "NDVI_Flowering": "ফসলের সবুজভাব", "WaterStress": "জলের ঘাটতি", "PestRisk": "পোকার ঝুঁকি"},
    "Telugu": {"Rainfall": "వర్షపాతం", "Temperature": "ఉష్ణోగ్రత", "Humidity": "తేమ", "SoilMoisture": "నేల తేమ", "NDVI_Flowering": "పంట పచ్చదనం", "WaterStress": "నీటి కొరత", "PestRisk": "పురుగు ప్రమాదం"},
    "Tamil": {"Rainfall": "மழைப்பொழிவு", "Temperature": "வெப்பநிலை", "Humidity": "ஈரப்பதம்", "SoilMoisture": "மண் ஈரப்பதம்", "NDVI_Flowering": "பயிர் பசுமை", "WaterStress": "நீர் பற்றாக்குறை", "PestRisk": "பூச்சி அபாயம்"},
    "Kannada": {"Rainfall": "ಮಳೆ", "Temperature": "ತಾಪಮಾನ", "Humidity": "ಆರ್ದ್ರತೆ", "SoilMoisture": "ಮಣ್ಣಿನ ತೇವಾಂಶ", "NDVI_Flowering": "ಬೆಳೆ ಹಸಿರು", "WaterStress": "ನೀರಿನ ಕೊರತೆ", "PestRisk": "ಕೀಟ ಅಪಾಯ"},
    "Gujarati": {"Rainfall": "વરસાદ", "Temperature": "તાપમાન", "Humidity": "ભેજ", "SoilMoisture": "જમીનની ભેજ", "NDVI_Flowering": "પાકની હરિયાળી", "WaterStress": "પાણીની અછત", "PestRisk": "જીવાત જોખમ"},
}


def localize_value(language, value):
    return VALUE_TRANSLATIONS.get(language, {}).get(str(value), value)


def localize_feature(language, feature):
    return FEATURE_TRANSLATIONS.get(language, {}).get(feature, feature)


def localize_map_html(html, language):
    """Localize the labels and values embedded in Folium district popups."""
    labels = {
        "Current Crop": {"Hindi": "वर्तमान फसल", "Marathi": "सध्याचे पीक", "Bengali": "বর্তমান ফসল", "Telugu": "ప్రస్తుత పంట", "Tamil": "தற்போதைய பயிர்", "Kannada": "ಪ್ರಸ್ತುತ ಬೆಳೆ", "Gujarati": "વર્તમાન પાક"},
        "Recommended Crop": {"Hindi": "सुझाई गई फसल", "Marathi": "सुचविलेले पीक", "Bengali": "প্রস্তাবিত ফসল", "Telugu": "సూచించిన పంట", "Tamil": "பரிந்துரைக்கப்பட்ட பயிர்", "Kannada": "ಸೂಚಿಸಿದ ಬೆಳೆ", "Gujarati": "સૂચિત પાક"},
        "Risk Level": {"Hindi": "जोखिम स्तर", "Marathi": "धोका पातळी", "Bengali": "ঝুঁকির স্তর", "Telugu": "ప్రమాద స్థాయి", "Tamil": "அபாய நிலை", "Kannada": "ಅಪಾಯ ಮಟ್ಟ", "Gujarati": "જોખમ સ્તર"},
        "Consensus Risk": {"Hindi": "कुल जोखिम", "Marathi": "एकूण धोका", "Bengali": "মোট ঝুঁকি", "Telugu": "మొత్తం ప్రమాదం", "Tamil": "மொத்த அபாயம்", "Kannada": "ಒಟ್ಟು ಅಪಾಯ", "Gujarati": "કુલ જોખમ"},
        "Top Options": {"Hindi": "मुख्य विकल्प", "Marathi": "प्रमुख पर्याय", "Bengali": "সেরা বিকল্প", "Telugu": "ముఖ్య ఎంపికలు", "Tamil": "முக்கிய தேர்வுகள்", "Kannada": "ಮುಖ್ಯ ಆಯ್ಕೆಗಳು", "Gujarati": "મુખ્ય વિકલ્પો"},
    }
    for source, translated in labels.items():
        html = html.replace(source, translated.get(language, source))
    for source, translated in VALUE_TRANSLATIONS.get(language, {}).items():
        html = html.replace(source, translated)
    return html
