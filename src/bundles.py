"""Everyday words for industries (user reviews, 3 Nov 2026: "AI" found cattle farming; "coffee", "barber", "gym" found
nothing). BUNDLES are ready-made, approximate code sets a user can ask for by id; WORDS map an everyday word to the
code(s) for that one activity, whose descriptions find_sic shows. Codes are 5-digit SIC 2007 or a 2-4 digit group;
tests check every one exists in the data. Review codex-bundles.md: a bundle's main limit goes in the answer's first
sentence (`short`), the full note in a caveat, and trigger words must not promise more than the codes cover. A
trigger starting "=" matches only the whole query ("online", not "online business").
"""

# id: (label, codes, short limit for the summary, full note for a caveat, words that find it)
BUNDLES: dict[str, tuple[str, list[str], str, str, list[str]]] = {
    "ai-and-data": (
        "AI, software and data", ["62012", "62020", "62090", "63110", "72190"],
        "a proxy, as there is no SIC code for AI, so most companies counted aren't AI companies",
        "There is no SIC code for AI. These codes cover software, IT consultancy and services, data processing and other "
        "research, so most companies counted aren't AI companies, and AI companies filed under other codes are missed.",
        ["ai", "artificial intelligence", "machine learning", "ml", "llm", "generative ai", "data science",
         "data scientist", "ai startup"]),
    "tech-and-software": (
        "tech and software", ["62011", "62012", "62020", "62030", "62090", "63110", "63120", "58210", "58290"],
        "software, games, IT services, hosting and web portals; tech firms filed by the sector they serve are missed",
        "Software, games, IT services and facilities management, hosting and web portals. Tech companies that list "
        "what they sell or the sector they serve (for example finance or retail) are missed. There is no code for "
        "cybersecurity: such firms usually use these codes.",
        ["tech", "technology", "software", "saas", "it", "app", "apps", "tech startup", "cybersecurity",
         "cyber security"]),
    "ecommerce": (
        "e-commerce and online shops", ["47910"],
        "only companies whose stated activity is online or mail-order selling; brands that list what they sell are missed",
        "Only companies whose stated activity is selling online or by mail order. Many online brands list what they "
        "sell instead (clothing is 47710), so they are missed.",
        ["e commerce", "ecommerce", "=online", "online shop", "online store", "online retail", "online seller",
         "online selling", "selling online", "sell online",
         "dropshipping", "amazon seller"]),
    "cafes-and-coffee-shops": (
        "cafés and coffee shops", ["56102"],
        "unlicensed restaurants and cafés, so it also counts other restaurants without an alcohol licence",
        "Unlicensed restaurants and cafés, so it also counts other restaurants without an alcohol licence. Coffee vans "
        "and kiosks may be filed as take-away (56103).",
        ["coffee", "coffee shop", "cafe", "tea room", "coffee house"]),
    "restaurants-and-takeaways": (
        "restaurants and takeaways", ["56101", "56102", "56103"],
        "licensed and unlicensed restaurants, cafés and take-aways",
        "Licensed and unlicensed restaurants, cafés, take-aways and food stands. Event catering and pubs are not included.",
        ["restaurant", "eatery"]),
    "pubs-and-bars": (
        "pubs, bars and licensed clubs", ["56301", "56302"],
        "pubs, bars and licensed clubs; pubs run by a chain usually aren't new companies",
        "Licensed clubs, pubs and bars. Pubs run by a chain are usually branches of one company, so they don't appear "
        "as new companies. Nightclubs may use these codes or others.", ["pub", "bar"]),
    "hospitality": (
        "hospitality (accommodation and food)", ["55", "56"],
        "every accommodation and food and drink service code",
        "Hotels, holiday lets and other accommodation, plus every food and drink service.",
        ["hospitality", "hotel and restaurant"]),
    "beauty-and-wellbeing": (
        "hair, beauty and well-being", ["96020", "96040"],
        "hairdressing and beauty plus spas and massage; it can't separate barbers, nails or beauty",
        "Hairdressing and other beauty treatment (barbers, nails and beauty share one code), plus spas, massage and "
        "other physical well-being. Many are sole traders, who aren't on the register.",
        ["beauty", "salon", "spa", "aesthetics", "wellbeing", "well being", "massage"]),
    "fitness-and-sport": (
        "fitness and sport", ["93130", "93199"],
        "fitness facilities plus all other sports activities, not just gyms",
        "Fitness facilities, plus other sports activities (which personal trainers often use, along with sports clubs "
        "and events). Many trainers are sole traders, who aren't on the register.",
        ["fitness", "personal trainer", "pilates", "yoga", "fitness studio"]),
    "construction": (
        "construction and building trades", ["41", "42", "43"],
        "every building, civil engineering and specialist trade code",
        "Building, civil engineering and every specialist trade (electricians, plumbers, roofers and so on).",
        ["construction", "builder", "building trade", "trades", "tradesman", "tradespeople"]),
    "property": (
        "property", ["68"],
        "all of division 68: buying, letting and managing any property, and estate agents; many are one landlord's "
        "holding company",
        "Buying, letting and managing property, and estate and letting agents. Many are holding companies for one "
        "landlord's homes.", ["property", "real estate", "landlord", "buy to let", "property investment"]),
    "recruitment": (
        "recruitment and staffing", ["78109", "78200", "78300"],
        "recruitment agencies, temporary staffing and HR outsourcing",
        "Recruitment agencies, temporary staffing and HR outsourcing. Casting agencies (78101) are not included.",
        ["recruitment", "recruiter", "staffing", "temp agency", "headhunter"]),
    "couriers-and-haulage": (
        "couriers and road haulage", ["53201", "53202", "49410"],
        "couriers and road freight; warehousing and freight forwarding are not included",
        "Couriers and road freight. Warehousing and freight forwarding are in the logistics bundle. Many delivery "
        "drivers are sole traders, who aren't on the register.",
        ["courier", "delivery", "haulage", "haulier", "last mile"]),
    "logistics": (
        "logistics", ["49410", "52101", "52102", "52103", "52290", "53201", "53202"],
        "road freight, warehousing, couriers and other transport support, which may include freight forwarding",
        "Road freight, warehousing and storage, couriers, and other transport support activities (52290), which may "
        "include freight forwarding but isn't only that. Rail, sea and air transport are not included.",
        ["logistics", "freight", "freight forwarder", "freight forwarding", "warehousing", "warehouse"]),
    "care": (
        "residential and home care", ["87", "88100"],
        "every residential care code plus home care for older and disabled people; children's social work is not included",
        "Nursing homes and every kind of residential care, plus home care and other social work for older and disabled "
        "people. Children's social work, day centres and charities' other social work are not included.",
        ["care home", "home care", "domiciliary care", "elderly care", "nursing home", "carer"]),
    "creative-and-content": (
        "creative, media and content", ["90030", "73110", "59111", "59112", "59113", "74100", "74209"],
        "a selected mix of art, advertising, film and video, design and photography; content creators have no code",
        "Artistic creation, advertising agencies, film and video production, design and photography: a selected mix, "
        "not all media. There is no code for content creators or influencers: they use any of these, or others.",
        ["content creator", "influencer", "youtuber", "creative agency", "media production", "videographer"]),
    "marketing": (
        "marketing and PR", ["73110", "73120", "70210"],
        "advertising agencies, media buying and PR",
        "Advertising agencies, media buying, and public relations. Marketing consultants filed as management "
        "consultancy (70229) are missed.",
        ["marketing", "digital marketing", "pr agency", "advertising", "social media agency", "marketing agency"]),
    "consultancy": (
        "management consultancy", ["70229"],
        "management consultancy other than financial; IT and engineering consultancies are missed",
        "Management consultancy other than financial. IT and engineering consultancies use their own codes.",
        ["consultancy", "consulting", "management consultant"]),
    "fintech-and-finance": (
        "two catch-all finance codes", ["64999", "66190"],
        "a narrow proxy, not a count of fintech companies: two catch-all finance codes, which also hold other finance firms",
        "There is no SIC code for fintech or crypto. These are two catch-all financial-service codes, so they also "
        "count other finance firms, and fintechs filed as software (62012), payments or banking are missed.",
        ["fintech"]),
    "second-hand-and-vintage": (
        "second-hand and antique shops", ["47799", "47791"],
        "second-hand and antique shops; online resellers usually file under clothing or online retail and are missed",
        "Shops selling second-hand goods and antiques. Online resellers often list clothing (47710) or online retail "
        "(47910) instead, and most resellers are sole traders, who aren't on the register.",
        ["second hand", "vintage", "resale", "reseller", "thrift", "antique", "preloved", "charity shop"]),
    "vape-and-tobacco": (
        "specialist tobacco shops (some vape shops)", ["47260"],
        "specialist tobacco retail, which only some vape shops use; the rest are missed",
        "Specialist tobacco retail, which some vape shops use. Vape shops filed as other specialist retail (47789) "
        "are missed.", ["vape", "vape shop", "vaping", "e cigarette", "tobacconist"]),
    "renewables": (
        "electricity and electrical installation", ["35110", "43210"],
        "electricity producers and all electrical installers; it can't isolate solar or renewables",
        "Production of electricity (from any source) and all electrical installation. There is no code for solar or "
        "renewables, so most installers counted fit other kinds of electrical work.",
        ["solar", "renewable", "renewable energy", "green energy", "solar panel"]),
    "cleaning": (
        "cleaning", ["812"],
        "every cleaning code, including pest control",
        "Every cleaning code: buildings, windows, specialist and industrial cleaning, pest control and others.",
        ["cleaning", "cleaner", "cleaning company"]),
    "accountancy": (
        "accountants and bookkeepers", ["69201", "69202", "69203"],
        "accounting and auditing, bookkeeping and tax advice",
        "Accounting and auditing, bookkeeping and tax advice.",
        ["accountant", "accountancy", "bookkeeper", "bookkeeping", "tax adviser"]),
}

