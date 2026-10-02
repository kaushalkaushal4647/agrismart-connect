/**
 * AgriSmart Connect — Click-to-Speak Voice Guidance System
 * =========================================================
 * Uses the browser's native window.speechSynthesis API.
 * No external libraries. Fully client-side. Lightweight.
 *
 * HOW TO ADD/EDIT VOICE DESCRIPTIONS:
 *  Edit the `VOICE_DESCRIPTIONS` object below.
 *  Each key maps to a language code, and inside it,
 *  each module key holds the spoken text.
 *  Then call: AgriVoice.speakModule('moduleName')
 *  or attach: data-voice-module="moduleName" to any element.
 */

(function () {
    'use strict';

    // ─────────────────────────────────────────────────────────
    // 1. VOICE SETTINGS
    // ─────────────────────────────────────────────────────────
    var voiceSettings = {
        language: 'en-IN',
        rate: 0.9,
        pitch: 1
    };

    var LANG_MAP = {
        'en': 'en-IN',
        'ta': 'ta-IN',
        'hi': 'hi-IN',
        'ml': 'ml-IN',
        'te': 'te-IN'
    };

    // ─────────────────────────────────────────────────────────
    // 2. CENTRALIZED VOICE DESCRIPTIONS
    // ─────────────────────────────────────────────────────────
    var VOICE_DESCRIPTIONS = {

        en: {
            marketplace:
                'Welcome to the agrismart connect Marketplace. Farmers can register their products, upload real product images, add prices and available quantities, and sell directly to consumers, retail shops, and restaurants. This helps reduce unnecessary middlemen and gives farmers direct access to buyers.',

            aiAssistant:
                'This is the agrismart connect AI Assistant. Farmers can ask questions about crops, farming practices, pests, diseases, irrigation, weather, and other agricultural problems. The assistant provides AI-powered guidance and supports multilingual interaction.',

            cropDoctor:
                'This is the Visual Crop Disease Doctor. Upload a photo of an affected leaf or fruit for AI-powered multimodal pathology analysis and receive instant guidance on the detected disease.',

            hub:
                'This is the agrismart connect Hub. The hub connects farmers, orders, product quality checking, packing, and delivery operations. It helps organize agricultural products before they are sent to customers, retail shops, and restaurants.',

            irrigation:
                'This is the Smart Irrigation system. Soil moisture data is collected using sensors connected to an ESP32. The system can monitor soil conditions and control the water pump automatically or manually, helping farmers provide water when it is needed.',

            weather:
                'This weather module provides weather information that can help farmers plan irrigation, crop activities, and other farming operations.',

            pestDetection:
                'This AI-powered agricultural detection system helps identify possible crop pests or diseases from agricultural information or images and provides guidance to the farmer.',

            logistics:
                'This is the AgriSmart Connect Smart Logistics system. After an order is placed, products can move from the farmer or hub to the customer through delivery operations. The system is designed to improve order coordination and delivery visibility.',

            farmer:
                'This is the Farmer Dashboard. Farmers can manage their products, prices, images, available quantities, orders, and other marketplace activities from this section.',

            customer:
                'This is the Customer section. Customers can discover agricultural products, view product information, add products to their cart, place orders, and track their purchases.',

            retail:
                'This section is designed for retail shops. Shops can discover agricultural products, place bulk or regular orders, and manage their purchases through the agrismart connect marketplace.',

            restaurant:
                'This section is designed for restaurants. Restaurants can discover fresh agricultural products, place orders directly through the marketplace, and manage their procurement requirements.',

            payment:
                'This is the payment and checkout section. Buyers can review their order and complete payment securely before the order is processed.',

            tracking:
                'This section allows users to monitor their order status from order placement through processing, packing, dispatch, and delivery.',

            admin:
                'This is the Super Admin Command Center. Administrators can view platform analytics, manage users, configure the matching engine, monitor market liquidity, and oversee farmer payouts.',

            delivery:
                'This is the Delivery Partner portal. Delivery agents can claim collection runs, track hub pickups, and confirm delivery handoffs to customers.',

            home:
                'Welcome to AgriSmart Connect. This is a demand-matched agricultural supply platform that connects farmers directly with consumers, retail shops, and restaurants through regional collection hubs.',

            productRegistration:
                'Farmer product registration allows growers to list their harvested crops with variety, expected harvest date, unit price, and available weight.',

            imageUpload:
                'Real crop images show the true condition and grade of the harvest, helping buyers verify quality before ordering.',

            productEditing:
                'Farmers can update their produce prices and available inventory in real time as harvests progress.',

            productSearch:
                'Buyers can quickly filter agricultural produce by crop name, category, district, and organic certification.',

            cart:
                'Review your selected harvest items, adjust order quantities in kilograms, and check estimated hub handling fees.',

            ordering:
                'Confirm delivery address and finalize your harvest consignment order directly with local farmers and hubs.',

            farmerOrderManagement:
                'Farmers can view incoming buyer orders, review demand matching, and track hub pickups.'
        },

        ta: {
            marketplace:
                'அக்ரிஸ்மார்ட் கனெக்ட் சந்தைக்கு வரவேற்கிறோம். விவசாயிகள் தங்கள் பொருட்களை பதிவுசெய்து, படங்களை பதிவேற்றி, விலை மற்றும் அளவுகளை சேர்த்து, நேரடியாக நுகர்வோர், சில்லறை கடைகள் மற்றும் உணவகங்களுக்கு விற்கலாம்.',

            aiAssistant:
                'இது அக்ரிஸ்மார்ட் AI உதவியாளர். விவசாயிகள் பயிர்கள், பண்ணை நடைமுறைகள், பூச்சிகள், நோய்கள், நீர்ப்பாசனம் மற்றும் வானிலை பற்றி கேள்விகள் கேட்கலாம்.',

            cropDoctor:
                'இது காட்சி பயிர் நோய் மருத்துவர். பாதிக்கப்பட்ட இலை அல்லது பழத்தின் புகைப்படத்தை பதிவேற்றி AI ஆய்வு மூலம் உடனடி வழிகாட்டுதல் பெறுங்கள்.',

            hub:
                'இது அக்ரிஸ்மார்ட் கேந்திரம். இந்த மையம் விவசாயிகள், ஆர்டர்கள், தர சோதனை, பேக்கிங் மற்றும் டெலிவரி செயல்பாடுகளை இணைக்கிறது.',

            irrigation:
                'இது ஸ்மார்ட் நீர்ப்பாசன அமைப்பு. ESP32 உடன் இணைக்கப்பட்ட உணரிகள் மூலம் மண் ஈரப்பதம் கண்காணிக்கப்படுகிறது.',

            weather:
                'இந்த வானிலை தொகுதி விவசாயிகளுக்கு நீர்ப்பாசனம் மற்றும் பயிர் செயல்பாடுகளை திட்டமிட உதவும் தகவல்களை வழங்குகிறது.',

            pestDetection:
                'இந்த AI அமைப்பு பயிர் பூச்சி அல்லது நோய்களை கண்டறிந்து விவசாயிகளுக்கு வழிகாட்டுகிறது.',

            logistics:
                'இது ஸ்மார்ட் லாஜிஸ்டிக்ஸ் அமைப்பு. ஆர்டர் செய்யப்பட்ட பிறகு, பொருட்கள் விவசாயி அல்லது மையத்திலிருந்து வாடிக்கையாளருக்கு டெலிவரி செய்யப்படும்.',

            farmer:
                'இது விவசாயி டாஷ்போர்டு. விவசாயிகள் பொருட்கள், விலைகள், படங்கள் மற்றும் ஆர்டர்களை இங்கிருந்து நிர்வகிக்கலாம்.',

            customer:
                'இது நுகர்வோர் பிரிவு. வாடிக்கையாளர்கள் வேளாண் பொருட்களை கண்டறிந்து, கார்ட்டில் சேர்த்து, ஆர்டர் செய்யலாம்.',

            retail:
                'இந்த பிரிவு சில்லறை கடைகளுக்கானது. கடைகள் வேளாண் பொருட்களை கண்டறிந்து மொத்த ஆர்டர்களை வழங்கலாம்.',

            restaurant:
                'இந்த பிரிவு உணவகங்களுக்கானது. உணவகங்கள் புதிய வேளாண் பொருட்களை நேரடியாக சந்தை மூலம் ஆர்டர் செய்யலாம்.',

            payment:
                'இது கட்டண மற்றும் செக்அவுட் பிரிவு. வாங்குவோர் ஆர்டரை மதிப்பாய்வு செய்து பாதுகாப்பாக கட்டணம் செலுத்தலாம்.',

            tracking:
                'இந்த பிரிவு ஆர்டரின் நிலையை ஆர்டர் வழங்கியதிலிருந்து டெலிவரி வரை கண்காணிக்க உதவுகிறது.',

            admin:
                'இது சூப்பர் அட்மின் கட்டளை மையம். நிர்வாகிகள் தளத்தின் பகுப்பாய்வு மற்றும் விவசாயி கட்டணங்களை இங்கிருந்து கண்காணிக்கலாம்.',

            delivery:
                'இது டெலிவரி பார்ட்னர் போர்டல். டெலிவரி முகவர்கள் சேகரிப்பு ரன்களை கோரி டெலிவரியை உறுதிப்படுத்தலாம்.',

            home:
                'அக்ரிஸ்மார்ட் கனெக்டுக்கு வரவேற்கிறோம். இது விவசாயிகளை நுகர்வோர், சில்லறை கடைகள் மற்றும் உணவகங்களுடன் நேரடியாக இணைக்கும் வேளாண் தளம்.'
        },

        hi: {
            marketplace:
                'AgriSmart Connect मार्केटप्लेस में आपका स्वागत है। किसान अपने उत्पादों को पंजीकृत कर सकते हैं, छवियां अपलोड कर सकते हैं, कीमतें और मात्रा जोड़ सकते हैं, और सीधे उपभोक्ताओं को बेच सकते हैं।',

            aiAssistant:
                'यह AgriSmart AI सहायक है। किसान फसलों, कृषि पद्धतियों, कीटों, रोगों और सिंचाई के बारे में प्रश्न पूछ सकते हैं।',

            hub:
                'यह AgriSmart हब है। यह हब किसानों, ऑर्डरों, गुणवत्ता जांच, पैकिंग और डिलीवरी को जोड़ता है।',

            irrigation:
                'यह स्मार्ट सिंचाई प्रणाली है। ESP32 से जुड़े सेंसर मिट्टी की नमी को मापते हैं और पंप को स्वचालित रूप से नियंत्रित करते हैं।',

            logistics:
                'यह स्मार्ट लॉजिस्टिक्स प्रणाली है। ऑर्डर देने के बाद उत्पाद किसान से ग्राहक तक डिलीवरी के माध्यम से पहुंचते हैं।',

            farmer:
                'यह किसान डैशबोर्ड है। किसान अपने उत्पाद, कीमतें और ऑर्डरों को यहां से प्रबंधित कर सकते हैं।',

            customer:
                'यह उपभोक्ता अनुभाग है। ग्राहक कृषि उत्पादों को खोज सकते हैं और ऑर्डर दे सकते हैं।',

            retail:
                'यह अनुभाग खुदरा दुकानों के लिए है।',

            restaurant:
                'यह अनुभाग रेस्तरां के लिए है। रेस्तरां मार्केटप्लेस के माध्यम से ताजा कृषि उत्पाद ऑर्डर कर सकते हैं।',

            payment:
                'यह भुगतान और चेकआउट अनुभाग है।',

            tracking:
                'यह अनुभाग ऑर्डर की स्थिति डिलीवरी तक ट्रैक करने देता है।',

            admin:
                'यह सुपर एडमिन कमांड सेंटर है।',

            delivery:
                'यह डिलीवरी पार्टनर पोर्टल है।',

            home:
                'AgriSmart Connect में आपका स्वागत है। यह किसानों को उपभोक्ताओं और व्यवसायों से जोड़ने वाला कृषि मंच है।',

            weather: 'यह मौसम मॉड्यूल किसानों को सिंचाई और फसल गतिविधियों की योजना बनाने में मदद करता है।',

            pestDetection: 'यह AI प्रणाली फसल कीटों और रोगों की पहचान करती है।',

            cropDoctor: 'यह विजुअल क्रॉप डिजीज डॉक्टर है। प्रभावित पत्ती की फोटो अपलोड करें और AI विश्लेषण के माध्यम से मार्गदर्शन प्राप्त करें।'
        },

        ml: {
            marketplace: 'AgriSmart Connect മാർക്കറ്റ്‌പ്ലേസിലേക്ക് സ്വാഗതം. കർഷകർക്ക് ഉൽപ്പന്നങ്ങൾ നേരിട്ട് വിൽക്കാൻ കഴിയും.',
            aiAssistant: 'ഇത് AgriSmart AI സഹായകൻ ആണ്. കർഷകർക്ക് പംട, കൃഷി, വ്യാധികൾ ഇവ സംബന്ധിച്ച ചോദ്യങ്ങൾ ചോദിക്കാം.',
            hub: 'ഇത് AgriSmart ഹബ് ആണ്. ഗുണനിലവാര പരിശോധനയും ഡെലിവറിയും ഇവിടെ നിന്ന് നടക്കുന്നു.',
            irrigation: 'ഇത് സ്മാർട്ട് ജലസേചന വ്യവസ്ഥ ആണ്. ESP32 ഉപയോഗിച്ച് മണ്ണ് ഈർപ്പം നിരീക്ഷിക്കുന്നു.',
            logistics: 'ഇത് ഡെലിവറി ലോജിസ്റ്റിക്‌സ് ആണ്. ഓർഡർ ചെയ്‌ത ഉൽപ്പന്നങ്ങൾ ഡെലിവർ ചെയ്യപ്പെടും.',
            farmer: 'ഇത് കർഷകൻ ഡാഷ്‌ബോർഡ് ആണ്.',
            customer: 'ഇത് ഉപഭോക്തൃ വിഭാഗം ആണ്.',
            payment: 'ഇത് പേയ്‌മെന്റ് വിഭാഗം ആണ്.',
            tracking: 'ഓർഡർ ട്രാക്ക് ചെയ്യാൻ ഈ വിഭാഗം ഉപയോഗിക്കുക.',
            home: 'AgriSmart Connect ലേക്ക് സ്വാഗതം.',
            weather: 'ഈ കാലാവസ്ഥ മൊഡ്യൂൾ കർഷകരെ ആസൂത്രണം ചെയ്യാൻ സഹായിക്കുന്നു.',
            pestDetection: 'ഈ AI വിള രോഗ കണ്ടെത്തൽ ഉപകരണം ആണ്.',
            retail: 'ഈ വിഭാഗം ചില്ലറ കടകൾക്ക് വേണ്ടിയുള്ളതാണ്.',
            restaurant: 'ഈ വിഭാഗം റെസ്‌റ്റോറന്റുകൾക്ക് വേണ്ടിയുള്ളതാണ്.',
            admin: 'ഇത് അഡ്‌മിൻ കമാൻഡ് സെന്റർ ആണ്.',
            delivery: 'ഇത് ഡെലിവറി പോർട്ടൽ ആണ്.',
            cropDoctor: 'ഇത് ദൃശ്യ വിള രോഗ ഡോക്ടർ ആണ്.'
        },

        te: {
            marketplace: 'AgriSmart Connect మార్కెట్‌ప్లేస్‌కు స్వాగతం. రైతులు నేరుగా విక్రయించవచ్చు.',
            aiAssistant: 'ఇది AgriSmart AI సహాయకుడు. రైతులు పంటలు, చీడలు, నీటి పారుదల గురించి అడగవచ్చు.',
            hub: 'ఇది AgriSmart హబ్. నాణ్యత తనిఖీ మరియు డెలివరీ ఇక్కడ జరుగుతాయి.',
            irrigation: 'ఇది స్మార్ట్ నీటి పారుదల వ్యవస్థ. ESP32 ద్వారా నేల తేమ పర్యవేక్షిస్తారు.',
            logistics: 'ఇది డెలివరీ లాజిస్టిక్స్ వ్యవస్థ.',
            farmer: 'ఇది రైతు డాష్‌బోర్డ్.',
            customer: 'ఇది వినియోగదారు విభాగం.',
            payment: 'ఇది చెల్లింపు విభాగం.',
            tracking: 'ఆర్డర్ స్థితిని ట్రాక్ చేయండి.',
            home: 'AgriSmart Connect కి స్వాగతం.',
            weather: 'వాతావరణ మాడ్యూల్ రైతులకు సహాయపడుతుంది.',
            pestDetection: 'ఈ AI పంట రోగ గుర్తింపు సాధనం.',
            retail: 'ఇది చిల్లర దుకాణాల విభాగం.',
            restaurant: 'ఇది రెస్టారెంట్‌ల విభాగం.',
            admin: 'ఇది అడ్మిన్ కమాండ్ సెంటర్.',
            delivery: 'ఇది డెలివరీ పోర్టల్.',
            cropDoctor: 'ఇది విజువల్ క్రాప్ డిసీజ్ డాక్టర్.'
        }
    };

    // ─────────────────────────────────────────────────────────
    // 3. CORE SPEECH ENGINE
    // ─────────────────────────────────────────────────────────
    // 3. CORE SPEECH & AUDIO ENGINE
    // ─────────────────────────────────────────────────────────

    var activeAudio = null;
    var audioQueue = [];

    function stopAudio() {
        audioQueue = [];
        if (activeAudio) {
            try {
                activeAudio.pause();
                activeAudio.currentTime = 0;
            } catch (e) { }
            activeAudio = null;
        }
    }

    function stopSpeaking() {
        if ('speechSynthesis' in window) {
            try { window.speechSynthesis.cancel(); } catch (e) { }
        }
        stopAudio();
    }

    function getCurrentLang() {
        if (window.AgriSmartI18n && typeof window.AgriSmartI18n.getCurrentLanguage === 'function') {
            return window.AgriSmartI18n.getCurrentLanguage() || 'en';
        }
        return localStorage.getItem('agrismart_lang') || 'en';
    }

    function getSpeechLang() {
        var uiLang = getCurrentLang();
        return LANG_MAP[uiLang] || 'en-IN';
    }

    function getDescription(moduleKey) {
        var lang = getCurrentLang();
        var langData = VOICE_DESCRIPTIONS[lang] || VOICE_DESCRIPTIONS['en'];
        return (langData && langData[moduleKey]) || (VOICE_DESCRIPTIONS['en'] && VOICE_DESCRIPTIONS['en'][moduleKey]) || '';
    }

    function findVoiceForLang(langCode) {
        if (!('speechSynthesis' in window)) return null;
        var voices = window.speechSynthesis.getVoices() || [];
        if (voices.length === 0) return null;
        var code = (langCode || '').toLowerCase();
        var prefix = code.split('-')[0];

        // 1. Exact match (e.g. ta-in)
        var voice = voices.find(function (v) {
            return v.lang && v.lang.toLowerCase() === code;
        });
        if (voice) return voice;

        // 2. Prefix match (e.g. ta)
        voice = voices.find(function (v) {
            return v.lang && v.lang.toLowerCase().startsWith(prefix);
        });
        if (voice) return voice;

        // 3. Named match (e.g. Tamil, Valluvar, Pallavi)
        if (prefix === 'ta') {
            voice = voices.find(function (v) {
                var n = (v.name || '').toLowerCase();
                return n.indexOf('tamil') !== -1 || n.indexOf('valluvar') !== -1 || n.indexOf('pallavi') !== -1;
            });
        }
        return voice || null;
    }

    function _setSpeakingState(el, isSpeaking) {
        if (!el) return;
        try {
            if (isSpeaking) {
                el.setAttribute('data-voice-speaking', 'true');
                var icon = el.querySelector('.agv-speaker-icon');
                if (icon) icon.textContent = '🔊';
            } else {
                el.removeAttribute('data-voice-speaking');
                var icon2 = el.querySelector('.agv-speaker-icon');
                if (icon2) icon2.textContent = '🔈';
            }
        } catch (e) { }
    }

    function splitTextForAudio(text, maxLen) {
        maxLen = maxLen || 140;
        if (!text || text.length <= maxLen) return [text];
        var sentences = text.match(/[^.!?\n]+[.!?\n]*/g) || [text];
        var chunks = [];
        var current = '';
        sentences.forEach(function (s) {
            s = s.trim();
            if (!s) return;
            if ((current + ' ' + s).trim().length <= maxLen) {
                current = (current ? current + ' ' : '') + s;
            } else {
                if (current) chunks.push(current);
                if (s.length <= maxLen) {
                    current = s;
                } else {
                    var words = s.split(' ');
                    current = '';
                    words.forEach(function (w) {
                        if ((current + ' ' + w).trim().length <= maxLen) {
                            current = (current ? current + ' ' : '') + w;
                        } else {
                            if (current) chunks.push(current);
                            current = w;
                        }
                    });
                }
            }
        });
        if (current) chunks.push(current);
        return chunks;
    }

    function playAudioFallback(text, langCode, onEndCallback) {
        stopAudio();
        var chunks = splitTextForAudio(text, 140);
        if (!chunks || chunks.length === 0) {
            if (onEndCallback) onEndCallback();
            return;
        }
        audioQueue = chunks.slice();
        var shortLang = (langCode || 'ta').split('-')[0];

        function playNext() {
            if (audioQueue.length === 0) {
                activeAudio = null;
                if (onEndCallback) onEndCallback();
                return;
            }
            var chunk = audioQueue.shift();
            var url = 'https://translate.google.com/translate_tts?ie=UTF-8&tl=' + encodeURIComponent(shortLang) + '&client=tw-ob&q=' + encodeURIComponent(chunk);
            var audio = new Audio(url);
            activeAudio = audio;
            audio.onended = function () {
                playNext();
            };
            audio.onerror = function () {
                playNext();
            };
            audio.play().catch(function (err) {
                console.warn('[AgriVoice] Audio playback blocked or offline:', err);
                if (onEndCallback) onEndCallback();
            });
        }
        playNext();
    }

    function speak(text, opts, sourceEl) {
        if (!text || !text.trim()) return;
        var lang = (opts && opts.lang) || getSpeechLang();
        var langPrefix = lang.toLowerCase().split('-')[0];

        stopSpeaking();
        if (sourceEl) _setSpeakingState(sourceEl, true);

        // Check if browser has a native voice installed for this language
        var nativeVoice = findVoiceForLang(lang);

        // If regional language (like Tamil 'ta') and no native voice is installed on OS:
        if (!nativeVoice && (langPrefix === 'ta' || langPrefix === 'ml' || langPrefix === 'te')) {
            playAudioFallback(text, lang, function () {
                if (sourceEl) _setSpeakingState(sourceEl, false);
            });
            return;
        }

        if (!('speechSynthesis' in window)) {
            playAudioFallback(text, lang, function () {
                if (sourceEl) _setSpeakingState(sourceEl, false);
            });
            return;
        }

        try {
            var utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = lang;
            utterance.rate = (opts && opts.rate !== undefined) ? opts.rate : voiceSettings.rate;
            utterance.pitch = (opts && opts.pitch !== undefined) ? opts.pitch : voiceSettings.pitch;
            if (nativeVoice) utterance.voice = nativeVoice;

            utterance.onend = function () {
                if (sourceEl) _setSpeakingState(sourceEl, false);
            };

            utterance.onerror = function (e) {
                if (sourceEl) _setSpeakingState(sourceEl, false);
                if (e.error === 'language-unavailable' || e.error === 'synthesis-failed') {
                    if (sourceEl) _setSpeakingState(sourceEl, true);
                    playAudioFallback(text, lang, function () {
                        if (sourceEl) _setSpeakingState(sourceEl, false);
                    });
                }
            };

            window.speechSynthesis.speak(utterance);
        } catch (err) {
            console.warn('[AgriVoice] Voice guidance error, falling back to audio stream:', err);
            playAudioFallback(text, lang, function () {
                if (sourceEl) _setSpeakingState(sourceEl, false);
            });
        }
    }

    function speakModule(moduleKey, sourceEl) {
        var text = getDescription(moduleKey);
        if (!text) {
            console.warn('[AgriVoice] No description for module:', moduleKey);
            return;
        }
        var lang = getSpeechLang();
        speak(text, { lang: lang }, sourceEl);
    }

    // ─────────────────────────────────────────────────────────
    // 4. SPEAKER BUTTON FACTORY
    // ─────────────────────────────────────────────────────────

    function createSpeakerButton(moduleKey, titleText) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'agv-speaker-btn';
        btn.setAttribute('aria-label', 'Listen to ' + moduleKey + ' explanation');
        btn.setAttribute('title', titleText || 'Listen to explanation');
        var icon = document.createElement('span');
        icon.className = 'agv-speaker-icon';
        icon.textContent = '🔈';
        btn.appendChild(icon);
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            speakModule(moduleKey, btn);
        });
        return btn;
    }

    // ─────────────────────────────────────────────────────────
    // 5. CSS
    // ─────────────────────────────────────────────────────────

    function injectVoiceStyles() {
        if (document.getElementById('agv-voice-styles')) return;
        var style = document.createElement('style');
        style.id = 'agv-voice-styles';
        style.textContent = [
            '.agv-speaker-btn {',
            '  display:inline-flex;align-items:center;justify-content:center;',
            '  background:transparent;border:1px solid rgba(21,128,61,0.25);',
            '  border-radius:50%;width:30px;height:30px;cursor:pointer;',
            '  font-size:0.95rem;line-height:1;transition:background 0.18s,border-color 0.18s,transform 0.15s;',
            '  vertical-align:middle;flex-shrink:0;padding:0;outline:none;color:inherit;',
            '}',
            '.agv-speaker-btn:hover {',
            '  background:rgba(21,128,61,0.08);border-color:rgba(21,128,61,0.5);transform:scale(1.1);',
            '}',
            '.agv-speaker-btn:focus-visible {outline:2px solid #15803d;outline-offset:2px;}',
            '[data-voice-speaking="true"] .agv-speaker-btn,',
            '.agv-speaker-btn[data-voice-speaking="true"] {',
            '  animation:agv-pulse 1.2s ease-in-out infinite;',
            '  border-color:rgba(21,128,61,0.7);background:rgba(21,128,61,0.1);',
            '}',
            '@keyframes agv-pulse {',
            '  0%,100%{box-shadow:0 0 0 0 rgba(21,128,61,0.3);}',
            '  50%{box-shadow:0 0 0 5px rgba(21,128,61,0);}',
            '}',
            '.agv-page-voice-tag {',
            '  display:inline-flex;align-items:center;gap:0.35rem;',
            '  font-size:0.78rem;font-weight:600;color:#15803d;',
            '  background:rgba(21,128,61,0.08);border:1px solid rgba(21,128,61,0.2);',
            '  border-radius:9999px;padding:0.2rem 0.6rem;cursor:pointer;',
            '  transition:background 0.18s,border-color 0.18s;vertical-align:middle;',
            '  user-select:none;margin-left:0.5rem;',
            '}',
            '.agv-page-voice-tag:hover {',
            '  background:rgba(21,128,61,0.14);border-color:rgba(21,128,61,0.4);',
            '}',
            '.agv-page-voice-tag:focus-visible {outline:2px solid #15803d;outline-offset:2px;}',
            '.agv-listen-btn {',
            '  display:inline-flex;align-items:center;gap:0.3rem;',
            '  font-size:0.72rem;font-weight:600;color:#64748b;',
            '  background:transparent;border:1px solid #e2e8f0;',
            '  border-radius:9999px;padding:0.18rem 0.55rem;cursor:pointer;',
            '  margin-top:0.45rem;transition:color 0.15s,border-color 0.15s,background 0.15s;',
            '}',
            '.agv-listen-btn:hover {color:#15803d;border-color:#15803d;background:rgba(21,128,61,0.06);}'
        ].join('\n');
        document.head.appendChild(style);
    }

    // ─────────────────────────────────────────────────────────
    // 6. PAGE HEADER VOICE TAG
    // ─────────────────────────────────────────────────────────

    function attachPageHeaderVoice(moduleKey) {
        if (!moduleKey) return;
        var h1 = document.querySelector('main h1, section h1, .container h1');
        if (!h1) return;
        if (h1.parentNode.querySelector('.agv-page-voice-tag')) return;
        var tag = document.createElement('button');
        tag.type = 'button';
        tag.className = 'agv-page-voice-tag';
        tag.setAttribute('aria-label', 'Listen to ' + moduleKey + ' page explanation');
        tag.setAttribute('title', 'Click to hear what this page does');
        tag.tabIndex = 0;
        tag.innerHTML = '🔈 Listen';
        tag.addEventListener('click', function () { speakModule(moduleKey, tag); });
        tag.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); speakModule(moduleKey, tag); }
        });
        h1.insertAdjacentElement('afterend', tag);
    }

    // ─────────────────────────────────────────────────────────
    // 7. ROLE CARDS & WORKFLOW CARDS (index.html)
    // ─────────────────────────────────────────────────────────

    function attachRoleCardVoice() {
        var ROLE_HREF_MAP = {
            '/farmer.html': 'farmer',
            '/consumer.html': 'customer',
            '/restaurant.html': 'restaurant',
            '/retailer.html': 'retail',
            '/hub.html': 'hub',
            '/admin.html': 'admin',
            '/marketplace.html': 'marketplace',
            '/ai.html': 'aiAssistant',
            '/iot.html': 'irrigation',
            '/logistics.html': 'logistics',
            '/orders.html': 'tracking',
            '/delivery.html': 'delivery'
        };

        document.querySelectorAll('.role-card').forEach(function (card) {
            var anchor = card.querySelector('a[href]');
            if (!anchor) return;
            var href = anchor.getAttribute('href');
            var moduleKey = ROLE_HREF_MAP[href];
            if (!moduleKey) return;

            var heading = card.querySelector('h3');
            if (heading && !heading.querySelector('.agv-speaker-btn')) {
                var btn = createSpeakerButton(moduleKey, 'Listen to explanation');
                btn.style.marginLeft = '0.5rem';
                heading.appendChild(btn);
            }

            card.addEventListener('click', function (e) {
                var target = e.target;
                var tTag = target.tagName.toLowerCase();
                if (tTag === 'a' || target.closest('a') || tTag === 'button' || target.closest('button')) return;
                speakModule(moduleKey, card);
            });
        });

        var WORKFLOW_STEP_MAP = { '01': 'farmer', '02': 'customer', '03': 'marketplace', '04': 'hub', '05': 'logistics' };
        document.querySelectorAll('.workflow-card').forEach(function (card) {
            var stepEl = card.querySelector('.step-number');
            if (!stepEl) return;
            var step = stepEl.textContent.trim();
            var moduleKey = WORKFLOW_STEP_MAP[step];
            if (!moduleKey) return;
            card.style.cursor = 'pointer';
            card.setAttribute('tabindex', '0');
            card.setAttribute('aria-label', 'Click to hear about this step');
            card.addEventListener('click', function () { speakModule(moduleKey, card); });
            card.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); speakModule(moduleKey, card); }
            });
        });
    }

    // ─────────────────────────────────────────────────────────
    // 8. DATA-VOICE-MODULE AUTO-ATTACH
    // ─────────────────────────────────────────────────────────

    function attachVoiceToElement(el) {
        var moduleKey = el.getAttribute('data-voice-module');
        if (!moduleKey) return;
        if (!el.getAttribute('aria-label')) {
            el.setAttribute('aria-label', 'Listen to ' + moduleKey + ' explanation');
        }
        var tag = el.tagName.toLowerCase();
        if (!['a', 'button', 'input', 'select', 'textarea'].includes(tag)) {
            if (!el.getAttribute('role')) el.setAttribute('role', 'button');
            if (!el.getAttribute('tabindex')) el.setAttribute('tabindex', '0');
        }
        el.addEventListener('click', function (e) {
            var t = e.target;
            var tTag = t.tagName.toLowerCase();
            if (['input', 'select', 'textarea', 'button', 'a'].includes(tTag)) return;
            speakModule(moduleKey, el);
        });
        el.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); speakModule(moduleKey, el); }
        });
    }

    function attachAllVoiceModules() {
        document.querySelectorAll('[data-voice-module]').forEach(attachVoiceToElement);
    }

    // ─────────────────────────────────────────────────────────
    // 9. AI CHAT LISTEN BUTTON INJECTOR
    // ─────────────────────────────────────────────────────────

    function injectChatListenButton(msgEl, responseText) {
        if (!msgEl || !responseText) return;
        if (msgEl.querySelector('.agv-listen-btn')) return;
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'agv-listen-btn';
        btn.setAttribute('aria-label', 'Listen to AI response');
        btn.innerHTML = '🔈 Listen';
        var capturedText = responseText;
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            speak(capturedText);
        });
        msgEl.appendChild(document.createElement('br'));
        msgEl.appendChild(btn);
    }

    // ─────────────────────────────────────────────────────────
    // 10. INIT
    // ─────────────────────────────────────────────────────────

    function init() {
        injectVoiceStyles();
        if ('speechSynthesis' in window) {
            window.speechSynthesis.getVoices();
            if (typeof window.speechSynthesis.addEventListener === 'function') {
                window.speechSynthesis.addEventListener('voiceschanged', function () {
                    window.speechSynthesis.getVoices();
                });
            }
        }
        attachAllVoiceModules();
        attachRoleCardVoice();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // ─────────────────────────────────────────────────────────
    // 11. PUBLIC API
    // ─────────────────────────────────────────────────────────
    window.AgriVoice = {
        speak: speak,
        speakModule: speakModule,
        stopSpeaking: stopSpeaking,
        getDescription: getDescription,
        createSpeakerButton: createSpeakerButton,
        injectChatListenButton: injectChatListenButton,
        attachPageHeaderVoice: attachPageHeaderVoice,
        voiceSettings: voiceSettings,
        VOICE_DESCRIPTIONS: VOICE_DESCRIPTIONS
    };

})();
