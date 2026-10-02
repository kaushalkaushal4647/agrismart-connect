/**
 * AgriSmart Connect - Multilingual Regional Language Support
 * Supported Languages:
 *  - English (en) [Default]
 *  - தமிழ் / Tamil (ta)
 *  - हिन्दी / Hindi (hi)
 *  - മലയാളം / Malayalam (ml)
 *  - తెలుగు / Telugu (te)
 */

(function () {
    'use strict';

    const I18N_STORAGE_KEY = 'agrismart_lang';

    const LANGUAGES = {
        'en': { name: 'English', native: 'English', flag: '🇬🇧' },
        'ta': { name: 'Tamil', native: 'தமிழ்', flag: '🇮🇳' },
        'hi': { name: 'Hindi', native: 'हिन्दी', flag: '🇮🇳' },
        'ml': { name: 'Malayalam', native: 'മലയാളം', flag: '🇮🇳' },
        'te': { name: 'Telugu', native: 'తెలుగు', flag: '🇮🇳' }
    };

    // Translation Dictionary
    const DICTIONARY = {
        ta: {
            // Brand & Navigation
            'AgriSmart': 'அக்ரிஸ்மார்ட்',
            'Connect': 'கனெக்ட்',
            'Core': 'மையம்',
            'Home': 'முகப்பு',
            'How It Works': 'செயல்படும் முறை',
            'Role Portals': 'பயனர் தளங்கள்',
            'Marketplace': 'சந்தை (Marketplace)',
            'AI Agronomist': 'AI வேளாண் நிபுணர்',
            'Smart IoT': 'ஸ்மார்ட் IoT',
            'Wholesale': 'மொத்த விற்பனை',
            'Retail Wholesale': 'சில்லறை மொத்த விற்பனை',
            'My Orders': 'என் ஆர்டர்கள்',
            'Active Consignments': 'செயலில் உள்ள ஒப்பந்தங்கள்',
            'Fulfillment Pipeline': 'விநியோக நிலவரம்',
            'Sign In': 'உள்நுழைக',
            'Get Started': 'தொடங்குங்கள்',
            'Log Out': 'வெளியேறு',
            'Sign Out': 'வெளியேறு',
            'Register Store': 'கடையை பதிவுசெய்க',
            'Join the Network': 'வலையமைப்பில் இணைக',
            'Explore Portals': 'தளங்களை காண்க',
            'Explore Marketplace': 'சந்தையை ஆராய்க',

            // Hero & Descriptions
            'Demand-Matched Agricultural Supply Platform': 'தேவைக்கு ஏற்ப இணைக்கப்பட்ட விவசாய விநியோக தளம்',
            'Demand-Matched': 'தேவைக்கு ஏற்ப இணைக்கப்பட்ட',
            'Agricultural Supply': 'விவசாய விநியோக',
            'Platform': 'தளம்',
            'Next-Gen Agricultural Logistics': 'அதிநவீன வேளாண் தளவாடங்கள்',
            'AgriSmart Connect matches farmer harvest schedules directly with real-time consumer and B2B demand. No speculative over-purchasing, zero spoilage, and verified quality through regional collection hubs.':
                'அக்ரிஸ்மார்ட் கனெக்ட் விவசாயிகளின் அறுவடை அட்டவணையை நுகர்வோர் மற்றும் வணிக தேவைகளுடன் நேரடியாக இணைக்கிறது. வீணாதல் இல்லாத, தரமான விவசாய விநியோகம்.',

            // Roles
            'Farmers & Producers': 'விவசாயிகள் & உற்பத்தியாளர்கள்',
            'Direct Consumers': 'நேரடி நுகர்வோர்',
            'Retailers & Supermarkets': 'சில்லறை விற்பனையாளர்கள்',
            'Restaurants & Commercial': 'உணவகங்கள் & வணிக நிறுவனங்கள்',
            'Collection Hubs': 'சேகரிப்பு மையங்கள்',
            'Quality Inspectors': 'தர பரிசோதகர்கள்',
            'Delivery Fleet': 'விநியோகக் குழு',
            'Platform Admin': 'நிர்வாகி (Admin)',

            // Common Actions & Buttons
            'Select Crop': 'பயிரைத் தேர்ந்தெடுக்கவும்',
            '-- Select Crop --': '-- பயிரைத் தேர்ந்தெடுக்கவும் --',
            'Select Variety': 'ரகத்தைத் தேர்ந்தெடுக்கவும்',
            '-- Select Variety --': '-- ரகத்தைத் தேர்ந்தெடுக்கவும் --',
            'Preferred Collection Hub': 'விருப்பமான சேகரிப்பு மையம்',
            '-- Select Preferred Hub --': '-- சேகரிப்பு மையத்தை தேர்ந்தெடுக்கவும் --',
            'List Produce Batch': 'விளைச்சல் தொகுப்பை பட்டியலிடுக',
            'List Upcoming Harvest': 'எதிர்கால அறுவடையை பட்டியலிடுக',
            'Confirm & Lock Consignment Contract': 'ஒப்பந்தத்தை உறுதிசெய்து பூட்டவும்',
            'Run Multi-Farmer Split Match': 'விவசாயிகள் ஒருங்கிணைப்பு தேடல்',
            'Add to Cart': 'கார்ட்டில் சேர்க்க',
            'Proceed to Checkout': 'செக்அவுட் செய்க',
            'Cancel': 'ரத்து செய்க',
            'Submit': 'சமர்ப்பிக்கவும்',
            'Save Changes': 'மாற்றங்களை சேமிக்கவும்',
            'Filter by Category': 'வகை வாரியாக வடிகட்டவும்',
            'All Crops': 'அனைத்து பயிர்களும்',
            'Search produce or farm...': 'பயிர் அல்லது பண்ணையை தேடவும்...',
            'Order Produce': 'ஆர்டர் செய்க',

            // Crop Names
            'Tomato': 'தக்காளி',
            'Potato': 'உருளைக்கிழங்கு',
            'Onion': 'வெங்காயம்',
            'Carrot': 'கேரட்',
            'Spinach': 'பசலைக்கீரை',
            'Cabbage': 'முட்டைக்கோஸ்',
            'Cauliflower': 'காலிஃபிளவர்',
            'Green Chilli': 'பச்சை மிளகாய்',

            // Quality & Order Statuses
            'Grade A': 'தரம் A (உயர்தரம்)',
            'Grade B': 'தரம் B (வணிகம்)',
            'Grade C': 'தரம் C (செயலாக்கம்)',
            'Order Placed': 'ஆர்டர் பதிவு செய்யப்பட்டது',
            'Farmer Assigned': 'விவசாயி நியமிக்கப்பட்டார்',
            'Collection': 'சேகரிப்பு',
            'At Hub QA': 'மையத்தில் தர ஆய்வு',
            'Packed': 'பேக் செய்யப்பட்டது',
            'Out for Delivery': 'டெலிவரிக்கு புறப்பட்டது',
            'Delivered': 'விநியோகிக்கப்பட்டது',
            'Cancelled': 'ரத்து செய்யப்பட்டது',
            'Pending': 'நிலுவையில் உள்ளது',
            'Paid': 'செலுத்தப்பட்டது',
            'Escrow Locked': 'பாதுகாப்பு வைப்பு வைக்கப்பட்டது',

            // Messages & Alerts
            'Language switched to Tamil': 'மொழி தமிழுக்கு மாற்றப்பட்டது',
            'Profile details loaded': 'சுயவிவர தகவல்கள் ஏற்றப்பட்டன',
            'Order placed successfully!': 'ஆர்டர் வெற்றிகரமாக பதிவு செய்யப்பட்டது!'
        },

        hi: {
            // Brand & Navigation
            'AgriSmart': 'एग्रीस्मार्ट',
            'Connect': 'कनेक्ट',
            'Core': 'कोर',
            'Home': 'होम',
            'How It Works': 'यह कैसे काम करता है',
            'Role Portals': 'भूमिका पोर्टल',
            'Marketplace': 'मंडी / मार्केटप्लेस',
            'AI Agronomist': 'एआई कृषि विशेषज्ञ',
            'Smart IoT': 'स्मार्ट आईओटी',
            'Wholesale': 'थोक व्यापार',
            'Retail Wholesale': 'खुदरा थोक खरीद',
            'My Orders': 'मेरे ऑर्डर',
            'Active Consignments': 'सक्रिय अनुबंध',
            'Fulfillment Pipeline': 'आपूर्ति स्थिति',
            'Sign In': 'साइन इन',
            'Get Started': 'शुरू करें',
            'Log Out': 'लॉग आउट',
            'Sign Out': 'लॉग आउट',
            'Register Store': 'दुकान पंजीकृत करें',
            'Join the Network': 'नेटवर्क से जुड़ें',
            'Explore Portals': 'पोर्टल देखें',
            'Explore Marketplace': 'मार्केटप्लेस देखें',

            // Hero & Descriptions
            'Demand-Matched Agricultural Supply Platform': 'मांग-आधारित कृषि आपूर्ति मंच',
            'Demand-Matched': 'मांग-आधारित',
            'Agricultural Supply': 'कृषि आपूर्ति',
            'Platform': 'मंच',
            'Next-Gen Agricultural Logistics': 'आधुनिक कृषि लॉजिस्टिक्स',
            'AgriSmart Connect matches farmer harvest schedules directly with real-time consumer and B2B demand. No speculative over-purchasing, zero spoilage, and verified quality through regional collection hubs.':
                'एग्रीस्मार्ट कनेक्ट किसानों के फसल कटाई समय को सीधे उपभोक्ताओं और थोक खरीदारों की मांग से जोड़ता है। शून्य बर्बादी और प्रमाणित गुणवत्ता।',

            // Roles
            'Farmers & Producers': 'किसान और उत्पादक',
            'Direct Consumers': 'प्रत्यक्ष उपभोक्ता',
            'Retailers & Supermarkets': 'खुदरा विक्रेता और सुपरमार्केट',
            'Restaurants & Commercial': 'रेस्टोरेंट और वाणिज्यिक',
            'Collection Hubs': 'संग्रह केंद्र (Hubs)',
            'Quality Inspectors': 'गुणवत्ता निरीक्षक',
            'Delivery Fleet': 'डिलीवरी वाहन दल',
            'Platform Admin': 'प्लेटफ़ॉर्म व्यवस्थापक',

            // Common Actions & Buttons
            'Select Crop': 'फसल चुनें',
            '-- Select Crop --': '-- फसल चुनें --',
            'Select Variety': 'किस्म चुनें',
            '-- Select Variety --': '-- किस्म चुनें --',
            'Preferred Collection Hub': 'पसंदीदा संग्रह केंद्र',
            '-- Select Preferred Hub --': '-- संग्रह केंद्र चुनें --',
            'List Produce Batch': 'उपज बैच दर्ज करें',
            'List Upcoming Harvest': 'आगामी कटाई दर्ज करें',
            'Confirm & Lock Consignment Contract': 'अनुबंध की पुष्टि करें और लॉक करें',
            'Run Multi-Farmer Split Match': 'मल्टी-किसान मिलान चलाएं',
            'Add to Cart': 'कार्ट में जोड़ें',
            'Proceed to Checkout': 'चेकआउट करें',
            'Cancel': 'रद्द करें',
            'Submit': 'जमा करें',
            'Save Changes': 'बदलाव सहेजें',
            'Filter by Category': 'श्रेणी अनुसार फ़िल्टर करें',
            'All Crops': 'सभी फसलें',
            'Search produce or farm...': 'फसल या खेत खोजें...',
            'Order Produce': 'उत्पाद ऑर्डर करें',

            // Crop Names
            'Tomato': 'टमाटर',
            'Potato': 'आलू',
            'Onion': 'प्याज',
            'Carrot': 'गाजर',
            'Spinach': 'पालक',
            'Cabbage': 'पत्ता गोभी',
            'Cauliflower': 'फूलगोभी',
            'Green Chilli': 'हरी मिर्च',

            // Quality & Order Statuses
            'Grade A': 'ग्रेड A (प्रीमियम)',
            'Grade B': 'ग्रेड B (वाणिज्यिक)',
            'Grade C': 'ग्रेड C (प्रसंस्करण)',
            'Order Placed': 'ऑर्डर दर्ज',
            'Farmer Assigned': 'किसान आवंटित',
            'Collection': 'संग्रहण',
            'At Hub QA': 'हब गुणवत्ता जांच',
            'Packed': 'पैक किया गया',
            'Out for Delivery': 'वितरण हेतु रवाना',
            'Delivered': 'सफलतापूर्वक डिलीवर',
            'Cancelled': 'रद्द',
            'Pending': 'लंबित',
            'Paid': 'भुगतान पूर्ण',
            'Escrow Locked': 'एस्क्रो सुरक्षित',

            // Messages & Alerts
            'Language switched to Hindi': 'भाषा बदलकर हिन्दी कर दी गई है',
            'Order placed successfully!': 'ऑर्डर सफलतापूर्वक दर्ज किया गया!'
        },

        ml: {
            // Brand & Navigation
            'AgriSmart': 'അഗ്രിസ്മാർട്ട്',
            'Connect': 'കണക്ട്',
            'Core': 'കോർ',
            'Home': 'ഹോം',
            'How It Works': 'പ്രവർത്തനരീതി',
            'Role Portals': 'പോർട്ടലുകൾ',
            'Marketplace': 'വിപണി (Marketplace)',
            'AI Agronomist': 'AI കാർഷിക വിദഗ്ദ്ധൻ',
            'Smart IoT': 'സ്മാർട്ട് IoT',
            'Wholesale': 'മൊത്തവ്യാപാരം',
            'Retail Wholesale': 'റീട്ടെയിൽ മൊത്തവ്യാപാരം',
            'My Orders': 'എന്റെ ഓർഡറുകൾ',
            'Active Consignments': 'സജീവ ഓർഡറുകൾ',
            'Fulfillment Pipeline': 'വിതരണ പുരോഗതി',
            'Sign In': 'ലോഗിൻ ചെയ്യുക',
            'Get Started': 'ആരംഭിക്കുക',
            'Log Out': 'ലോഗ് ഔട്ട്',
            'Sign Out': 'ലോഗ് ഔട്ട്',
            'Register Store': 'സ്ഥാപനം രജിസ്റ്റർ ചെയ്യുക',
            'Join the Network': 'ശൃംഖലയിൽ ചേരുക',
            'Explore Portals': 'പോർട്ടലുകൾ കാണുക',
            'Explore Marketplace': 'വിപണി കാണുക',

            // Hero & Descriptions
            'Demand-Matched Agricultural Supply Platform': 'ആവശ്യാനുസരണം ബന്ധിപ്പിച്ച കാർഷിക വിതരണ പ്ലാറ്റ്ഫോം',
            'Next-Gen Agricultural Logistics': 'നവയുഗ കാർഷിക ലോജിസ്റ്റിക്സ്',
            'AgriSmart Connect matches farmer harvest schedules directly with real-time consumer and B2B demand. No speculative over-purchasing, zero spoilage, and verified quality through regional collection hubs.':
                'കർഷകരുടെ വിളവെടുപ്പ് ഉപഭോക്താക്കളുടെ ആവശ്യങ്ങളുമായി നേരിട്ട് ബന്ധിപ്പിക്കുന്നു. നഷ്ടമില്ലാത്ത നേരിട്ടുള്ള കാർഷിക വിതരണം.',

            // Roles
            'Farmers & Producers': 'കർഷകരും ഉൽപ്പാദകരും',
            'Direct Consumers': 'ഉപഭോക്താക്കൾ',
            'Retailers & Supermarkets': 'സൂപ്പർമാർക്കറ്റുകൾ',
            'Restaurants & Commercial': 'റെസ്റ്റോറന്റുകൾ',
            'Collection Hubs': 'ശേഖരണ കേന്ദ്രങ്ങൾ',
            'Quality Inspectors': 'ഗുണനിലവാര പരിശോധകർ',
            'Delivery Fleet': 'വിതരണ ശൃംഖല',
            'Platform Admin': 'അഡ്മിൻ',

            // Actions & Crops
            'Select Crop': 'വിള തിരഞ്ഞെടുക്കുക',
            '-- Select Crop --': '-- വിള തിരഞ്ഞെടുക്കുക --',
            'Select Variety': 'ഇനം തിരഞ്ഞെടുക്കുക',
            '-- Select Variety --': '-- ഇനം തിരഞ്ഞെടുക്കുക --',
            'Preferred Collection Hub': 'ശേഖരണ കേന്ദ്രം തിരഞ്ഞെടുക്കുക',
            'List Produce Batch': 'വിളവ് ചേർക്കുക',
            'Confirm & Lock Consignment Contract': 'കരാർ സ്ഥിരീകരിച്ച് ലോക്ക് ചെയ്യുക',
            'Add to Cart': 'കാർട്ടിലേക്ക് ചേർക്കുക',
            'Cancel': 'റദ്ദാക്കുക',
            'Submit': 'സമർപ്പിക്കുക',
            'Tomato': 'തക്കാളി',
            'Potato': 'ഉരുളക്കിഴങ്ങ്',
            'Onion': 'സവാള',
            'Carrot': 'കാരറ്റ്',
            'Spinach': 'ചീര',

            // Statuses
            'Grade A': 'ഗ്രേഡ് A (ഉയർന്നത്)',
            'Grade B': 'ഗ്രേഡ് B',
            'Order Placed': 'ഓർഡർ നൽകി',
            'Farmer Assigned': 'കർഷകനെ നിശ്ചയിച്ചു',
            'Delivered': 'വിതരണം ചെയ്തു',
            'Paid': 'പണം നൽകി'
        },

        te: {
            // Brand & Navigation
            'AgriSmart': 'అగ్రిస్మార్ట్',
            'Connect': 'కనెక్ట్',
            'Core': 'కోర్',
            'Home': 'హోమ్',
            'How It Works': 'ఎలా పనిచేస్తుంది',
            'Role Portals': 'పోర్టల్స్',
            'Marketplace': 'మార్కెట్‌ప్లేస్',
            'AI Agronomist': 'AI వ్యవసాయ నిపుణుడు',
            'Smart IoT': 'స్మార్ట్ IoT',
            'Wholesale': 'హోల్‌సేల్',
            'Retail Wholesale': 'చిల్లర హోల్‌సేల్',
            'My Orders': 'నా ఆర్డర్లు',
            'Active Consignments': 'కన్సైన్‌మెంట్లు',
            'Fulfillment Pipeline': 'డెలివరీ ట్రాకింగ్',
            'Sign In': 'లాగిన్',
            'Get Started': 'ప్రారంభించండి',
            'Log Out': 'లాగ్ అవుట్',
            'Sign Out': 'లాగ్ అవుట్',
            'Register Store': 'స్టోర్ నమోదు చేయండి',
            'Join the Network': 'నెట్‌వర్క్‌లో చేరండి',
            'Explore Portals': 'పోర్టల్‌లను చూడండి',
            'Explore Marketplace': 'మార్కెట్‌ప్లేస్ చూడండి',

            // Hero & Descriptions
            'Demand-Matched Agricultural Supply Platform': 'డిమాండ్-ఆధారిత వ్యవసాయ సరఫరా వేదిక',
            'Next-Gen Agricultural Logistics': 'నూతన తరం వ్యవసాయ లాజిస్టిక్స్',
            'AgriSmart Connect matches farmer harvest schedules directly with real-time consumer and B2B demand. No speculative over-purchasing, zero spoilage, and verified quality through regional collection hubs.':
                'రైతుల పంట కోత సమయాన్ని వినియోగదారుల డిమాండ్‌తో నేరుగా అనుసంధానించే వేదిక. నాణ్యమైన తాజా వ్యవసాయ ఉత్పత్తులు.',

            // Roles
            'Farmers & Producers': 'రైతులు మరియు ఉత్పత్తిదారులు',
            'Direct Consumers': 'ప్రత్యక్ష వినియోగదారులు',
            'Retailers & Supermarkets': 'సూపర్‌మార్కెట్లు',
            'Restaurants & Commercial': 'రెస్టారెంట్లు',
            'Collection Hubs': 'సేకరణ కేంద్రాలు',
            'Quality Inspectors': 'నాణ్యతా తనిఖీదారులు',
            'Delivery Fleet': 'డెలివరీ బృందం',
            'Platform Admin': 'అడ్మిన్',

            // Actions & Crops
            'Select Crop': 'పంటను ఎంచుకోండి',
            '-- Select Crop --': '-- పంటను ఎంచుకోండి --',
            'Select Variety': 'రకాన్ని ఎంచుకోండి',
            '-- Select Variety --': '-- రకాన్ని ఎంచుకోండి --',
            'Preferred Collection Hub': 'సేకరణ కేంద్రాన్ని ఎంచుకోండి',
            'List Produce Batch': 'ఉత్పత్తిని జోడించండి',
            'Confirm & Lock Consignment Contract': 'కాంట్రాక్ట్‌ను నిర్ధారించి లాక్ చేయండి',
            'Add to Cart': 'కార్ట్‌కు జోడించండి',
            'Cancel': 'రద్దు చేయండి',
            'Submit': 'సమర్పించండి',
            'Tomato': 'టమాటా',
            'Potato': 'బంగాళాదుంప',
            'Onion': 'ఉల్లిపాయ',
            'Carrot': 'క్యారెట్',
            'Spinach': 'పాలకూర',

            // Statuses
            'Grade A': 'గ్రేడ్ A (ప్రీమియం)',
            'Grade B': 'గ్రేడ్ B',
            'Order Placed': 'ఆర్డర్ చేయబడింది',
            'Farmer Assigned': 'రైతు కేటాయించబడింది',
            'Delivered': 'డెలివరీ పూర్తయింది',
            'Paid': 'చెల్లించబడింది'
        }
    };

    /**
     * Get Current Active Language
     */
    function getCurrentLanguage() {
        return localStorage.getItem(I18N_STORAGE_KEY) || 'en';
    }

    /**
     * Set Language & Re-render Translations
     */
    function setLanguage(langCode) {
        if (!LANGUAGES[langCode]) {
            langCode = 'en';
        }
        localStorage.setItem(I18N_STORAGE_KEY, langCode);
        applyTranslations(langCode);
        updateLanguageSelectorUI(langCode);

        // Show friendly notification if toast utility is ready
        if (typeof window.showToast === 'function') {
            const langObj = LANGUAGES[langCode];
            const msg = langCode === 'en'
                ? 'Language switched to English'
                : `Language switched to ${langObj.native} (${langObj.name})`;
            window.showToast(msg, 'success', 2500);
        }
    }

    /**
     * Translation Lookup Function for JavaScript code
     */
    function t(key, defaultText) {
        const lang = getCurrentLanguage();
        if (lang === 'en' || !DICTIONARY[lang]) {
            return defaultText || key;
        }
        return DICTIONARY[lang][key] || defaultText || key;
    }

    /**
     * Recursively Translate DOM Elements
     */
    function applyTranslations(lang) {
        document.documentElement.lang = lang;
        const dict = DICTIONARY[lang];

        // 1. Elements with explicit data-i18n attribute
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            if (lang === 'en') {
                if (el._originalText !== undefined) {
                    el.textContent = el._originalText;
                }
            } else if (dict && dict[key]) {
                if (el._originalText === undefined) {
                    el._originalText = el.textContent;
                }
                el.textContent = dict[key];
            }
        });

        // 2. Input / Textarea Placeholders
        document.querySelectorAll('input[placeholder], textarea[placeholder]').forEach(input => {
            const currentPh = input.getAttribute('placeholder');
            if (!input._origPlaceholder) {
                input._origPlaceholder = currentPh;
            }
            if (lang === 'en') {
                input.setAttribute('placeholder', input._origPlaceholder);
            } else if (dict && dict[input._origPlaceholder]) {
                input.setAttribute('placeholder', dict[input._origPlaceholder]);
            }
        });

        // 3. Automated text node replacement for common UI strings
        if (lang === 'en') {
            // Restore originals
            restoreOriginalText(document.body);
        } else if (dict) {
            translateTextNodes(document.body, dict);
        }
    }

    /**
     * Helper to walk DOM text nodes and replace matched strings
     */
    function translateTextNodes(node, dict) {
        if (!node) return;
        // Skip scripts, styles, inputs, SVGs
        const tag = (node.nodeName || '').toUpperCase();
        if (['SCRIPT', 'STYLE', 'CODE', 'PRE', 'TEXTAREA', 'INPUT', 'SELECT'].includes(tag)) {
            return;
        }

        if (node.nodeType === Node.TEXT_NODE) {
            const text = (node.nodeValue || '').trim();
            if (text && dict[text]) {
                if (node._originalValue === undefined) {
                    node._originalValue = node.nodeValue;
                }
                node.nodeValue = node.nodeValue.replace(text, dict[text]);
            }
        } else if (node.childNodes) {
            node.childNodes.forEach(child => translateTextNodes(child, dict));
        }
    }

    /**
     * Restore original English text nodes
     */
    function restoreOriginalText(node) {
        if (!node) return;
        if (node.nodeType === Node.TEXT_NODE) {
            if (node._originalValue !== undefined) {
                node.nodeValue = node._originalValue;
            }
        } else if (node.childNodes) {
            node.childNodes.forEach(child => restoreOriginalText(child));
        }
    }

    /**
     * Inject / Mount Language Selector Dropdown into Navbar & Floating Action
     */
    function renderLanguageWidgets() {
        const currentLang = getCurrentLanguage();

        // 1. Inject into Navbar right before or inside nav-actions
        injectNavbarSelector(currentLang);

        // 2. Inject floating corner language pill (accessible anywhere on screen)
        injectFloatingSelector(currentLang);
    }

    function injectNavbarSelector(currentLang) {
        // Check if already mounted
        if (document.getElementById('agrismart-navbar-lang-container')) {
            return;
        }

        const navActions = document.getElementById('nav-auth-actions');
        const navContainer = document.querySelector('.nav-container') || document.querySelector('.navbar');

        const wrapper = document.createElement('div');
        wrapper.id = 'agrismart-navbar-lang-container';
        wrapper.className = 'agrismart-lang-wrapper';
        wrapper.innerHTML = createSelectorHTML('nav-lang-select', currentLang);

        if (navActions && navActions.parentNode) {
            navActions.parentNode.insertBefore(wrapper, navActions);
        } else if (navContainer) {
            navContainer.appendChild(wrapper);
        }

        attachSelectorEvents('nav-lang-select');
    }

    function injectFloatingSelector(currentLang) {
        if (document.getElementById('agrismart-floating-lang-btn')) {
            return;
        }

        const floatDiv = document.createElement('div');
        floatDiv.id = 'agrismart-floating-lang-btn';
        floatDiv.className = 'agrismart-floating-lang';
        floatDiv.innerHTML = `
            <div class="lang-float-inner">
                <span class="lang-globe-icon">🌐</span>
                <select id="floating-lang-select" class="lang-select-native" aria-label="Change Language">
                    ${Object.entries(LANGUAGES).map(([code, obj]) => `
                        <option value="${code}" ${code === currentLang ? 'selected' : ''}>
                            ${obj.flag} ${obj.native} (${obj.name})
                        </option>
                    `).join('')}
                </select>
            </div>
        `;
        document.body.appendChild(floatDiv);

        attachSelectorEvents('floating-lang-select');
    }

    function createSelectorHTML(id, currentLang) {
        return `
            <div class="lang-selector-badge">
                <span style="font-size:1.1rem; line-height:1;">🌐</span>
                <select id="${id}" class="lang-select-input" aria-label="Language Selector">
                    ${Object.entries(LANGUAGES).map(([code, obj]) => `
                        <option value="${code}" ${code === currentLang ? 'selected' : ''}>
                            ${obj.flag} ${obj.native} (${obj.name})
                        </option>
                    `).join('')}
                </select>
            </div>
        `;
    }

    function attachSelectorEvents(selectId) {
        const select = document.getElementById(selectId);
        if (!select) return;

        select.addEventListener('change', (e) => {
            const newLang = e.target.value;
            setLanguage(newLang);
        });
    }

    function updateLanguageSelectorUI(lang) {
        ['nav-lang-select', 'floating-lang-select'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = lang;
        });
    }

    /**
     * Inject CSS Styles for Language Pickers
     */
    function injectStyles() {
        if (document.getElementById('agrismart-i18n-styles')) return;

        const style = document.createElement('style');
        style.id = 'agrismart-i18n-styles';
        style.textContent = `
            /* Navbar Language Selector */
            .agrismart-lang-wrapper {
                display: inline-flex;
                align-items: center;
                margin-right: 0.75rem;
            }

            .lang-selector-badge {
                display: flex;
                align-items: center;
                gap: 0.35rem;
                background: var(--white, #fff);
                border: 1px solid var(--slate-200, #e2e8f0);
                padding: 0.35rem 0.65rem;
                border-radius: var(--radius-full, 9999px);
                box-shadow: 0 1px 2px rgba(0,0,0,0.04);
                transition: all 0.2s ease;
            }

            .lang-selector-badge:hover {
                border-color: var(--primary, #15803d);
                box-shadow: 0 2px 6px rgba(21,128,61,0.15);
            }

            .lang-select-input {
                background: transparent;
                border: none;
                font-family: inherit;
                font-size: 0.82rem;
                font-weight: 600;
                color: var(--slate-700, #334155);
                cursor: pointer;
                outline: none;
                padding-right: 0.25rem;
            }

            .lang-select-input:focus {
                color: var(--primary, #15803d);
            }

            /* Floating Quick Switcher (Bottom Right) */
            .agrismart-floating-lang {
                position: fixed;
                bottom: 20px;
                right: 20px;
                z-index: 9999;
                background: var(--white, #ffffff);
                border: 1px solid var(--slate-200, #e2e8f0);
                border-radius: 9999px;
                padding: 0.35rem 0.75rem;
                box-shadow: 0 4px 14px rgba(15,23,42,0.12);
                display: flex;
                align-items: center;
                gap: 0.4rem;
                transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            }

            .agrismart-floating-lang:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(21,128,61,0.2);
                border-color: var(--primary, #15803d);
            }

            .lang-float-inner {
                display: flex;
                align-items: center;
                gap: 0.4rem;
            }

            .lang-globe-icon {
                font-size: 1.15rem;
                line-height: 1;
            }

            .lang-select-native {
                border: none;
                background: transparent;
                font-family: inherit;
                font-size: 0.82rem;
                font-weight: 700;
                color: var(--slate-800, #1e293b);
                cursor: pointer;
                outline: none;
            }

            @media (max-width: 768px) {
                .agrismart-lang-wrapper {
                    margin-right: 0.25rem;
                }
                .agrismart-floating-lang {
                    bottom: 15px;
                    right: 15px;
                    padding: 0.3rem 0.55rem;
                }
            }
        `;
        document.head.appendChild(style);
    }

    // Initialize upon DOM readiness
    function init() {
        injectStyles();
        const currentLang = getCurrentLanguage();
        renderLanguageWidgets();
        if (currentLang !== 'en') {
            applyTranslations(currentLang);
        }

        // Mutation Observer to auto-translate dynamic cards/lists loaded by async APIs
        let observerTimeout = null;
        const observer = new MutationObserver(() => {
            const activeLang = getCurrentLanguage();
            if (activeLang !== 'en') {
                if (observerTimeout) clearTimeout(observerTimeout);
                observerTimeout = setTimeout(() => {
                    applyTranslations(activeLang);
                }, 150);
            }
        });

        observer.observe(document.body, { childList: true, subtree: true });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Expose global helpers
    window.AgriSmartI18n = {
        setLanguage,
        getCurrentLanguage,
        t,
        LANGUAGES
    };
})();