# Batch A4: plain names for the 2-digit SIC 2007 divisions, for breakdown_by_industry's rows
DIVISIONS: dict[str, str] = {
    "01": "crop and animal farming, hunting and related services", "02": "forestry and logging", "03": "fishing and fish farming", "05": "coal mining",
    "06": "oil and gas extraction", "07": "metal ore mining", "08": "quarrying and other mining",
    "09": "mining support services", "10": "food manufacturing", "11": "drinks manufacturing",
    "12": "tobacco manufacturing", "13": "textile manufacturing", "14": "clothing manufacturing",
    "15": "leather goods and footwear manufacturing", "16": "wood products (not furniture)",
    "17": "paper and paper products", "18": "printing", "19": "coke and refined petroleum products",
    "20": "chemicals", "21": "pharmaceuticals", "22": "rubber and plastic products",
    "23": "glass, ceramics, cement and stone products", "24": "basic metals", "25": "metal products (not machinery)",
    "26": "computers, electronics and optical products", "27": "electrical equipment", "28": "machinery",
    "29": "motor vehicles and parts", "30": "other transport equipment", "31": "furniture making",
    "32": "other manufacturing", "33": "machinery repair and installation", "35": "electricity and gas supply",
    "36": "water supply", "37": "sewerage", "38": "waste collection, treatment and recycling",
    "39": "remediation and other waste management", "41": "building construction", "42": "civil engineering",
    "43": "specialist building trades", "45": "motor trade and vehicle repair", "46": "wholesale",
    "47": "retail (not motor vehicles)", "49": "road and rail transport", "50": "water transport",
    "51": "air transport", "52": "warehousing and transport support", "53": "postal and courier services",
    "55": "accommodation", "56": "food and drink services (restaurants, cafés, pubs)", "58": "publishing",
    "59": "film, TV, video and music production", "60": "broadcasting", "61": "telecommunications",
    "62": "computer programming and IT consultancy", "63": "information services (data processing, web portals)",
    "64": "financial services (not insurance)", "65": "insurance and pensions",
    "66": "services auxiliary to finance and insurance", "68": "property", "69": "legal and accounting",
    "70": "head offices and management consultancy", "71": "architecture, engineering and technical testing",
    "72": "scientific research and development", "73": "advertising and market research",
    "74": "other professional services (design, photography, translation)", "75": "veterinary",
    "77": "rental and leasing", "78": "recruitment and staffing", "79": "travel agencies and tour operators",
    "80": "security and investigation", "81": "building services, cleaning and landscaping",
    "82": "office support and other business support", "84": "public administration and defence",
    "85": "education", "86": "health", "87": "residential care", "88": "social work without accommodation",
    "90": "creative arts and entertainment", "91": "libraries, museums and other culture", "92": "gambling and betting",
    "93": "sport, fitness and recreation", "94": "membership organisations", "95": "repair of computers and household goods",
    "96": "other personal services (hairdressing, beauty, laundry)", "97": "households employing domestic staff",
    "98": "residents property management, and households producing for their own use", "99": "international organisations",
    "none": "no activity stated or dormant",
}

# everyday word: the code(s) for that one activity (find_sic shows each code's own description)
WORDS: dict[str, list[str]] = {
    "barber": ["96020"], "hairdresser": ["96020"], "hair salon": ["96020"], "nail": ["96020"], "nail salon": ["96020"],
    "gym": ["93130"], "electrician": ["43210"], "plumber": ["43220"], "plumbing": ["43220"], "decorator": ["43341"],
    "painter": ["43341"], "takeaway": ["56103"], "take away": ["56103"], "food truck": ["56103"],
    "childcare": ["88910"], "nursery": ["88910"], "taxi": ["49320"], "vet": ["75000"], "dentist": ["86230"],
    "gp": ["86210"], "tutor": ["85590"], "tutoring": ["85590"], "photographer": ["74209"],
    "dog grooming": ["96090"], "tattoo": ["96090"], "gardener": ["81300"], "landscaper": ["81300"],
    "landscaping": ["81300"], "hotel": ["55100"], "mechanic": ["45200"], "garage": ["45200"], "car repair": ["45200"],
    "estate agent": ["68310"], "letting agent": ["68310", "68320"], "architect": ["71111"], "solicitor": ["69102"],
    "lawyer": ["69102"], "bakery": ["10710", "47240"], "baker": ["10710", "47240"], "jeweller": ["47770", "32120"],
    "jewellery": ["47770", "32120"], "florist": ["47760"], "pet shop": ["47760"], "dry cleaner": ["96010"],
    "laundrette": ["96010"], "clothing": ["47710"], "clothes shop": ["47710"],
    "biotech": ["72110"], "conference organiser": ["82302"], "exhibition organiser": ["82301"],
    "security guard": ["80100"], "security company": ["80100"], "funeral": ["96030"], "removals": ["49420"],
    "driving school": ["85530"],
}
