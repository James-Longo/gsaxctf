"""
school_catalog_seed.py - hand-curated identity facts for the school catalog.

This file is the human-editable source of truth that build_school_catalog.py
expands into backend/data/school_catalog.json. Everything here is a FACT about
an institution (its name, town, official MPA name, the abbreviations and
mascots it is printed under, co-op memberships), never a guess about one
particular results file. Per-file evidence (athlete continuity, team-score
blocks) is computed by the builder, not written here.

Conventions
-----------
id          stable, lowercase: me-hs-*, me-ms-*, col-*, oos-<st>-*, club-*, x-*
names       full / official forms. A Hy-Tek truncation of any of these
            (first N chars, N>=4) resolves to the school when unique.
aliases     other spellings that mean exactly this school at its level
            (matched after normalisation, never truncated).
codes       short abbreviations as printed ('MTA', 'GNG'). Codes are
            ambiguous by nature: the builder accepts a code only when athlete
            continuity in that file does not contradict it.
nicknames   mascots ('Red Eddies'). Same treatment as codes.
mpa         the school's name in the MPA classification lists.
years       [first, last] ACADEMIC year the school existed under this identity
            (None = open-ended). Academic year: XC season-year Y -> Y; Indoor and
            Outdoor season-year Y -> Y-1 (the fall the school year started). A
            name match outside these years is rejected ('Elan' after 2011 is a
            parse error, 'SMHS' before 2011 cannot be Spruce Mountain).
"""

import re as _re

# ---------------------------------------------------------------------------
# Maine high schools (MPA members and other Maine secondary schools)
# (id, display name, town, mpa name, names/aliases, codes, nicknames, extra)
# ---------------------------------------------------------------------------
ME_HS = [
    # 2026-10-24 store-team review: small schools printed in XC meets and missing from the catalog
    ('me-hs-vineyard-christian', 'Vineyard Christian', None, None, ['Vineyard Christian', 'Vinyard'], [], [], {}),   # scored team, 2010-11 MVC meets
    ('me-hs-lfca', 'Lisbon Falls Christian Academy', 'Lisbon Falls', None,
     ['Lisbon Falls Christian Academy', 'Lisbon Falls Christian', 'LFCA'], [], [], {}),
    ('me-hs-acadia-christian', 'Acadia Christian', None, None, ['Acadia Christian'], [], [], {}),
    # --- Class A (XC 2026-27) ---
    ('me-hs-edward-little', 'Edward Little High School', 'Auburn', 'Edward Little',
     ['Edward Little', 'Edward Little HS', 'Edward Little High', 'Edward Littl'],
     ['EL', 'ELHS', 'ELH', 'EDLI'], ['Red Eddies', 'Eddies'], {}),
    ('me-hs-lewiston', 'Lewiston High School', 'Lewiston', 'Lewiston',
     ['Lewiston', 'Lewiston HS', 'Lewiston High'], ['LHS', 'LEW', 'LEWI', 'LEWS'], ['Blue Devils'], {}),
    ('me-hs-bangor', 'Bangor High School', 'Bangor', 'Bangor',
     ['Bangor', 'Bangor HS', 'Bangor High'], ['BAN', 'BANG', 'BGR'], ['Rams'], {}),
    ('me-hs-oxford-hills', 'Oxford Hills Comprehensive High School', 'South Paris', 'Oxford Hills',
     ['Oxford Hills', 'Oxford Hills HS', 'Oxford Hills High School', 'Ox Hills', 'OxHills',
      'Oxford Hills Comprehensive'], ['OHHS', 'OXHL', 'OXH', 'OHCHS', 'OXFO'], ['Vikings'], {}),
    ('me-hs-hampden', 'Hampden Academy', 'Hampden', 'Hampden',
     ['Hampden Academy', 'Hampden', 'Hampden Acad', 'Hamden Academy'], ['HA', 'HAMP', 'HAM'], ['Broncos'], {}),
    ('me-hs-camden-hills', 'Camden Hills Regional High School', 'Rockport', 'Camden Hills',
     ['Camden Hills', 'Camden Hills Regional', 'Camden Hills HS', 'Camden Hills High School'],
     ['CHRHS', 'CHHS', 'CHR', 'CAMH'], ['Windjammers'], {}),
    ('me-hs-brunswick', 'Brunswick High School', 'Brunswick', 'Brunswick',
     ['Brunswick', 'Brunswick HS', 'Brunswick High'], ['BRUN', 'BRU', 'BHS'], ['Dragons'], {}),
    ('me-hs-messalonskee', 'Messalonskee High School', 'Oakland', 'Messalonskee',
     ['Messalonskee', 'Messalonskee HS', 'Messalonskeee', 'Messalonske'], ['MESS', 'MESSO', 'MHS'], ['Eagles'], {}),
    ('me-hs-mt-ararat', 'Mt. Ararat High School', 'Topsham', 'Mt. Ararat',
     ['Mt. Ararat', 'Mount Ararat', 'Mt Ararat', 'Mt. Ararat HS', 'Mt. Ararat High',
      'Mount Ararat High School',
      # 2026-10-19: 'Ararat' (Mt. Blue relays 2018, Waterville 2012 HS meets), 'Mt, Ararat' (Mt. Blue 2019)
      'Ararat', 'Mt, Ararat'], ['MTA', 'MAHS', 'MTAR'], ['Eagles'], {}),
    ('me-hs-skowhegan', 'Skowhegan Area High School', 'Skowhegan', 'Skowhegan',
     ['Skowhegan', 'Skowhegan Area', 'Skowhegan HS', 'Skowhegan High School', 'Skowhegan Area HS'],
     ['SAHS', 'SKOW', 'SKW', 'SKOH'], ['Indians', 'River Hawks'], {}),
    ('me-hs-brewer', 'Brewer High School', 'Brewer', 'Brewer',
     ['Brewer', 'Brewer HS', 'Brewer High'], ['BRW', 'BREW', 'BRHS'], ['Witches'], {}),
    ('me-hs-mt-blue', 'Mt. Blue High School', 'Farmington', 'Mt. Blue',
     ['Mt. Blue', 'Mount Blue', 'Mt Blue', 'Mt. Blue HS', 'Mount Blue High School',
      'Mt. Blue Track and Field'], ['MTB', 'MTBL', 'MBHS', 'MB'], ['Cougars'], {}),
    ('me-hs-thornton', 'Thornton Academy', 'Saco', 'Thornton',
     ['Thornton Academy', 'Thornton', 'Thornton Acad', 'Thorton Academy', 'Thronton', 'Thiornton'],
     ['TA', 'THOR', 'THOA', 'THA'], ['Golden Trojans', 'Trojans'], {}),
    ('me-hs-portland', 'Portland High School', 'Portland', 'Portland',
     ['Portland', 'Portland HS', 'Portland High', 'Portlandd'], ['PHS', 'PORT', 'PTLD'], ['Bulldogs'], {}),
    ('me-hs-sanford', 'Sanford High School', 'Sanford', 'Sanford',
     ['Sanford', 'Sanford HS', 'Sanford High'], ['SHS', 'SANF', 'SANH', 'SAN'], ['Spartans'], {}),
    ('me-hs-bonny-eagle', 'Bonny Eagle High School', 'Standish', 'Bonny Eagle',
     ['Bonny Eagle', 'Bonny Eagle HS', 'Bonny Eagle High'], ['BE', 'BEHS', 'BONN'], ['Scots'], {}),
    ('me-hs-deering', 'Deering High School', 'Portland', 'Deering',
     ['Deering', 'Deering HS', 'Deering High'], ['DHS', 'DEER', 'DEE'], ['Rams'], {}),
    ('me-hs-south-portland', 'South Portland High School', 'South Portland', 'South Portland',
     ['South Portland', 'South Portland HS', 'So. Portland', 'So Portland', 'S. Portland', 'SP Red Riots'],
     ['SP', 'SPHS', 'SOPO'], ['Red Riots', 'Riots'], {}),
    ('me-hs-noble', 'Noble High School', 'North Berwick', 'Noble',
     ['Noble', 'Noble HS', 'Noble High'], ['NHS', 'NOBL', 'NOB'], ['Knights'], {}),
    ('me-hs-windham', 'Windham High School', 'Windham', 'Windham',
     ['Windham', 'Windham HS', 'Windham High', 'Windham Boys Indoor Track', 'Windham Girls Indoor Track'],
     ['WHS', 'WIND', 'WINDH'], ['Eagles'], {}),
    ('me-hs-scarborough', 'Scarborough High School', 'Scarborough', 'Scarborough',
     ['Scarborough', 'Scarborough HS', 'Scarborough High', 'Scarboro', 'Scarboro HS'],
     ['SCAR', 'SHS', 'SCARB'], ['Red Storm'], {}),
    ('me-hs-massabesic', 'Massabesic High School', 'Waterboro', 'Massabesic',
     ['Massabesic', 'Massabesic HS', 'Massabesic High'], ['MASS', 'MHS', 'MASH'], ['Mustangs'], {}),
    ('me-hs-gorham', 'Gorham High School', 'Gorham', 'Gorham',
     ['Gorham', 'Gorham HS', 'Gorham High'], ['GHS', 'GORH', 'GOR'], ['Rams'], {}),
    ('me-hs-biddeford', 'Biddeford High School', 'Biddeford', 'Biddeford',
     ['Biddeford', 'Biddeford HS', 'Biddeford High'], ['BIDD', 'BIDH', 'BHS', 'BIDDOT&F', 'BIDDT&F', 'BIDDTF'], ['Tigers'], {}),
    ('me-hs-kennebunk', 'Kennebunk High School', 'Kennebunk', 'Kennebunk',
     ['Kennebunk', 'Kennebunk HS', 'Kennebunk High'], ['KHS', 'KENN', 'KENH', 'KHSTF', 'KHSIT', 'KEN'], ['Rams'], {}),
    ('me-hs-marshwood', 'Marshwood High School', 'South Berwick', 'Marshwood',
     ['Marshwood', 'Marshwood HS', 'Marshwood High', 'Marshwood Indoor Track'], ['MARS', 'MARSH', 'MHS'], ['Hawks'], {}),
    ('me-hs-westbrook', 'Westbrook High School', 'Westbrook', 'Westbrook',
     ['Westbrook', 'Westbrook HS', 'Westbrook High', 'Westbrook High School Boys', 'Westbrook High School Girls'],
     ['WEST', 'WEHS', 'WHS'], ['Blue Blazes'], {}),
    ('me-hs-falmouth', 'Falmouth High School', 'Falmouth', 'Falmouth',
     ['Falmouth', 'Falmouth HS', 'Falmouth High'], ['FHS', 'FAL', 'FALH', 'FALM'], ['Yachtsmen', 'Navigators'], {}),
    ('me-hs-fryeburg', 'Fryeburg Academy', 'Fryeburg', 'Fryeburg',
     ['Fryeburg Academy', 'Fryeburg', 'Fryeburg Acad'], ['FA', 'FRYE', 'FRY'], ['Raiders'], {}),
    ('me-hs-cheverus', 'Cheverus High School', 'Portland', 'Cheverus',
     ['Cheverus', 'Cheverus HS', 'Cheverus High', 'Chevrus High Sch', 'Chevrus'], ['CHEV', 'CHS'], ['Stags'], {}),
    # --- Class B ---
    ('me-hs-cony', 'Cony High School', 'Augusta', 'Cony',
     ['Cony', 'Cony HS', 'Cony High', 'Cony Rams'], ['CONY', 'CNY', 'CON'], ['Rams'], {}),
    ('me-hs-nokomis', 'Nokomis Regional High School', 'Newport', 'Nokomis',
     ['Nokomis', 'Nokomis Regional', 'Nokomis HS', 'Nokomis High School', 'Nokomis High', 'Nekomis'],
     ['NOK', 'NOKO', 'NRHS'], ['Warriors'], {}),
    ('me-hs-gardiner', 'Gardiner Area High School', 'Gardiner', 'Gardiner',
     ['Gardiner', 'Gardiner Area', 'Gardiner HS', 'Gardiner High School', 'Gardiner High', 'Gardner High Sch',
      'Gardner High School'], ['GAHS', 'GAR', 'GARD', 'GHS'], ['Tigers'], {}),
    ('me-hs-hermon', 'Hermon High School', 'Hermon', 'Hermon',
     ['Hermon', 'Hermon HS', 'Hermon High', 'Hawks-Hermon', 'Hawks/Hermon', 'Hawks (Hermon)', 'Hermon Track Club',
      'Hemon Track Club', 'Hawks Track Club'], ['HER', 'HERM', 'HHS'], ['Hawks'], {}),
    ('me-hs-medomak', 'Medomak Valley High School', 'Waldoboro', 'Medomak Valley',
     ['Medomak Valley', 'Medomak', 'Medomak Valley HS', 'MedomakValley', 'Med Valley', 'Medval', 'Merdomak',
      'Medomak High School'], ['MVHS', 'MED', 'MEDO'], ['Panthers'], {}),
    ('me-hs-old-town', 'Old Town High School', 'Old Town', 'Old Town',
     ['Old Town', 'Old Town HS', 'Old Town High'], ['OTHS', 'OT', 'OLDT'], ['Coyotes'], {}),
    ('me-hs-erskine', 'Erskine Academy', 'South China', 'Erskine',
     ['Erskine Academy', 'Erskine', 'Erskine Acad', 'Erskin Academy'], ['EA', 'ERSK', 'ERS'], ['Eagles'], {}),
    ('me-hs-lawrence', 'Lawrence High School', 'Fairfield', 'Lawrence',
     ['Lawrence', 'Lawrence HS', 'Lawrence High'], ['LHS', 'LAWR', 'LAW'], ['Bulldogs'], {}),
    ('me-hs-ellsworth', 'Ellsworth High School', 'Ellsworth', 'Ellsworth',
     ['Ellsworth', 'Ellsworth HS', 'Ellsworth High'], ['EHS', 'ELLS', 'ELL'], ['Eagles'], {}),
    ('me-hs-john-bapst', 'John Bapst Memorial High School', 'Bangor', 'John Bapst',
     ['John Bapst', 'John Bapst Memorial', 'John Bapst HS', 'John Bapst Memorial HS', 'J Bapst', 'John Bapst MHS',
      'John Bapst High School', 'Bapst Crusaders', 'Bapst'], ['JB', 'JBMHS', 'JBAP'], ['Crusaders'], {}),
    ('me-hs-oceanside', 'Oceanside High School', 'Rockland', 'Oceanside',
     ['Oceanside', 'Oceanside HS', 'Oceanside High'], ['OHS', 'OCEAN', 'OCE'], ['Mariners'], {'years': [2011, None], 'notes': 'Formed fall 2011 from Rockland + Georges Valley.'}),
    ('me-hs-waterville', 'Waterville Senior High School', 'Waterville', 'Waterville',
     ['Waterville', 'Waterville HS', 'Waterville High School', 'Waterville High', 'Waterville Shs',
      'Waterville Senior High'], ['WTVL', 'WHS', 'WAT'], ['Purple Panthers'], {}),
    ('me-hs-mdi', 'Mount Desert Island High School', 'Bar Harbor', 'Mt. Desert',
     ['Mount Desert Island', 'Mt. Desert Island', 'Mt Desert Island', 'Mount Desert', 'Mt. Desert', 'Mt Desert',
      'Mount Desert Island HS', 'Mt. Desert Island HS', 'MDI High School', 'MDI HS', 'Mount Desert Island HighSchool',
      'Mount Desert Island Highschool'], ['MDI', 'MDIHS'], ['Trojans'], {}),
    ('me-hs-belfast', 'Belfast Area High School', 'Belfast', 'Belfast',
     ['Belfast', 'Belfast Area', 'Belfast HS', 'Belfast High School', 'Belfast Area HS'], ['BAHS', 'BELF', 'BEL'], ['Lions'], {}),
    ('me-hs-presque-isle', 'Presque Isle High School', 'Presque Isle', 'Presque Isle',
     ['Presque Isle', 'Presque Isle HS', 'Presque Isle High'], ['PI', 'PIHS'], ['Wildcats'], {}),
    ('me-hs-foxcroft', 'Foxcroft Academy', 'Dover-Foxcroft', 'Foxcroft',
     ['Foxcroft Academy', 'Foxcroft', 'Foxcroft Acad'], ['FA', 'FOX', 'FOXC'], ['Ponies'], {}),
    ('me-hs-caribou', 'Caribou High School', 'Caribou', 'Caribou',
     ['Caribou', 'Caribou HS', 'Caribou High'], ['CAR', 'CHS', 'CARI'], ['Vikings'], {}),
    ('me-hs-freeport', 'Freeport High School', 'Freeport', 'Freeport',
     ['Freeport', 'Freeport HS', 'Freeport High', 'Freeport Falcons'], ['FREE', 'FHS'], ['Falcons'], {}),
    ('me-hs-morse', 'Morse High School', 'Bath', 'Morse',
     ['Morse', 'Morse HS', 'Morse High', 'Morse Shipbuilders', 'Morse Shipbuilers'], ['MOR', 'MORS', 'MORSE', 'MHS'],
     ['Shipbuilders'], {}),
    ('me-hs-greely', 'Greely High School', 'Cumberland', 'Greely',
     ['Greely', 'Greely HS', 'Greely High', 'Greeley'], ['GHS', 'GREE', 'GRE'], ['Rangers'], {}),
    ('me-hs-gray-ng', 'Gray-New Gloucester High School', 'Gray', 'Gray-New Gloucester',
     ['Gray-New Gloucester', 'Gray New Gloucester', 'Gray-NG', 'Gray NG', 'Gray-Ng', 'Gray-New Glouches'],
     ['GNG', 'GNGHS', 'GNGH'], ['Patriots'], {}),
    ('me-hs-yarmouth', 'Yarmouth High School', 'Yarmouth', 'Yarmouth',
     ['Yarmouth', 'Yarmouth HS', 'Yarmouth High'], ['YHS', 'YAR', 'YARM'], ['Clippers'], {}),
    ('me-hs-lincoln-academy', 'Lincoln Academy', 'Newcastle', 'Lincoln',
     ['Lincoln Academy', 'Lincoln Acad', 'Lincoln Indoor', 'Lincoln Outdoor'], ['LA', 'LINC', 'LAC'], ['Eagles'], {}),
    ('me-hs-leavitt', 'Leavitt Area High School', 'Turner', 'Leavitt',
     ['Leavitt', 'Leavitt Area', 'Leavitt HS', 'Leavitt High School', 'Leavitt Area HS', 'Leavitt High Sch',
      'Leavitt Area High Scool'], ['LAHS', 'LEAV', 'LEA', 'LEAVITT'], ['Hornets'], {}),
    ('me-hs-cape-elizabeth', 'Cape Elizabeth High School', 'Cape Elizabeth', 'Cape Elizabeth',
     ['Cape Elizabeth', 'Cape Elizabeth HS', 'Cape Eliz', 'Cape Eliz.', 'Cape'], ['CEHS', 'CAPE', 'CE'], ['Capers'], {}),
    ('me-hs-york', 'York High School', 'York', 'York',
     ['York', 'York HS', 'York High', 'York Indoor Track'], ['YHS', 'YORK', 'YOR'], ['Wildcats'], {}),
    ('me-hs-lake-region', 'Lake Region High School', 'Naples', 'Lake Region',
     ['Lake Region', 'Lake Region HS', 'Lake Region High'], ['LRHS', 'LR', 'LAKE'], ['Lakers'], {}),
    ('me-hs-poland', 'Poland Regional High School', 'Poland', 'Poland',
     ['Poland', 'Poland Regional', 'Poland HS', 'Poland High School', 'Poland H. S.'], ['PRHS', 'POL', 'PRH'], ['Knights'], {}),
    ('me-hs-mountain-valley', 'Mountain Valley High School', 'Rumford', 'Mountain Valley',
     ['Mountain Valley', 'Mtn Valley', 'Mt Valley', 'Mt. Valley', 'Mountain Valley HS'], ['MVHS', 'MV', 'MTV'], ['Falcons'], {}),
    ('me-hs-spruce-mountain', 'Spruce Mountain High School', 'Jay', 'Spruce Mountain',
     ['Spruce Mountain', 'Spruce Mt', 'Spruce Mt.', 'Spruce Mtn', 'Spruce'], ['SPMT', 'SPR'], ['Phoenix'],
     {'years': [2011, None], 'notes': "Opened July 2011 (Jay + Livermore Falls). 'SMHS' is Sumner Memorial, never Spruce Mountain."}),
    ('me-hs-wells', 'Wells High School', 'Wells', 'Wells',
     ['Wells', 'Wells HS', 'Wells High', 'Wells Track and Field', 'Wells Track and'], ['WELL', 'WELLS', 'WHS'], ['Warriors'], {}),
    # --- Class C North ---
    ('me-hs-houlton', 'Houlton High School', 'Houlton', 'Houlton/Greater Houlton',
     ['Houlton', 'Houlton HS', 'Houlton High'], ['HHS', 'HOUL'], ['Shiretowners'], {}),
    ('me-hs-winslow', 'Winslow High School', 'Winslow', 'Winslow',
     ['Winslow', 'Winslow HS', 'Winslow High', 'Winslow Raiders'], ['WINS', 'WHS'], ['Black Raiders', 'Raiders'], {}),
    ('me-hs-orono', 'Orono High School', 'Orono', 'Orono',
     ['Orono', 'Orono HS', 'Orono High'], ['ORO', 'ORONO', 'OHS'], ['Red Riots'], {}),
    ('me-hs-bucksport', 'Bucksport High School', 'Bucksport', 'Bucksport',
     ['Bucksport', 'Bucksport HS', 'Bucksport High', 'Golden Bucks'], ['BUC', 'BUCK', 'BUCS', 'BHS'], ['Golden Bucks'], {}),
    ('me-hs-central', 'Central High School', 'Corinth', 'Central',
     ['Central', 'Central HS', 'Central High'], ['CHS', 'CEN', 'CENT'], ['Red Devils'], {}),
    ('me-hs-washington-academy', 'Washington Academy', 'East Machias', 'Washington',
     ['Washington Academy', 'Washington Acad', 'Wash Acad', 'Wash. Acad.', 'Washington'], ['WA'], ['Raiders'], {}),
    ('me-hs-dexter', 'Dexter Regional High School', 'Dexter', 'Dexter',
     ['Dexter', 'Dexter Regional', 'Dexter HS', 'Dexter Regional HS', 'Dexter High School'], ['DRHS', 'DEX'], ['Tigers'], {}),
    ('me-hs-mci', 'Maine Central Institute', 'Pittsfield', 'Maine Central Institute',
     ['Maine Central Institute', 'Maine Central', 'Maine Cent. Ins.', 'ME Cent. Inst.', 'Maine Cent Inst', 'M C I',
      'Maine Central Inst'], ['MCI'], ['Huskies'], {}),
    ('me-hs-gsa', 'George Stevens Academy', 'Blue Hill', 'George Stevens',
     ['George Stevens Academy', 'George Stevens', 'Geo Stevens', 'Geo. Stevens', 'George Stevens Acad',
      'George Stevens Academy / Blue',
      # Blue Hill Harbor School runners race as GSA's team: the combined label is GSA (James, 2026-10-17)
      'GSA/Blue Hill', 'George Stevens Academy / Blue Hill Harbor', 'George Stevens/Blue Hill Harbor'], ['GSA'], ['Eagles'], {}),
    ('me-hs-fort-kent', 'Fort Kent Community High School', 'Fort Kent', 'Fort Kent',
     ['Fort Kent', 'Fort Kent Community', 'Ft. Kent', 'Ft Kent', 'Fort Kent HS', 'Fort Kent Community HS',
      'Fort Kent Community H.S.', 'Fort Kent High School'], ['FKCHS', 'FTKT', 'FK'], ['Warriors'], {}),
    ('me-hs-sumner', 'Sumner Memorial High School', 'Sullivan', 'Sumner',
     ['Sumner', 'Sumner Memorial', 'Sumner HS', 'Sumner High School', 'Sumner Memorial HS', 'Sumner Memorial H.S.',
      'Sumner Memorial H. S.'], ['SUM', 'SMHS'], ['Tigers'], {}),
    ('me-hs-calais', 'Calais High School', 'Calais', 'Calais',
     ['Calais', 'Calais HS', 'Calais High'], ['CAL'], ['Blue Devils'], {}),
    ('me-hs-narraguagus', 'Narraguagus High School', 'Harrington', 'Narraguagus',
     ['Narraguagus', 'Narraguagus HS', 'Narragaugus', 'Narraguagus High'], ['NARR', 'NAR'], ['Knights'], {}),
    ('me-hs-machias', 'Machias Memorial High School', 'Machias', 'Machias',
     ['Machias', 'Machias Memorial', 'Machias HS', 'Machias High School', 'Machias Memorial HS'], ['MMHS', 'MACH'], ['Bulldogs'], {}),
    ('me-hs-woodland', 'Woodland Junior-Senior High School', 'Baileyville', 'Woodland',
     ['Woodland', 'Woodland HS', 'Woodland High School', 'Woodland Jr-Sr High School', 'Woodland Woodchucks'],
     ['WOOD'], ['Dragons'], {}),
    ('me-hs-hodgdon', 'Hodgdon High School', 'Hodgdon', 'Hodgdon',
     ['Hodgdon', 'Hodgdon HS', 'Hodgdon High'], ['HODG'], ['Hawks'], {}),
    ('me-hs-searsport', 'Searsport District High School', 'Searsport', 'Searsport',
     ['Searsport', 'Searsport District', 'Searsport HS', 'Searsport High', 'Searsport District HS'], ['SDHS', 'SEAR'], ['Vikings'], {}),
    ('me-hs-bangor-christian', 'Bangor Christian Schools', 'Bangor', 'Bangor Christian',
     ['Bangor Christian', 'Bangor Christian School', 'Bangor Christian HS', 'Bangor Christian High School',
      'Bangor Chr', 'Bangor Chr.', 'Bangor Chris', 'BGR Christian', 'BangorChristian', 'Bangor CHR'],
     ['BCS', 'BCHS'], ['Patriots'], {}),
    ('me-hs-penobscot-christian', 'Penobscot Christian School', 'Bangor', 'Penobscot Christian',
     ['Penobscot Christian', 'Penobscot Christian HS'], ['PCS'], [], {}),
    # 2013 track: scored as its own team beside Central in the same meets; two of its runners
    # had run 2012 XC for Central, which once pulled every "Highview Chr" row onto Central
    ('me-hs-highview-christian', 'Highview Christian Academy', 'Charleston', 'Highview Christian',
     ['Highview Christian', 'Highview Christian Academy', 'Highview Christian Academ', 'Highview Chr',
      'Highview Christian Acad'], [], [], {}),
    # MileSplit 2010 Camden Hills Invitational: two runners for this Camden private high school
    ('me-hs-watershed', 'Watershed School', 'Camden', None, ['Watershed School', 'Watershed'], [], [], {}),
    ('me-hs-mssm', 'Maine School of Science and Mathematics', 'Limestone', 'MSSM',
     ['Maine School of Science and Mathematics', 'Maine School of Science & Math', 'Maine School of Science'],
     ['MSSM'], [], {}),
    ('me-hs-deer-isle', 'Deer Isle-Stonington High School', 'Deer Isle', 'Deer Isle-Stonington',
     ['Deer Isle-Stonington', 'Deer Isle Stonington', 'Deer Isle', 'DI Stonington', 'DI- Stonington', 'DI-Stonington'],
     ['DIS', 'DISHS', 'STN', 'STNS'], ['Mariners'], {}),
    ('me-hs-shead', 'Shead High School', 'Eastport', 'Shead', ['Shead', 'Shead HS'], [], ['Tigers'], {}),
    ('me-hs-washburn', 'Washburn District High School', 'Washburn', 'Washburn',
     ['Washburn', 'Washburn District', 'Washburn HS', 'Washburn High School'], ['WDHS'], ['Beavers'], {}),
    ('me-hs-wisdom', 'Wisdom Middle/High School', 'St. Agatha', 'Wisdom', ['Wisdom', 'Wisdom HS'], [], ['Pioneers'], {}),
    ('me-hs-jonesport-beals', 'Jonesport-Beals High School', 'Jonesport', 'Jonesport-Beals',
     ['Jonesport-Beals', 'Jonesport Beals', 'Jones-Beals', 'Jonesport-Beals HS', 'J-Beals'], ['JBHS'], ['Royals'], {}),
    ('me-hs-east-grand', 'East Grand School', 'Danforth', 'East Grand',
     ['East Grand', 'East Grand HS', 'East Grand High School'], ['EG'], ['Lakers'], {}),
    ('me-hs-islesboro', 'Islesboro Central School', 'Islesboro', 'Islesboro',
     ['Islesboro', 'Islesboro Central', 'Islesboro HS', 'Isleboro'], [], ['Eagles'], {}),
    ('me-hs-madawaska', 'Madawaska Middle/High School', 'Madawaska', 'Madawaska',
     ['Madawaska', 'Madawaska HS', 'Madawaska High School'], ['MAD'], ['Owls'], {}),
    ('me-hs-schenck', 'Schenck High School', 'East Millinocket', 'Schenck',
     ['Schenck', 'Schenck HS'], ['SCK'], ['Wolverines'], {}),
    ('me-hs-stearns', 'Stearns High School', 'Millinocket', 'Stearns',
     ['Stearns', 'Stearns HS', 'Stearns High'], ['STE'], ['Minutemen'], {}),
    ('me-hs-mattanawcook', 'Mattanawcook Academy', 'Lincoln', 'Mattanawcook',
     ['Mattanawcook Academy', 'Mattanawcook', 'Mattanawcook Acad', 'Mattanawcook Aca'], ['MA', 'MATT', 'MAT'], ['Lynx'], {}),
    ('me-hs-lee-academy', 'Lee Academy', 'Lee', 'Lee', ['Lee Academy', 'Lee'], [], ['Pandas'], {}),
    ('me-hs-penobscot-valley', 'Penobscot Valley High School', 'Howland', 'Penobscot Valley',
     ['Penobscot Valley', 'Penob Valley', 'Penobscot Valley HS'], ['PVHS'], ['Howlers'], {}),
    # --- Class C South ---
    ('me-hs-oak-hill', 'Oak Hill High School', 'Wales', 'Oak Hill', ['Oak Hill', 'Oak Hill HS'], ['OH', 'OHHS'], ['Raiders'], {}),
    ('me-hs-maranacook', 'Maranacook Community High School', 'Readfield', 'Maranacook',
     ['Maranacook', 'Maranacook Community', 'Maranacook HS', 'Maranacook High', 'Maranacook High School'], ['MAR', 'MCHS'],
     ['Black Bears'], {}),
    ('me-hs-lisbon', 'Lisbon High School', 'Lisbon Falls', 'Lisbon',
     ['Lisbon', 'Lisbon HS', 'Lisbon High', 'Lisbon H S'], ['LIS', 'LISB', 'LHS'], ['Greyhounds'], {}),
    ('me-hs-traip', 'Robert W. Traip Academy', 'Kittery', 'Traip',
     ['Traip Academy', 'Traip', 'Robert W. Traip Academy', 'Traip Acad'], ['TRA', 'TRP', 'TRAIPTrack'], ['Rangers'], {}),
    ('me-hs-sacopee', 'Sacopee Valley High School', 'Hiram', 'Sacopee Valley',
     ['Sacopee Valley', 'Sacopee', 'Sacopee Valley HS', 'Sacope Valley', 'Soccopee Valley'], ['SVHS', 'SAC', 'SV'], ['Hawks'], {}),
    ('me-hs-waynflete', 'Waynflete School', 'Portland', 'Waynflete',
     ['Waynflete', 'Waynflete School', 'Waynflete HS', 'Waynflete High School'], ['WAYN'], ['Flyers'], {}),
    ('me-hs-hall-dale', 'Hall-Dale High School', 'Farmingdale', 'Hall-Dale',
     ['Hall-Dale', 'Hall Dale', 'HallDale', 'Hall-Dale HS', 'Hall-Dale High'], ['HD', 'HDHS', 'H-D'], ['Bulldogs'], {}),
    ('me-hs-dirigo', 'Dirigo High School', 'Dixfield', 'Dirigo',
     ['Dirigo', 'Dirigo HS', 'Dirigo High'], ['DIR'], ['Cougars'], {}),
    ('me-hs-winthrop', 'Winthrop High School', 'Winthrop', 'Winthrop',
     ['Winthrop', 'Winthrop HS', 'Winthrop High'], ['WINT', 'WHS'], ['Ramblers'], {}),
    ('me-hs-mt-abram', 'Mt. Abram High School', 'Salem Township', 'Mt. Abram',
     ['Mt. Abram', 'Mount Abram', 'Mt Abram', 'Mt. Abrams', 'Mt Abrams'], ['MTAB'], ['Roadrunners'], {}),
    ('me-hs-old-orchard', 'Old Orchard Beach High School', 'Old Orchard Beach', 'Old Orchard',
     ['Old Orchard Beach', 'Old Orchard', 'Old Orchard Beach HS'], ['OOB'], ['Seagulls'], {}),
    ('me-hs-carrabec', 'Carrabec High School', 'North Anson', 'Carrabec',
     ['Carrabec', 'Carrabec HS', 'Carrabec High', 'Carrabec Cobras'], ['CARR'], ['Cobras'], {}),
    ('me-hs-monmouth', 'Monmouth Academy', 'Monmouth', 'Monmouth',
     ['Monmouth Academy', 'Monmouth', 'Monmouth Acad', 'Monmouth Aca'], ['MON'], ['Mustangs'], {}),
    ('me-hs-madison', 'Madison Area Memorial High School', 'Madison', 'Madison',
     ['Madison', 'Madison Area', 'Madison Area Memorial', 'Madison HS', 'Madison High School', 'Madison Memorial',
      'Madisn'], ['MAMHS', 'MAD'], ['Bulldogs'], {}),
    ('me-hs-telstar', 'Telstar High School', 'Bethel', 'Telstar',
     ['Telstar', 'Telstar Regional', 'Telstar HS', 'Telstar Regional HS', 'Telstar High'], ['TEL'], ['Rebels'], {}),
    ('me-hs-nya', 'North Yarmouth Academy', 'Yarmouth', 'North Yarmouth',
     ['North Yarmouth Academy', 'North Yarmouth', 'NoYarmouth Acad', 'North Yarmouth Acad', 'NorthYarmputh Ac',
      'No. Yarmouth Academy'], ['NYA'], ['Panthers'], {}),
    ('me-hs-richmond', 'Richmond High School', 'Richmond', 'Richmond',
     ['Richmond', 'Richmond HS', 'Richmond High'], ['RICH', 'RIC'], ['Bobcats'], {}),
    ('me-hs-valley', 'Valley High School', 'Bingham', 'Valley', ['Valley', 'Valley HS'], [], ['Cavaliers'],
     {'middle_grades': 'me-ms-upper-kennebec'}),
    ('me-hs-forest-hills', 'Forest Hills Consolidated School', 'Jackman', 'Forest Hills',
     ['Forest Hills', 'Forest Hills HS'], [], ['Tigers'], {}),
    ('me-hs-maine-coast-waldorf', 'Maine Coast Waldorf School', 'Freeport', 'Maine Coast Waldorf',
     ['Maine Coast Waldorf', 'Maine Coast Waldorf School', 'Maine Coast', 'Maine Coast HS', 'Maine Coast Wald',
      'Merriconeag Waldorf', 'Merriconeag Waldorf School', 'Merriconeag', 'Maine Coast Waldorf High School',
      'Maine Coast Waldorf HS', 'Merriconeag Waldorf HS'], ['MCWS'], [],
     {'notes': 'Named Merriconeag Waldorf School until 2018.'}),
    ('me-hs-seacoast-christian', 'Seacoast Christian School', 'South Berwick', 'Seacoast Christian',
     ['Seacoast Christian', 'Seacoast Christian School', 'Seacoast Chr', 'Seacoast'], [], [], {}),
    ('me-hs-north-haven', 'North Haven Community School', 'North Haven', 'North Haven',
     ['North Haven', 'North Haven HS', 'North Haven Community'], ['NHCS'], [], {}),
    ('me-hs-boothbay', 'Boothbay Region High School', 'Boothbay Harbor', 'Boothbay',
     ['Boothbay Region', 'Boothbay', 'Boothbay Region HS', 'Boothbay HS', 'Boothbay High School', 'Boothbay Reg',
      'Boothbay Regional High School', 'Boothbay Regional'],
     ['BRHS', 'BBRHS'], ['Seahawks'], {}),
    ('me-hs-wiscasset', 'Wiscasset High School', 'Wiscasset', 'Wiscasset',
     ['Wiscasset', 'Wiscasset HS', 'Wiscasset High', 'Wiscassett', 'Wisc'], ['WISC'], ['Wolverines'], {}),
    # --- Outdoor-track-only / other current Maine HS ---
    ('me-hs-mt-view', 'Mount View High School', 'Thorndike', 'Mt. View',
     ['Mount View', 'Mt. View', 'Mt View', 'Mountain View', 'Mount View HS', 'Mt View HS', 'Mt. View High School'],
     ['MTV', 'MVHS', 'MNTV', 'Mntv'], ['Mustangs'], {}),
    ('me-hs-kents-hill', 'Kents Hill School', 'Readfield', 'Kents Hill',
     ['Kents Hill', 'Kents Hill School'], ['KH'], ['Huskies'], {}),
    ('me-hs-gould', 'Gould Academy', 'Bethel', 'Gould', ['Gould Academy', 'Gould'], [], [], {}),
    ('me-hs-penquis', 'Penquis Valley High School', 'Milo', 'Penquis Valley',
     ['Penquis Valley', 'Penquis', 'Penquis Valley HS'], ['PENQ', 'PVHS'], ['Patriots'], {}),
    ('me-hs-buckfield', 'Buckfield Junior-Senior High School', 'Buckfield', 'Buckfield',
     ['Buckfield', 'Buckfield HS', 'Buckfield High School'], [], ['Bucks'], {}),
    ('me-hs-fort-fairfield', 'Fort Fairfield Middle/High School', 'Fort Fairfield', 'Fort Fairfield',
     ['Fort Fairfield', 'Ft. Fairfield', 'Ft Fairfield', 'Ft.Fairfield', 'Fort Fairfield HS', 'Fort Fairfield High School'],
     ['FFHS', 'FTFD', 'FF'], ['Tigers'], {}),
    ('me-hs-easton', 'Easton Junior-Senior High School', 'Easton', 'Easton', ['Easton', 'Easton HS'], [], ['Bears'], {}),
    ('me-hs-greenville', 'Greenville Consolidated School', 'Greenville', 'Greenville',
     ['Greenville', 'Greenville HS', 'Greenville High School', 'Greenville High'], ['GRNV'], ['Lakers'], {}),
    ('me-hs-blue-hill-harbor', 'Blue Hill Harbor School', 'Blue Hill', 'Blue Hill Harbor',
     ['Blue Hill Harbor', 'Blue Hill Harbor School'], [], [], {}),
    ('me-hs-vinalhaven', 'Vinalhaven School', 'Vinalhaven', 'Vinalhaven', ['Vinalhaven', 'Vinalhaven HS'], [], [], {}),
    ('me-hs-greater-portland-christian', 'Greater Portland Christian School', 'South Portland', 'Greater Portland',
     ['Greater Portland Christian', 'Greater Portland', 'Gr. Portland CS', 'Gr. Portland', 'Greater Portland Christian School'],
     ['GPCS'], [], {}),
    ('me-hs-chop-point', 'Chop Point School', 'Woolwich', 'Chop Point', ['Chop Point', 'Chop Point School'], [], [], {}),
    ('me-hs-piscataquis', 'Piscataquis Community High School', 'Guilford', 'Piscataquis',
     ['Piscataquis', 'Piscataquis Community', 'Piscataquis Community HS', 'Piscataquis HS', 'Piscataquis Comm'],
     ['PCHS'], ['Pirates'], {}),
    ('me-hs-greater-houlton-christian', 'Greater Houlton Christian Academy', 'Houlton', None,
     ['Greater Houlton Christian Academy', 'Greater Houlton Christian', 'Greater Houlton', 'GrtrHltn',
      'Greater Houlton Christian Acad'], ['GHCA'], [], {}),
    ('me-hs-hyde', 'Hyde School', 'Bath', None, ['Hyde', 'Hyde School'], [], [], {}),
    # --- Other Maine secondary schools seen in results (no current MPA XC/track listing) ---
    ('me-hs-st-dominic', 'St. Dominic Academy', 'Auburn', None,
     ['St. Dominic', 'St Dominic', 'Saint Dominic', 'St. Dominic Academy', 'Saint Dominic Academy',
      'St. Dominic Regional', 'St. Dominic Regional High School', "St. Dom's", 'St. Doms', 'St Doms', 'Saint Doms',
      'St Dominic Regional High School',
      # 2026-10-19, XC: 'St D' (Lake Region invites 2005-09), 'Doms'/"Dom's" (NYA meets 2008), "St. Dom's Bcc/Gcc" (WMC 2006
      # boys/girls cross country); St. Dominic is the only Maine 'St. D...' school, and each file's other teams are its WMC rivals
      'St D', 'StD', 'Doms', "Dom's", "St. Dom's Bcc", "St. Dom's Gcc", 'Dominic Academy'], ['STDM', 'SDA'], ['Saints'], {}),
    ('me-hs-rockland', 'Rockland District High School', 'Rockland', None,
     ['Rockland', 'Rockland District', 'Rockland District HS', 'Rockland HS'], ['RDHS', 'ROCK'], ['Tigers'],
     {'years': [None, 2010], 'successor': 'me-hs-oceanside'}),
    ('me-hs-georges-valley', 'Georges Valley High School', 'Thomaston', None,
     ['Georges Valley', 'Georges Valley HS'], ['GVHS'], ['Buccaneers'],
     {'years': [None, 2010], 'successor': 'me-hs-oceanside'}),
    ('me-hs-mcauley', 'Catherine McAuley High School', 'Portland', None,
     ['Catherine McAuley', 'McAuley', 'Catherine McAuley High School', 'McAuley High School', 'McAuley HS',
      'Maine Girls Academy', "Maine Girls' Academy", 'Maine Girls Academy HS'], ['MGA', 'CMHS'], ['Lions'],
     {'years': [None, 2019], 'notes': "Renamed Maine Girls' Academy 2016; closed 2020."}),
    ('me-hs-jay', 'Jay High School', 'Jay', None, ['Jay', 'Jay HS', 'Jay High School'], ['JAY'], ['Tigers'],
     {'years': [None, 2010], 'successor': 'me-hs-spruce-mountain'}),
    ('me-hs-livermore-falls', 'Livermore Falls High School', 'Livermore Falls', None,
     ['Livermore Falls', 'Livermore Falls HS', 'Livermore'], ['LFHS', 'LF', 'LIV'], ['Andies'],
     {'years': [None, 2010], 'successor': 'me-hs-spruce-mountain'}),
    ('me-hs-limestone', 'Limestone Community School', 'Limestone', None,
     ['Limestone', 'Limestone Community School', 'Limestone HS'], ['LCS'], ['Eagles'], {}),
    ('me-hs-central-aroostook', 'Central Aroostook Junior-Senior High School', 'Mars Hill', None,
     ['Central Aroostook', 'Central Aroostook HS'], ['CA'], ['Panthers'], {}),
    ('me-hs-southern-aroostook', 'Southern Aroostook Community School', 'Dyer Brook', None,
     ['Southern Aroostook', 'Southern Aroostook Community School'], [], ['Warriors'], {}),
    ('me-hs-katahdin', 'Katahdin Middle/High School', 'Stacyville', None, ['Katahdin', 'Katahdin HS'], [], ['Cougars'], {}),
    ('me-hs-van-buren', 'Van Buren District Secondary School', 'Van Buren', None, ['Van Buren', 'Van Buren HS'], [], ['Crusaders'], {}),
    ('me-hs-ashland', 'Ashland District School', 'Ashland', None, ['Ashland', 'Ashland HS'], [], ['Hornets'], {}),
    ('me-hs-rangeley', 'Rangeley Lakes Regional School', 'Rangeley', None, ['Rangeley', 'Rangeley Lakes'], [], ['Lakers'], {}),
    ('me-hs-temple', 'Temple Academy', 'Waterville', None, ['Temple Academy'], [], [], {}),
    ('me-hs-hebron', 'Hebron Academy', 'Hebron', None, ['Hebron Academy', 'Hebron'], ['HEB'], [], {}),
    ('me-hs-berwick', 'Berwick Academy', 'South Berwick', None, ['Berwick Academy', 'Berwick'], [], [], {}),
    ('me-hs-pine-tree', 'Pine Tree Academy', 'Freeport', None, ['Pine Tree Academy'], [], [], {}),
    ('me-hs-calvary-chapel', 'Calvary Chapel Christian School', 'Orrington', None,
     ['Calvary Chapel', 'Calvary Chapel Christian School', 'Calvary Chapel School', 'Calvary'], ['CCS'], [], {}),
    ('me-hs-baxter', 'Baxter Academy for Technology and Science', 'Portland', None,
     ['Baxter Academy', 'Baxter Academy for Technology and Science'], [], [], {}),
    ('me-hs-casco-bay', 'Casco Bay High School', 'Portland', None, ['Casco Bay', 'Casco Bay HS', 'Casco Bay High School'], [], [], {}),
    ('me-hs-means', 'Maine Academy of Natural Sciences', 'Hinckley', None,
     ['Maine Academy of Natural Sciences', 'MeANS'], [], [], {}),
    ('me-hs-upper-kennebec', 'Upper Kennebec Valley Junior-Senior High School', 'Bingham', None,
     ['Upper Kennebec Valley', 'Upper Kennebec', 'Upper Kenneb'], [], [],
     {'successor': 'me-hs-valley', 'middle_grades': 'me-ms-upper-kennebec'}),
    ('me-hs-st-thomas', 'Saint Thomas Aquinas', 'Dover-Foxcroft', None, [], [], [], {}),
    ('me-hs-elan', 'Elan School', 'Poland', None,
     ['Elan', 'Elan School', 'The Elan School', 'ELAN School'], ['ELAN'], [],
     {'years': [None, 2010], 'notes': 'Elan School, Poland ME (residential; closed April 2011). Track 2003-2011 '
      '(Hampden, Orono, Class C, Sacopee, Old Town meets); XC 2003-2008 (Western D/C, WMC). Never Edward '
      'Little. Beware runners whose first name is Elan (Ramirez, Zanoni, Gable-Richards, Seago).'}),
    ('me-hs-harpswell', 'Harpswell Coastal Academy', 'Harpswell', None, ['Harpswell Coastal Academy'], [], [], {}),
    ('me-hs-cornville', 'Cornville Regional Charter School', 'Cornville', None, ['Cornville Regional Charter School', 'Cornville'], [], [], {}),
]

# MPA classification lists used (name in list -> catalog id is via the 'mpa'
# field above; co-ops below).
MPA_SOURCES = {
    'xc_2026': 'https://www.mpa.cc/resources/Tournament%20Info/Cross%20Country%20Boys/Bulletin%202026-27.pdf (p.9)',
    'it_2026': 'https://www.mpa.cc/resources/Tournament%20Info/Indoor%20Track%20Boys/Bulletin%202026-27.pdf (p.7; identical in 2025-26)',
    'ot_2026': 'https://www.mpa.cc/resources/Tournament%20Info/Outdoor%20Track%20Boys/Bulletin%202025-26.pdf (p.10)',
}

# MPA class/region per list. XC 2026-27 (A/B/C x North/South), indoor track
# 2026-27 (A/B), outdoor track 2025-26 (A/B/C). Keys are catalog ids or co-op ids.
MPA_XC_2026 = {
    'A North': ['me-hs-edward-little', 'me-hs-lewiston', 'me-hs-bangor', 'me-hs-oxford-hills', 'me-hs-hampden',
                'me-hs-camden-hills', 'me-hs-brunswick', 'me-hs-messalonskee', 'me-hs-mt-ararat', 'me-hs-skowhegan',
                'me-hs-brewer', 'me-hs-mt-blue'],
    'A South': ['me-hs-thornton', 'me-hs-portland', 'me-hs-sanford', 'me-hs-bonny-eagle', 'me-hs-deering',
                'me-hs-south-portland', 'me-hs-noble', 'me-hs-windham', 'me-hs-scarborough', 'me-hs-massabesic',
                'me-hs-gorham', 'me-hs-biddeford', 'me-hs-kennebunk', 'me-hs-marshwood', 'me-hs-westbrook',
                'me-hs-falmouth', 'me-hs-fryeburg', 'me-hs-cheverus'],
    'B North': ['me-hs-cony', 'me-hs-nokomis', 'me-hs-gardiner', 'me-hs-hermon', 'me-hs-medomak', 'me-hs-old-town',
                'me-hs-erskine', 'me-hs-lawrence', 'me-hs-ellsworth', 'me-hs-john-bapst', 'me-hs-oceanside',
                'me-hs-waterville', 'me-hs-mdi', 'me-hs-belfast', 'me-hs-presque-isle', 'me-hs-foxcroft',
                'me-hs-caribou'],
    'B South': ['me-hs-freeport', 'me-hs-morse', 'me-hs-greely', 'me-hs-gray-ng', 'me-hs-yarmouth',
                'me-hs-lincoln-academy', 'me-hs-leavitt', 'me-hs-cape-elizabeth', 'me-hs-york', 'me-hs-lake-region',
                'me-hs-poland', 'me-hs-mountain-valley|B', 'me-hs-spruce-mountain',
                'me-hs-wells'],
    'C North': ['coop-houlton-ghca', 'me-hs-winslow', 'me-hs-orono', 'me-hs-bucksport', 'me-hs-central',
                'me-hs-washington-academy', 'me-hs-dexter', 'me-hs-mci', 'me-hs-gsa', 'me-hs-fort-kent',
                'me-hs-sumner', 'me-hs-calais', 'me-hs-narraguagus', 'me-hs-machias|B', 'me-hs-woodland',
                'me-hs-hodgdon', 'me-hs-searsport', 'coop-bangor-christian-penobscot-christian', 'me-hs-mssm',
                'me-hs-deer-isle', 'me-hs-shead', 'me-hs-washburn', 'me-hs-wisdom', 'me-hs-jonesport-beals|B',
                'me-hs-east-grand|B', 'me-hs-islesboro', 'coop-xc-fort-kent-madawaska-g|G',
                'coop-schenck-stearns', 'coop-mattanawcook-lee-pvhs', 'coop-xc-machias-jonesport-beals-g|G'],
    'C South': ['me-hs-oak-hill', 'me-hs-maranacook', 'me-hs-lisbon', 'me-hs-traip', 'me-hs-sacopee',
                'me-hs-waynflete', 'me-hs-hall-dale', 'coop-xc-dirigo-mountain-valley-g|G', 'me-hs-dirigo|B',
                'me-hs-winthrop', 'me-hs-mt-abram', 'me-hs-old-orchard', 'me-hs-carrabec', 'me-hs-monmouth',
                'me-hs-madison', 'me-hs-telstar', 'me-hs-nya', 'me-hs-richmond', 'me-hs-valley', 'me-hs-forest-hills',
                'me-hs-maine-coast-waldorf', 'me-hs-seacoast-christian|B', 'me-hs-north-haven', 'coop-boothbay-wiscasset'],
}
# '|B' / '|G' = the list entry applies to that gender only (MPA prints "(B)"/"(G)").
# The XC list prints "Mountain Valley, (B)" in B South and "Dirigo/Mountain Valley (G)" in C South.

MPA_IT_2026 = {
    'A': ['me-hs-lewiston', 'me-hs-thornton', 'me-hs-portland', 'me-hs-edward-little', 'me-hs-sanford', 'me-hs-bangor',
          'me-hs-bonny-eagle', 'me-hs-deering', 'me-hs-oxford-hills', 'me-hs-south-portland', 'me-hs-noble',
          'me-hs-windham', 'me-hs-scarborough', 'me-hs-massabesic', 'me-hs-gorham', 'me-hs-hampden', 'me-hs-mt-ararat',
          'me-hs-camden-hills', 'coop-it-brunswick-hyde-b|B', 'me-hs-brunswick', 'me-hs-messalonskee', 'me-hs-westbrook',
          'me-hs-kennebunk', 'coop-it-skowhegan-madison', 'me-hs-falmouth', 'me-hs-brewer', 'me-hs-biddeford',
          'me-hs-marshwood', 'coop-it-cony-halldale-winthrop', 'coop-it-gardiner-lisbon-maranacook',
          'coop-cheverus-waynflete'],
    'B': ['me-hs-fryeburg', 'me-hs-freeport', 'me-hs-morse', 'me-hs-nokomis', 'me-hs-greely', 'me-hs-gray-ng',
          'me-hs-yarmouth', 'me-hs-hermon', 'me-hs-lincoln-academy', 'me-hs-leavitt', 'me-hs-medomak', 'me-hs-old-town',
          'me-hs-erskine', 'me-hs-lawrence', 'me-hs-ellsworth', 'me-hs-cape-elizabeth', 'me-hs-john-bapst', 'me-hs-york',
          'me-hs-lake-region', 'me-hs-oceanside', 'me-hs-poland', 'me-hs-waterville', 'me-hs-mdi', 'me-hs-belfast',
          'me-hs-presque-isle', 'me-hs-foxcroft', 'me-hs-wells', 'me-hs-maranacook', 'me-hs-winslow', 'me-hs-orono',
          'me-hs-bucksport', 'coop-it-central-dexter', 'coop-it-mattanawcook-pvhs', 'me-hs-traip', 'me-hs-sacopee',
          'me-hs-mci', 'me-hs-gsa', 'coop-it-sumner-narraguagus', 'coop-boothbay-wiscasset', 'me-hs-piscataquis',
          'coop-nya-maine-coast-waldorf', 'me-hs-bangor-christian'],
}

MPA_OT_2026 = {
    'A': ['me-hs-lewiston', 'me-hs-thornton', 'me-hs-portland', 'me-hs-edward-little', 'me-hs-sanford', 'me-hs-bangor',
          'me-hs-bonny-eagle', 'me-hs-deering', 'me-hs-oxford-hills', 'me-hs-south-portland', 'me-hs-noble',
          'me-hs-windham', 'me-hs-scarborough', 'me-hs-massabesic', 'me-hs-gorham', 'me-hs-hampden', 'me-hs-mt-ararat',
          'me-hs-camden-hills', 'me-hs-brunswick', 'me-hs-messalonskee', 'me-hs-westbrook', 'me-hs-kennebunk',
          'me-hs-skowhegan', 'me-hs-falmouth', 'me-hs-mt-blue', 'me-hs-brewer', 'me-hs-biddeford', 'me-hs-marshwood',
          'coop-cheverus-waynflete'],
    'B': ['me-hs-fryeburg', 'me-hs-cony', 'me-hs-freeport', 'me-hs-morse', 'me-hs-nokomis', 'me-hs-greely',
          'me-hs-gray-ng', 'me-hs-gardiner', 'me-hs-yarmouth', 'me-hs-hermon', 'me-hs-lincoln-academy', 'me-hs-medomak',
          'me-hs-leavitt', 'me-hs-old-town|B', 'coop-ot-old-town-pvhs-g|G', 'me-hs-erskine', 'me-hs-lawrence',
          'me-hs-ellsworth', 'me-hs-cape-elizabeth', 'me-hs-john-bapst', 'me-hs-york', 'me-hs-lake-region',
          'me-hs-oceanside', 'me-hs-poland', 'me-hs-waterville', 'me-hs-mdi', 'me-hs-belfast', 'me-hs-presque-isle',
          'me-hs-foxcroft', 'me-hs-caribou'],
    'C': ['me-hs-wells', 'me-hs-winslow', 'coop-houlton-ghca|B', 'me-hs-washington-academy', 'me-hs-spruce-mountain',
          'me-hs-mountain-valley', 'me-hs-maranacook', 'me-hs-bucksport', 'me-hs-mt-view', 'me-hs-mci', 'me-hs-orono',
          'coop-ot-lisbon-oak-hill', 'me-hs-gsa', 'me-hs-sacopee', 'me-hs-mattanawcook', 'me-hs-central',
          'me-hs-hall-dale', 'me-hs-dexter', 'me-hs-traip', 'me-hs-fort-kent', 'me-hs-calais', 'me-hs-sumner',
          'me-hs-winthrop', 'me-hs-kents-hill', 'me-hs-gould', 'me-hs-dirigo', 'me-hs-mt-abram', 'me-hs-madison',
          'me-hs-old-orchard', 'coop-nya-maine-coast-waldorf', 'me-hs-monmouth', 'me-hs-narraguagus', 'me-hs-carrabec',
          'me-hs-piscataquis', 'me-hs-telstar', 'me-hs-penquis', 'coop-boothbay-wiscasset', 'me-hs-buckfield',
          'me-hs-madawaska|B', 'me-hs-penobscot-valley|B', 'me-hs-fort-fairfield', 'me-hs-searsport', 'me-hs-richmond',
          'me-hs-lee-academy', 'me-hs-deer-isle|G', 'me-hs-mssm', 'me-hs-washburn',
          'coop-bangor-christian-penobscot-christian', 'me-hs-easton|B', 'me-hs-greenville', 'me-hs-blue-hill-harbor',
          'me-hs-vinalhaven|G', 'me-hs-greater-portland-christian', 'me-hs-seacoast-christian', 'me-hs-chop-point|G',
          'me-hs-north-haven|B'],
}

# ---------------------------------------------------------------------------
# Co-operative teams. A co-op is sport/season, gender and year specific.
# 'host' is the school whose name usually appears on result sheets.
# 'evidence' is filled with MPA list citations here; the builder adds
# observed raw labels and the seasons they appear in.
# ---------------------------------------------------------------------------
COOPS = [
    dict(id='coop-houlton-ghca', label='Houlton/Greater Houlton', host='me-hs-houlton',
         members=['me-hs-houlton', 'me-hs-greater-houlton-christian'], seasons=['XC', 'Outdoor', 'Indoor'],
         genders=['Boys', 'Girls'], years=[2019, None],
         labels=['Houlton/GHCA', 'Houlton/Hodg', 'Ghca / Houlton', 'Houlton High / GHCA', 'Houlton/Greater Houlton',
                 'Houlton/Greater Houlton Christian', 'Houlton/Gr. Houlton CA', 'Houlton/Greater Houlton CA'],
         evidence=['MPA XC 2026-27 C North "Houlton/Greater Houlton"', 'MPA OT 2025-26 C "Houlton/Greater Houlton (B)"']),
    # North Haven + Vinalhaven cross-country team 'Fox Islands' / 'H. Haven/Vinal': printed only in XC
    # 2004-2009 (Festival heats and sections, Class C West regionals, Camden Hills, Searsport, Belfast,
    # Cony, LaLiberte); both schools race under their own names in every other season and year
    dict(id='coop-fox-islands', label='Fox Islands (North Haven/Vinalhaven)', host='me-hs-north-haven',
         members=['me-hs-north-haven', 'me-hs-vinalhaven'], seasons=['XC'], genders=['Boys', 'Girls'], years=[2004, 2009],
         labels=['Fox Islands', 'Fox Island', 'H. Haven/Vinal', 'N. Haven/Vinal', 'North Haven/Vinalhaven'],
         evidence=['the label in 2004-2009 XC results (festival04gheats, festivalsectionsB 2005, classcboyswest 2007, focboyssections 2007, belfast9_13 2008, conyboys_sept25 2009)']),
    dict(id='coop-bangor-christian-penobscot-christian', label='Bangor Christian/Penobscot Christian',
         host='me-hs-bangor-christian', members=['me-hs-bangor-christian', 'me-hs-penobscot-christian'],
         seasons=['XC', 'Outdoor'], genders=['Boys', 'Girls'], years=[None, None],
         labels=['Bangor Christian/Penobscot Christian', 'BCS/PCS'],
         evidence=['MPA XC 2026-27 C North', 'MPA OT 2025-26 C (indoor track lists Bangor Christian alone)']),
    dict(id='coop-schenck-stearns', label='Schenck/Stearns', host='me-hs-stearns',
         members=['me-hs-schenck', 'me-hs-stearns'], seasons=['XC'], genders=['Boys', 'Girls'], years=[None, None],
         labels=['Schenck/Stearns', 'Stearns/Schenck'], evidence=['MPA XC 2026-27 C North']),
    dict(id='coop-mattanawcook-lee-pvhs', label='Mattanawcook/Lee/Penobscot Valley', host='me-hs-mattanawcook',
         members=['me-hs-mattanawcook', 'me-hs-lee-academy', 'me-hs-penobscot-valley'], seasons=['XC'],
         genders=['Boys', 'Girls'], years=[None, None],
         labels=['Mattanawcook/Lee/Penobscot Valley', 'Mattanawcook/Lee/PV'], evidence=['MPA XC 2026-27 C North']),
    dict(id='coop-xc-fort-kent-madawaska-g', label='Fort Kent/Madawaska (G)', host='me-hs-fort-kent',
         members=['me-hs-fort-kent', 'me-hs-madawaska'], seasons=['XC'], genders=['Girls'], years=[None, None],
         labels=['Fort Kent/Madawaska'], evidence=['MPA XC 2026-27 C North "Fort Kent/Madawaska (G)"']),
    dict(id='coop-xc-machias-jonesport-beals-g', label='Machias/Jones-Beals (G)', host='me-hs-machias',
         members=['me-hs-machias', 'me-hs-jonesport-beals'], seasons=['XC'], genders=['Girls'], years=[None, None],
         labels=['Machias/Jones-Beals', 'Machias/Jonesport-Beals'],
         evidence=['MPA XC 2026-27 C North "Machias/Jones-Beals (G)"; boys listed separately']),
    dict(id='coop-xc-dirigo-mountain-valley-g', label='Dirigo/Mountain Valley (G)', host='me-hs-dirigo',
         members=['me-hs-dirigo', 'me-hs-mountain-valley'], seasons=['XC'], genders=['Girls'], years=[None, None],
         labels=['Dirigo/Mountain Valley', 'Dirigo/Mtn Valley'],
         evidence=['MPA XC 2026-27 C South "Dirigo/Mountain Valley (G)"; boys listed separately']),
    dict(id='coop-boothbay-wiscasset', label='Boothbay/Wiscasset', host='me-hs-boothbay',
         members=['me-hs-boothbay', 'me-hs-wiscasset'], seasons=['XC', 'Indoor', 'Outdoor'], genders=['Boys', 'Girls'],
         years=[None, None],
         labels=['Boothbay/Wiscasset', 'BoothbayWiscasset', 'Boothbay Wiscasset', 'Boothbay-Wiscasset',
                 'Boothbay/Wis', 'Boothbay-Wisc', 'Wiscasset/Boothbay', 'BBWHS', 'Boothbay Wiscasset HS'],
         evidence=['MPA XC 2026-27 C South', 'MPA IT 2026-27 B', 'MPA OT 2025-26 C "Wiscasset/Boothbay"']),
    dict(id='coop-it-sumner-narraguagus', label='Sumner/Narraguagus (indoor track)', host='me-hs-sumner',
         members=['me-hs-sumner', 'me-hs-narraguagus'], seasons=['Indoor'], genders=['Boys', 'Girls'],
         years=[None, None],
         labels=['Sumner/Narraguagus', 'Sumner/Narragaugus', 'SumnerNarragaugus', 'Sumner/Narra', 'Sumner/Guagus',
                 'Sumner-Narraguagus'],
         evidence=['MPA IT 2026-27 B "Sumner/Narraguagus"; XC 2026-27 and OT 2025-26 list them separately']),
    dict(id='coop-nya-maine-coast-waldorf', label='North Yarmouth/Maine Coast Waldorf', host='me-hs-nya',
         members=['me-hs-nya', 'me-hs-maine-coast-waldorf'], seasons=['Indoor', 'Outdoor'], genders=['Boys', 'Girls'],
         years=[None, None], labels=['NYA/MCWS', 'North Yarmouth/Maine Coast Waldorf', 'NYA/Maine Coast Waldorf',
                                     'NYA Maine Coast Waldorf'],
         evidence=['MPA IT 2026-27 B', 'MPA OT 2025-26 C; XC 2026-27 lists them separately']),
    dict(id='coop-cheverus-waynflete', label='Cheverus/Waynflete', host='me-hs-cheverus',
         members=['me-hs-cheverus', 'me-hs-waynflete'], seasons=['Indoor', 'Outdoor'], genders=['Boys', 'Girls'],
         years=[None, None], labels=['Cheverus/Waynflete', 'Cheverus/Way', 'CHVW'],
         evidence=['MPA IT 2026-27 A', 'MPA OT 2025-26 A; XC lists them separately']),
    dict(id='coop-it-brunswick-hyde-b', label='Brunswick/Hyde (B)', host='me-hs-brunswick',
         members=['me-hs-brunswick', 'me-hs-hyde'], seasons=['Indoor'], genders=['Boys'], years=[None, None],
         labels=['Brunswick/Hyde'], evidence=['MPA IT 2026-27 A "Brunswick/Hyde (B)"']),
    dict(id='coop-it-skowhegan-madison', label='Skowhegan/Madison (indoor track)', host='me-hs-skowhegan',
         members=['me-hs-skowhegan', 'me-hs-madison'], seasons=['Indoor'], genders=['Boys', 'Girls'], years=[None, None],
         labels=['Skowhegan/Madison'], evidence=['MPA IT 2026-27 A']),
    dict(id='coop-it-cony-halldale-winthrop', label='Cony/Hall-Dale/Winthrop (indoor track)', host='me-hs-cony',
         members=['me-hs-cony', 'me-hs-hall-dale', 'me-hs-winthrop'], seasons=['Indoor'], genders=['Boys', 'Girls'],
         years=[None, None], labels=['Cony/Hall-Dale/Winthrop'], evidence=['MPA IT 2026-27 A']),
    dict(id='coop-it-gardiner-lisbon-maranacook', label='Gardiner/Lisbon/Maranacook (indoor track)', host='me-hs-gardiner',
         members=['me-hs-gardiner', 'me-hs-lisbon', 'me-hs-maranacook'], seasons=['Indoor'], genders=['Boys', 'Girls'],
         years=[None, None], labels=['Gardiner/Lisbon/Maranacook'], evidence=['MPA IT 2026-27 A']),
    dict(id='coop-it-central-dexter', label='Central/Dexter (indoor track)', host='me-hs-central',
         members=['me-hs-central', 'me-hs-dexter'], seasons=['Indoor'], genders=['Boys', 'Girls'], years=[None, None],
         labels=['Central/Dexter'], evidence=['MPA IT 2026-27 B']),
    dict(id='coop-it-mattanawcook-pvhs', label='Mattanawcook/Penobscot Valley (indoor track)', host='me-hs-mattanawcook',
         members=['me-hs-mattanawcook', 'me-hs-penobscot-valley'], seasons=['Indoor'], genders=['Boys', 'Girls'],
         years=[None, None], labels=['Mattanawcook/Penobscot Valley'], evidence=['MPA IT 2026-27 B']),
    dict(id='coop-ot-old-town-pvhs-g', label='Old Town/Penobscot Valley (G, outdoor track)', host='me-hs-old-town',
         members=['me-hs-old-town', 'me-hs-penobscot-valley'], seasons=['Outdoor'], genders=['Girls'], years=[None, None],
         labels=['Old Town/Penobscot Valley'], evidence=['MPA OT 2025-26 B "Old Town/Penobscot Valley (G)"']),
    dict(id='coop-ot-lisbon-oak-hill', label='Lisbon/Oak Hill (outdoor track)', host='me-hs-lisbon',
         members=['me-hs-lisbon', 'me-hs-oak-hill'], seasons=['Outdoor', 'Indoor'], genders=['Boys', 'Girls'],
         years=[2019, None], labels=['Lisbon/Oak Hill', 'Lisb/OH', 'Lisbon/Oak H', 'Lisbon-Oak Hill'],
         evidence=['MPA OT 2025-26 C "Lisbon/Oak Hill"']),
    dict(id='coop-limestone-mssm', label='Limestone/MSSM', host='me-hs-mssm',
         members=['me-hs-limestone', 'me-hs-mssm'], seasons=['XC', 'Indoor', 'Outdoor'], genders=['Boys', 'Girls'],
         years=[None, None], labels=['Limestone/MSSM', 'Limestone/MS', 'LCS/MSSM', 'Lim/MSSM', 'LIM/MSSM',
                                     'LimestoneMSSM'],
         evidence=['observed labels only (pre-2026 MPA lists not recovered)']),
    dict(id='coop-lisbon-st-dom', label='Lisbon/St. Dominic', host='me-hs-lisbon',
         members=['me-hs-lisbon', 'me-hs-st-dominic'], seasons=['Indoor', 'Outdoor'], genders=['Boys', 'Girls'],
         years=[None, None], labels=['Lisb/St,Doms', 'Lisbon/St. Doms', 'Lisbon/St Doms', 'Lisbon/St. Dominic'],
         evidence=['observed label only']),
    dict(id='coop-houlton-hodgdon', label='Houlton/Hodgdon(/GHCA)', host='me-hs-houlton',
         members=['me-hs-houlton', 'me-hs-hodgdon', 'me-hs-greater-houlton-christian'], seasons=['Indoor', 'Outdoor'],
         genders=['Boys', 'Girls'], years=[None, None],
         labels=['Houlton/Hodg', 'Houlton/Hodgdon', 'Houlton/Hodgdon/GHCA', 'Hltn/GHCA/Hdgdn'], evidence=['observed label only']),
    dict(id='coop-boothbay-wiscasset-richmond', label='Boothbay/Wiscasset/Richmond', host='me-hs-boothbay',
         members=['me-hs-boothbay', 'me-hs-wiscasset', 'me-hs-richmond'], seasons=['Indoor', 'Outdoor'],
         genders=['Boys', 'Girls'], years=[None, None], labels=['Bthby/Wisc/Rchmd'], evidence=['observed label only']),
    dict(id='coop-mattanawcook-penobscot', label='Mattanawcook/Penobscot Valley', host='me-hs-mattanawcook',
         members=['me-hs-mattanawcook', 'me-hs-penobscot-valley'], seasons=['XC', 'Outdoor'], genders=['Boys', 'Girls'],
         years=[None, None], labels=['Mattan/Penob'], evidence=['observed label only']),
]

# ---------------------------------------------------------------------------
# Maine middle / junior high / K-8 schools
# ---------------------------------------------------------------------------
ME_MS = [
    # 2026-10-24 store-team review: schools printed in XC meets and missing from the catalog
    ('me-ms-madison-athens', 'Madison/Athens (combined MS team)', 'Madison', None,
     ['Madison/Athens', 'MadisonAthens', 'Madison-Athens', 'Madison Athens'], [], [], {}),   # scored as one team, 2005 Central Maine MS league
    ('me-ms-st-brigid', 'St. Brigid School', 'Portland', None, ['St. Brigid School', "St. Brigid's", "St Brigid's", 'St. Brigid', 'St Brigid'], [], [], {}),   # Portland K-8; 2022 Falmouth MS meets
    ('me-ms-islesford', 'Islesford School', 'Cranberry Isles', None, ['Islesford School', 'Islesford', 'Isleford'], [], [], {}),
    # Penobscot / Hancock / Waldo / Knox / Washington
    ('me-ms-doughty', 'James F. Doughty School', 'Bangor', None,
     ['James F. Doughty School', 'James Doughty School', 'James Doughty', 'Doughty', 'James Doughty MS', 'JamesDoughty',
      'Doughty Middle School', 'James F Doughty'], ['JFD', 'JFDS', 'JDS'], [], {}),
    ('me-ms-cohen', 'William S. Cohen School', 'Bangor', None,
     ['William S. Cohen School', 'William S Cohen School', 'William S. Cohen', 'William S Cohen', 'W.S. Cohen', 'WS Cohen',
      'Cohen', 'Cohen School', 'Cohen MS', 'Cohen Middle School', 'William S Cohen MS'], ['WSCS', 'WSC', 'COH'], [], {}),
    ('me-ms-brewer', 'Brewer Community School', 'Brewer', None,
     ['Brewer Community School', 'Brewer Middle School', 'Brewer MS', 'Brewer CS', 'Brewer Community'], [], [],
     {'notes': "'BCS' is NOT used for Brewer: in MS meets it is Bangor Christian Schools."}),
    ('me-ms-wagner', 'Samuel L. Wagner Middle School', 'Winterport', None,
     ['Samuel L. Wagner Middle School', 'Wagner Middle School', 'Wagner MS', 'Wagner', 'Wagner Middle', 'Wagner School'],
     ['WAG', 'WAGN'], [], {}),
    ('me-ms-central', 'Central Middle School', 'Corinth', None,
     ['Central Middle School', 'Central MS', 'Central Middle', 'Central Midd'], [], [], {}),
    ('me-ms-sumner', 'Sumner Memorial (middle grades)', 'Sullivan', None,
     ['Sumner Middle School', 'Sumner MS', 'Sumner Middle', 'Sumner Learning Campus'], [], [], {}),
    ('me-ms-medway', 'Medway Middle School', 'Medway', None, ['Medway Middle School', 'Medway MS', 'Medway Middl'], [], [], {}),
    ('me-ms-richmond', 'Richmond Middle School', 'Richmond', None, ['Richmond Middle School', 'Richmond MS'], [], [], {}),
    ('me-ms-southern-maine-catholic', 'Southern Maine Catholic (combined MS team)', None, None,
     ['Southern Maine Catholic', 'Southern ME Catholic', 'So. ME Catholic', 'So. Maine Catholic', 'Southern ME Cath',
      'SO Maine Catholic'], [], [], {'kind': 'combined', 'notes': 'Catholic K-8 schools of southern Maine; members not identified.'}),
    ('me-ms-reeds-brook', 'Reeds Brook Middle School', 'Hampden', None,
     ['Reeds Brook Middle School', 'Reeds Brook', 'Reeds Brooks', 'Reeds Brook MS', 'Reeds Brooks MS', 'Reeds Brook Middle'],
     ['RBMS'], [], {}),
    ('me-ms-orono', 'Orono Middle School', 'Orono', None, ['Orono Middle School', 'Orono MS', 'Orono Middle'], ['OMS'], [], {}),
    ('me-ms-leonard', 'Leonard Middle School', 'Old Town', None,
     ['Leonard Middle School', 'Leonard MS', 'Leonard', 'Leonard School', 'J.A. Leonard', 'J.A. Leornard', 'Old Town MS',
      'Old Town Middle School', 'OT LMS', 'OT Lms'], ['LMS', 'OTMS'], [], {}),
    ('me-ms-hermon', 'Hermon Middle School', 'Hermon', None, ['Hermon Middle School', 'Hermon MS', 'Hermon Middle'], ['HMS'], [], {}),
    ('me-ms-glenburn', 'Glenburn School', 'Glenburn', None,
     ['Glenburn School', 'Glenburn', 'Glenburn MS', 'Glenburn Middle School', 'Glenburn Middle'], ['GLEN'], [], {}),
    ('me-ms-veazie', 'Veazie Community School', 'Veazie', None,
     ['Veazie Community School', 'Veazie', 'Veazie MS', 'Veazie School', 'Veazie Community'], ['VZ', 'VCS'], [], {}),
    ('me-ms-holbrook', 'Holbrook School', 'Holden', None, ['Holbrook School', 'Holbrook', 'Holbrook MS'], [], [], {}),
    ('me-ms-dedham', 'Dedham School', 'Dedham', None, ['Dedham School', 'Dedham'], [], [], {}),
    ('me-ms-holbrook-dedham', 'Holbrook/Dedham (combined MS track team)', 'Holden', None,
     ['Holbrook-Dedham', 'Holbrook/Dedham', 'Holbrook/ Dedham', 'Holbrook & Dedham', 'Holbrook-Ded', 'Holbrook/Dedham Track',
      'Holham', 'HolHam', 'HOL-HAM', 'Hol-Ham', 'Holbrook & Dedham Track'], ['HOL'], [],
     {'kind': 'combined', 'members': ['me-ms-holbrook', 'me-ms-dedham'],
      'notes': "Holbrook School (Holden) + Dedham School. 'Holham' is this team (EMMS meets 2012-2018; relays print "
               "\"Holbrook/ Dedham 'A'\" in 2012 EllsworthMSboys_may2), NOT Hall-Dale."}),
    ('me-ms-center-drive', 'Center Drive School', 'Orrington', None,
     ['Center Drive School', 'Center Drive', 'Center Drive MS', 'Center Dr', 'CDS Eagles', 'Cds Eagles'], ['CDS'], [], {}),
    ('me-ms-bucksport', 'Bucksport Middle School', 'Bucksport', None,
     ['Bucksport Middle School', 'Bucksport MS', 'Bucksport Middle'], ['BMS'], [], {}),
    ('me-ms-ellsworth', 'Ellsworth Elementary-Middle School', 'Ellsworth', None,
     ['Ellsworth Elementary-Middle School', 'Ellsworth Elementary Middle School', 'Ellsworth MS', 'Ellsworth Middle School',
      'Ellsworth Elem Mid School', 'Ellsworth Middle'], ['EEMS'], [], {}),
    ('me-ms-mdi-elementary', 'MDI Elementary Schools (combined)', 'Mount Desert Island', None,
     ['MDI Elementary Schools', 'MDI Elementary', 'MDI Elem', 'MDI Schools', 'MDI MS'], [], [], {'kind': 'combined'}),
    ('me-ms-conners-emerson', 'Conners Emerson School', 'Bar Harbor', None,
     ['Conners Emerson School', 'Conners-Emerson', 'Connor-Emerson', 'Connors-Emerson', 'Conners Emerson', 'Emerson School',
      'Emerson'], [], [], {}),
    ('me-ms-mt-desert-elementary', 'Mount Desert Elementary School', 'Northeast Harbor', None,
     ['Mount Desert Elementary School', 'Mt. Desert Elementary School', 'Mt Desert Elementary', 'Mt. Desert Elementary'],
     [], [], {}),
    ('me-ms-beech-hill', 'Beech Hill School', 'Otis', None, ['Beech Hill School', 'Beech Hill'], [], [],
     {'notes': 'PK-8, Hancock County.'}),
    ('me-ms-cave-hill', 'Cave Hill School', 'Eastbrook', None, ['Cave Hill School', 'Cave Hill'], [], [],
     {'notes': 'RSU 24, Hancock County (currently PK-5).'}),
    ('me-ms-hebron', 'Hebron Academy Middle School', 'Hebron', None, ['Hebron Academy Middle School', 'Hebron Academy MS'],
     ['HAMS'], [], {'notes': "'HAMS' in 2018 Tripp meets."}),
    # MileSplit Triple C festival 2013: "Windham/Raymond", RSU 14's two middle schools scored as one team
    ('me-ms-windham-raymond', 'Windham/Raymond (combined RSU 14 MS team)', 'Windham', None,
     ['Windham/Raymond', 'Windham-Raymond'], [], [], {'kind': 'combined', 'members': ['me-ms-windham', 'me-ms-jordan-small']}),
    ('me-ms-durham-freeport', 'Durham/Freeport (combined RSU 5 MS team)', 'Freeport', None,
     ['Durham-Freeport', 'Freeport-Durham', 'Freeport-Durham FMS', 'Durham/Freeport'], [], [],
     {'kind': 'combined', 'members': ['me-ms-durham', 'me-ms-freeport']}),
    ('me-ms-rsu19', 'RSU 19 middle-school team (Nokomis area)', 'Newport', None, ['RSU 19'], [], [],
     {'kind': 'combined', 'notes': "'Warriors' in 2016/2019 Eastern Maine MS meets (medium confidence)."}),
    ('me-ms-whitefield', 'Whitefield Elementary School', 'Whitefield', None,
     ['Whitefield Elementary School', 'Whitefield MS', 'Whitefield School', 'Whitefield'], [], [], {}),
    ('me-ms-athens', 'Athens Community School', 'Athens', None, ['Athens Community School', 'Athens'], [], [], {}),
    ('me-ms-pemetic', 'Pemetic Elementary School', 'Southwest Harbor', None, ['Pemetic School', 'Pemetic'], [], [], {}),
    ('me-ms-tremont', 'Tremont Consolidated School', 'Bass Harbor', None, ['Tremont School', 'Tremont'], [], [], {}),
    ('me-ms-trenton', 'Trenton Elementary School', 'Trenton', None, ['Trenton Elementary', 'Trenton Elem', 'Trenton School', 'Trenton'],
     [], [], {}),
    ('me-ms-lamoine', 'Lamoine Consolidated School', 'Lamoine', None, ['Lamoine Consolidated School', 'Lamoine'], [], [], {}),
    ('me-ms-surry', 'Surry Elementary School', 'Surry', None, ['Surry Elementary', 'Surry School', 'Surry'], [], [], {}),
    ('me-ms-sedgwick', 'Sedgwick Elementary School', 'Sedgwick', None, ['Sedgwick Elementary', 'Sedgwick'], [], [], {}),
    ('me-ms-brooksville', 'Brooksville Elementary School', 'Brooksville', None, ['Brooksville School', 'Brooksville'], [], [], {}),
    ('me-ms-blue-hill', 'Blue Hill Consolidated School', 'Blue Hill', None,
     ['Blue Hill Consolidated School', 'Blue Hill Consolidated', 'Blue Hill', 'Blue Hill MS', 'Blue Hill School'], [], [], {}),
    ('me-ms-bay-school', 'Bay School', 'Blue Hill', None, ['Bay School', 'The Bay School'], [], [], {}),
    # MileSplit Hancock County middle-school meets 2011-2014 (Airline, Coastal, PVMSCC small-school, Parker
    # Pruett): a scored team "Hancock" / "Hancock School" beside Dedham, Surry, Bay School and Blue Hill
    ('me-ms-hancock', 'Hancock Grammar School', 'Hancock', None,
     ['Hancock Grammar School', 'Hancock Grammar', 'Hancock School', 'Hancock'], [], [], {}),
    # MileSplit Parker Pruett MS meet 2011 (Sullivan): five runners
    ('me-ms-swans-island', "Swan's Island School", "Swan's Island", None, ["Swan's Island School", "Swan's Island", 'Swans Island'], [], [], {}),
    # MileSplit Airline Invitational 2012: two runners
    ('me-ms-adams-castine', 'Adams School', 'Castine', None, ['Adams School'], [], [], {}),
    ('me-ms-penobscot', 'Penobscot Elementary School', 'Penobscot', None, ['Penobscot Elementary'], [], [], {}),
    ('me-ms-peninsula', 'Peninsula School', 'Prospect Harbor', None, ['Peninsula School'], [], [], {}),
    ('me-ms-orland', 'Orland Consolidated School', 'Orland', None, ['Orland School', 'Orland'], [], [], {}),
    ('me-ms-dis-elementary', 'Deer Isle-Stonington Elementary School', 'Deer Isle', None, ['Deer Isle-Stonington Elementary'], [], [], {}),
    ('me-ms-airline', 'Airline Community School', 'Aurora', None,
     ['Airline Community School', 'Airline School', 'Airline', 'Airline Sch'], ['AIR'], [], {}),
    ('me-ms-penbrook', 'Penbrook Middle (unidentified)', None, None, ['Penbrook Mid', 'Penbrook', 'PenBrook'], [], [],
     {'notes': 'Appears only in Hancock County XC meets 2023-2025; not identified.'}),
    ('me-ms-troy-howard', 'Troy A. Howard Middle School', 'Belfast', None,
     ['Troy A. Howard Middle School', 'Troy Howard Middle School', 'Troy Howard', 'Troy Howard MS', 'Troy Howard Middle',
      'Belfast Middle School', 'Belfast MS'],
     ['THMS'], [], {}),
    ('me-ms-searsport', 'Searsport Middle School', 'Searsport', None,
     ['Searsport Middle School', 'Searsport MS', 'SearsMiddle', 'Searsport Middle'], [], [], {}),
    ('me-ms-drinkwater', 'Edna Drinkwater School', 'Northport', None,
     ['Edna Drinkwater School', 'Edna Drinkwater', 'Edna Drinkwa', 'Drinkwater School', 'Drinkwater'], ['EDS'], [], {}),
    ('me-ms-camden-rockport', 'Camden-Rockport Middle School', 'Camden', None,
     ['Camden-Rockport Middle School', 'Camden Rockport Middle School', 'Camden Rockport MS', 'Camden-Rockport MS',
      'Camden Rockport Middle', 'Camden Hills Middle School'], ['CRMS'], [],
     {'notes': "'Camden Hills Middle School' in 2012-2013 Busline MS championships: the district's middle school (its runners CRMS elsewhere)."}),
    ('me-ms-oceanside', 'Oceanside Middle School', 'Thomaston', None,
     ['Oceanside Middle School', 'Oceanside MS', 'Oceanside Middle'], ['OMS'], [], {}),
    ('me-ms-rockland', 'Rockland District Middle School', 'Rockland', None,
     ['Rockland District Middle School', 'Rockland MS', 'Rockland District MS'], ['RDMS'], [],
     {'notes': 'Continued after the 2011 RSU 13 merger (RDMS in 2012 meets); later folded into Oceanside MS.'}),
    ('me-ms-lincolnville', 'Lincolnville Central School', 'Lincolnville', None,
     ['Lincolnville Central School', 'Lincolnville School', 'Lincolnville', 'Lincolnville Community School'], ['LCS'], [],
     {'notes': "'LCS' here (2018 Lincolnville XC meet, middle-school level); 'LCS' in high-school meets is Limestone."}),
    ('me-ms-appleton', 'Appleton Village School', 'Appleton', None, ['Appleton Village School', 'Appleton Village', 'Appleton Vil', 'Appleton'],
     [], [], {}),
    ('me-ms-hope', 'Hope Elementary School', 'Hope', None, ['Hope Elementary'], [], [], {}),
    ('me-ms-st-george', 'St. George School', 'Tenants Harbor', None,
     ['St. George School', 'St George School', 'Saint George School', 'St. George', 'St George'], ['STG'], [], {}),
    ('me-ms-medomak', 'Medomak Middle School', 'Waldoboro', None,
     ['Medomak Middle School', 'Medomak MS', 'Medomak Middle', 'Medomak Valley Middle School'], [], [], {}),
    ('me-ms-great-salt-bay', 'Great Salt Bay Community School', 'Damariscotta', None,
     ['Great Salt Bay Community School', 'Great Salt Bay', 'Great Salt Bay School', 'Gr Salt Bay', 'Great Salt Bay MS',
      'Great Salt Bay Middle School'], ['GSB'], [], {}),
    ('me-ms-jefferson', 'Jefferson Village School', 'Jefferson', None,
     ['Jefferson Village School', 'Jefferson Village', 'Jefferson Vi', 'Jefferson'], [], [], {}),
    ('me-ms-nobleboro', 'Nobleboro Central School', 'Nobleboro', None, ['Nobleboro Central School', 'Nobleboro'], [], [], {}),
    ('me-ms-bristol', 'Bristol Consolidated School', 'Pemaquid', None, ['Bristol Consolidated School', 'Bristol Consolidated'], [], [], {}),
    # middle schools first seen in MileSplit's 2026 cross-country results
    ('me-ms-mountain-view-pvmscc', 'Mountain View School', None, None, ['Mountain View School', 'Mountain View MS'], [], [], {}),
    # Bingham's middle grades: 'Quimby (Valley) Middle School' in 2011; 'Valley' / 'Upper Kenneb' in the
    # junior-high meets (the Hartwells and Lays of 2024-26, Levi Short and Harry Louis of 2021)
    ('me-ms-upper-kennebec', 'Upper Kennebec Valley Middle School', 'Bingham', None,
     ['Upper Kennebec Valley Middle School', 'Upper Kennebec Valley MS', 'Upper Kennebec MS', 'UKV MS',
      'Quimby (Valley) Middle School'], [], [], {}),
    ('me-ms-south-portland', 'South Portland Middle School', 'South Portland', None,
     ['South Portland Middle School', 'South Portland MS'], [], [], {}),
    ('me-ms-friends-portland', 'Friends School of Portland', 'Falmouth', None, ['Friends School of Portland', 'Friends School'], [], [], {}),
    ('me-ms-st-johns-brunswick', "St. John's Catholic School", 'Brunswick', None, ["St. John's Catholic School", "St Johns Catholic School"], [], [], {}),
    ('me-ms-st-michael-augusta', 'St. Michael School', 'Augusta', None, ['St. Michael School', 'St Michael School', 'St. Michael'], [], [], {}),
    ('me-ms-mount-jefferson', 'Mount Jefferson Junior High', 'Lee', None, ['Mount Jefferson Junior High', 'Mt. Jefferson JH', 'Mount Jefferson JH'], [], [], {}),
    ('me-ms-helen-dunn', 'Helen Dunn School', None, None, ['Helen Dunn School'], [], [], {}),
    ('me-ms-berwick-academy', 'Berwick Academy (middle grades)', 'South Berwick', None, ['Berwick Academy (middle grades)'], [], [], {}),
    ('me-ms-boothbay', 'Boothbay Region Elementary School (middle grades)', 'Boothbay', None,
     ['Boothbay Middle School', 'Boothbay MS', 'Boothbay Middle', 'Boothbay Region Elementary'], [], [], {}),
    ('me-ms-wiscasset', 'Wiscasset Middle School', 'Wiscasset', None,
     ['Wiscasset Middle School', 'Wiscasset MS', 'Wiscasset Middle', 'Wiscasset Middle High School'], [], [], {}),
    ('me-ms-islesboro', 'Islesboro Central School (middle grades)', 'Islesboro', None, ['Islesboro MS'], ['ICS'], [], {}),
    ('me-ms-rose-gaffney', 'Rose M. Gaffney School', 'Machias', None, ['Rose Gaffney School', 'Rose M. Gaffney School', 'Rose Gaffney'],
     [], [], {}),
    ('me-ms-mt-view', 'Mount View Middle School', 'Thorndike', None,
     ['Mount View Middle School', 'Mt. View Middle School', 'Mt View Middle School', 'Mt. View JH', 'Mt View JH',
      'Mount View Junior High School', 'Mt. View Junior High School', 'Mt. View Middle', 'Mt View Middle', 'Mt. View MS',
      'Mount View JH'], ['MVJH', 'MVJHS', 'MVMS', 'MVJHT'], [], {}),
    ('me-ms-mattanawcook', 'Mattanawcook Junior High School', 'Lincoln', None,
     ['Mattanawcook Junior High School', 'Mattanawcook Junior High', 'Mattanawcook JH', 'Mattanawcook MS'], ['MJHS', 'MJH', 'MJHT'],
     [], {}),
    ('me-ms-indian-island', 'Indian Island School', 'Indian Island', None,
     ['Indian Island School', 'Indian Island', 'Indian Islan', 'Indian Island MS', 'Indian I.'], [], [], {}),
    ('me-ms-lewis-libby', 'Lewis S. Libby School', 'Milford', None,
     ['Lewis S. Libby School', 'Lewis Libby School', 'Lewis Libby', 'Milford', 'Milford MS', 'Milford Middle School',
      'Milford Middle', 'LewisLib/Milford'], ['MIL', 'MILF'], [],
     {'notes': "'Milford' in Maine MS meets is the Lewis Libby School, Milford ME (store wrongly has 'Milford HS')."}),
    ('me-ms-piscataquis', 'Piscataquis Community Middle School', 'Guilford', None,
     ['Piscataquis Community Middle School', 'Piscataquis MS', 'Piscataquis Community MS', 'Piscataquis CMS',
      'Piscataquis Middle', 'Piscatiquis Com Middle School'], ['PCMS'], [], {}),
    ('me-ms-sedomocha', 'SeDoMoCha Middle School', 'Dover-Foxcroft', None,
     ['SeDoMoCha Middle School', 'SeDoMoCha', 'Sedomocha', 'Sedomocha MS', 'SeDoMoCha School', 'Sedomocha Middle',
      'Sedomocha/DF', 'Sodomocha', 'SeDo', 'Sedo'], ['SEDO'], [], {}),
    ('me-ms-nokomis', 'Nokomis Middle School', 'Newport', None, ['Nokomis Middle School', 'Nokomis MS', 'Nokomis Middle'], [], [], {}),
    ('me-ms-ridge-view', 'Ridge View Community School', 'Dexter', None,
     ['Ridge View Community School', 'Ridge View School', 'Ridgeview School', 'Ridge View', 'Ridgeview', 'Ridge View MS'], [], [],
     {'notes': 'RSU 19-area K-8 feeding Dexter/Nokomis.'}),
    ('me-ms-warsaw', 'Warsaw Middle School', 'Pittsfield', None,
     ['Warsaw Middle School', 'Warsaw MS', 'Warsaw JH', 'Warsaw', 'Warsaw Middle', 'Warsaw Elementary'], ['WAJH', 'WARJH'], [], {}),
    ('me-ms-hartland', 'Hartland Consolidated School', 'Hartland', None, ['Hartland Consolidated School', 'Hartland Com', 'Hartland'],
     [], [], {}),
    ('me-ms-caravel', 'Caravel Middle School', 'Carmel', None, ['Caravel Middle School', 'Caravel MS', 'Caravel', 'Caravel Middle'],
     [], [], {}),
    ('me-ms-dexter', 'Dexter Middle School', 'Dexter', None, ['Dexter Middle School', 'Dexter MS'], [], [], {}),
    ('me-ms-penobscot-christian', 'Penobscot Christian School (middle grades)', 'Bangor', None,
     ['Penobscot Christian Middle School', 'Penobscot Christian MS'], [], [], {}),
    ('me-ms-bangor-christian', 'Bangor Christian Schools (middle grades)', 'Bangor', None,
     ['Bangor Christian Middle School', 'Bangor Christian MS'], [], [], {}),
    ('me-ms-all-saints', 'All Saints Catholic School', 'Bangor', None,
     ['All Saints Catholic School', 'All Saints', 'All Saints School', 'All Saints CS', 'All Saints C'], ['ASCS'], [], {}),
    ('me-ms-st-dominic', 'St. Dominic Academy (middle grades)', 'Auburn', None,
     ['St. Dominic Middle School', 'St Dominic MS', 'St Dominic M', 'St. Dominic MS',
      # 'St DOMS MS' (2017 stdomms7); 'Doms'/"Dom's" also here so that in a middle-school meet they mean the middle grades
      # ('DOMS' in the 2018/2021 WMC MS meets) and in a high-school meet the academy
      'St DOMS MS', 'St Doms MS', 'Doms', "Dom's"], [], [], {}),
    # Aroostook
    ('me-ms-presque-isle', 'Presque Isle Middle School', 'Presque Isle', None,
     ['Presque Isle Middle School', 'Presque Isle MS', 'Presque Isle Middle'], ['PIMS'], [], {}),
    ('me-ms-caribou', 'Caribou Middle School', 'Caribou', None, ['Caribou Middle School', 'Caribou MS', 'Caribou Middle'], [], [], {}),
    ('me-ms-fort-fairfield', 'Fort Fairfield Middle School', 'Fort Fairfield', None,
     ['Fort Fairfield Middle School', 'Fort Fairfield MS', 'Ft. Fairfield MS'], ['FFMS'], [], {}),
    ('me-ms-easton', 'Easton Middle School', 'Easton', None, ['Easton MS', 'Easton Middle School'], [], [], {}),
    ('me-ms-limestone', 'Limestone Middle School', 'Limestone', None, ['Limestone Middle', 'Limestone MS'], [], [], {}),
    ('me-ms-ghca', 'Greater Houlton Christian Academy (middle grades)', 'Houlton', None,
     ['GHCA Middle School', 'Ghca Middle School', 'Ghca Middle', 'GHCA MS'], [], [], {}),
    ('me-ms-houlton', 'Houlton Middle School', 'Houlton', None, ['Houlton Middle School', 'Houlton MS'], [], [], {}),
    ('me-ms-woodland', 'Woodland Elementary School', 'Woodland', None, ['Woodland Elementary', 'Woodland Element', 'Woodland School'],
     [], [], {}),
    ('me-ms-union-122', 'Union 122 (combined middle-school team)', None, None, ['Union 122', 'U122', 'Uthirtytwo'], [], [],
     {'kind': 'combined', 'notes': 'Appears in eastern/northern Maine MS outdoor meets 2008-2026; member schools not identified.'}),
    ('me-ms-valley-rivers', 'Valley Rivers Middle School', None, None,
     ['Valley Rivers Middle School', 'Valley Rivers MS', 'Valley Rivers'], ['VRMS'], [],
     {'notes': 'MS outdoor meets 2013-2026; town not identified.'}),
    # Kennebec / Somerset / Franklin
    ('me-ms-waterville', 'Waterville Junior High School', 'Waterville', None,
     ['Waterville Junior High School', 'Waterville Junior High', 'Waterville JH', 'Waterville Jr. High School',
      'Waterville Middle School', 'Waterville MS', 'Waterville Junior High Panther', 'Waterville Junio'], ['WJHS', 'WJH'], [], {}),
    ('me-ms-winslow', 'Winslow Junior High School', 'Winslow', None,
     ['Winslow Junior High School', 'Winslow Junior High', 'Winslow JH', 'Winslow Middle School', 'Winslow MS', 'Winslow Midd'],
     ['WINJH', 'WJHS', 'WJHR'], [], {'notes': "'WJHR' = Winslow JH Raiders (2021 Winslow/Lawrence JH meets)."}),
    ('me-ms-messalonskee', 'Messalonskee Middle School', 'Oakland', None,
     ['Messalonskee Middle School', 'Messalonskee MS', 'Messalonskee Junior High', 'Messalonskee JH', 'Messalonskee Middle',
      'Mesalonskee Junior High School'], ['MMS'], [], {}),
    ('me-ms-china', 'China Middle School', 'China', None, ['China Middle School', 'China MS', 'China'], ['CHIN'], [], {}),
    ('me-ms-lawrence', 'Lawrence Junior High School', 'Fairfield', None,
     ['Lawrence Junior High School', 'Lawrence Junior High', 'Lawrence JH', 'Lawrence Jr. High School', 'Lawrence MS'],
     ['LJHS'], [], {}),
    ('me-ms-skowhegan', 'Skowhegan Area Middle School', 'Skowhegan', None,
     ['Skowhegan Area Middle School', 'Skowhegan Middle School', 'Skowhegan MS', 'Skowhegan JH', 'Skowhegan Junior High'],
     ['SAMS'], [], {}),
    ('me-ms-madison', 'Madison Junior High School', 'Madison', None,
     ['Madison Junior High School', 'Madison JH', 'Madison Junior High', 'Madison MS', 'Madison Middle'], [], [], {}),
    ('me-ms-carrabec', 'Carrabec Community School', 'North Anson', None,
     ['Carrabec Community School', 'Carrabec Community', 'Carrabec MS', 'Carrabec Middle', 'Carrabec Junior High',
      'Carrabec JH'], ['CJHS'], [], {}),
    ('me-ms-cony', 'Cony Middle School', 'Augusta', None,
     ['Cony Middle School', 'Cony MS', 'Cony Middle', 'Cony Junior High'], [], [], {}),
    ('me-ms-hodgkins', 'Hodgkins Middle School', 'Augusta', None, ['Hodgkins Middle School', 'Hodgkins Middle', 'Hodgkins MS'], [], [],
     {'years': [None, 2010]}),
    ('me-ms-hall-dale', 'Hall-Dale Middle School', 'Farmingdale', None,
     ['Hall-Dale Middle School', 'Hall-Dale MS', 'Hall Dale Middle School', 'Hall-Dale Middle', 'Hall Dale MS', 'Hall Dale Middle'],
     [], [], {}),
    ('me-ms-gardiner', 'Gardiner Regional Middle School', 'Gardiner', None,
     ['Gardiner Regional Middle School', 'Gardiner Middle School', 'Gardiner MS', 'Gardiner Area Middle', 'Gardiner Middle'],
     [], [], {}),
    ('me-ms-maranacook', 'Maranacook Community Middle School', 'Readfield', None,
     ['Maranacook Community Middle School', 'Maranacook Middle School', 'Maranacook MS', 'Maranacook Middle'], ['MCMS'], [], {}),
    ('me-ms-winthrop', 'Winthrop Middle School', 'Winthrop', None,
     ['Winthrop Middle School', 'Winthrop MS', 'Winthrop Middle', 'Wintrop Middle'], ['WMS'], [], {}),
    ('me-ms-monmouth', 'Monmouth Middle School', 'Monmouth', None,
     ['Monmouth Middle School', 'Monmouth MS', 'Monmouth Middle', 'Monmouth Academy MS', 'Monmouth Academy Middle School'], [], [], {}),
    ('me-ms-windsor', 'Windsor Elementary School', 'Windsor', None,
     ['Windsor Elementary School', 'Windsor School', 'Windsor', 'Windsor MS', 'Windsor Middle School', 'Windsor Middle'], [], [], {}),
    ('me-ms-mt-blue', 'Mt. Blue Middle School', 'Farmington', None,
     ['Mt. Blue Middle School', 'Mount Blue Middle School', 'Mt. Blue JH', 'Mt Blue JH', 'Mount Blue JH', 'Mt. Blue Junior High',
      'Mount Blue Junior High', 'Mt Blue MS', 'Mt. Blue Middle', 'Mt Blue Middle', 'Mount Blue Junior High School',
      'Mt. Blue Junior High School', 'Mt. Blue MS'], ['MBJH', 'MBJHT', 'MBMS'], [], {}),
    ('me-ms-spruce-mountain', 'Spruce Mountain Middle School', 'Jay', None,
     ['Spruce Mountain Middle School', 'Spruce Mountain MS', 'Spruce Mt MS', 'Spruce Mountain Middle'], ['SMMS'], [],
     {'notes': "'SMMS' (ScoresLJHS 2016-2017, ScoresCALMeet 2021); 'SMMSAC' is a meet name."}),
    ('me-ms-day-mountain', 'Day Mountain Middle School', 'Temple', None, ['Day Mountain Middle School', 'Day Mountain', 'Day Mountain School'],
     [], [], {}),
    ('me-ms-mt-abram', 'Mt. Abram Middle grades (Strong/Kingfield)', None, None, ['Mt. Abram MS', 'Mt Abram Middle School'], [], [], {}),
    ('me-ms-vassalboro', 'Vassalboro Community School', 'Vassalboro', None, ['Vassalboro Community School', 'Vassalboro'], [], [], {}),
    # Androscoggin / Oxford
    ('me-ms-auburn', 'Auburn Middle School', 'Auburn', None,
     ['Auburn Middle School', 'Auburn MS', 'Auburn Middle', 'Auburn Middl'], ['AMS'], [], {}),
    ('me-ms-lewiston', 'Lewiston Middle School', 'Lewiston', None,
     ['Lewiston Middle School', 'Lewiston MS', 'Lewiston Middle'], ['LMS'], [], {}),
    ('me-ms-lisbon', 'Philip W. Sugg Middle School', 'Lisbon', None,
     ['Philip W. Sugg Middle School', 'Sugg Middle School', 'Sugg Middle', 'Lisbon Middle School', 'Lisbon MS', 'Lisbon Middle'],
     [], [], {}),
    ('me-ms-oak-hill', 'Oak Hill Middle School', 'Sabattus', None, ['Oak Hill Middle School', 'Oak Hill MS', 'Oak Hill Middle'], [], [], {}),
    ('me-ms-tripp', 'Tripp Middle School', 'Turner', None,
     ['Tripp Middle School', 'Tripp', 'Tripp MS', 'Tripp Middle', 'Tripp Tigers'], ['TRIPP', 'TMS'], [], {}),
    ('me-ms-whittier', 'Bruce M. Whittier Middle School', 'Poland', None,
     ['Bruce M. Whittier Middle School', 'Whittier Middle School', 'Whittier', 'Whittier MS', 'Whittier Mid', 'Whittier M.S.',
      'Whittier MidKnights', 'Poland Middle School', 'Poland MS', 'Poland Middle'], ['WHIT', 'BMW'], [], {}),
    ('me-ms-oxford-hills', 'Oxford Hills Middle School', 'South Paris', None,
     ['Oxford Hills Middle School', 'Oxford Hills MS', 'Oxford Hills Middle'], ['OHMS'], [], {}),
    ('me-ms-telstar', 'Telstar Middle School', 'Bethel', None, ['Telstar Middle School', 'Telstar MS', 'Telstar Middle'], [], [], {}),
    ('me-ms-dirigo', 'Dirigo Middle School', 'Dixfield', None, ['Dirigo Middle School', 'Dirigo MS', 'Dirigo Middle'], ['DMS'], [], {}),
    ('me-ms-mountain-valley', 'Mountain Valley Middle School', 'Mexico', None,
     ['Mountain Valley Middle School', 'Mountain Valley MS', 'Mt Valley MS', 'Mt. Valley MS', 'Mountain Valley Middle'], [], [], {}),
    ('me-ms-molly-ockett', 'Molly Ockett Middle School', 'Fryeburg', None, ['Molly Ockett Middle School', 'Molly Ockett'], [], [], {}),
    ('me-ms-lake-region', 'Lake Region Middle School', 'Naples', None, ['Lake Region Middle School', 'Lake Region MS'], ['LRMS'], [], {}),
    ('me-ms-sacopee', 'Sacopee Valley Middle School', 'Hiram', None,
     ['Sacopee Valley Middle School', 'Sacopee Valley MS', 'Sacopee MS'], ['SVMS'], [], {}),
    ('me-ms-buckfield', 'Buckfield Junior-Senior High (middle grades)', 'Buckfield', None, ['Buckfield MS'], [], [], {}),
    # Cumberland / Sagadahoc
    ('me-ms-brunswick', 'Brunswick Junior High School', 'Brunswick', None,
     ['Brunswick Junior High School', 'Brunswick Jr. High', 'Brunswick Jr. High School', 'Brunswick Junior High', 'Brunswick JH',
      'Brunswick Middle School', 'Brunswick MS', 'Brunswick Middle', 'Brunswick Jr High Schoolo', 'Brunswick Jr H.S.'],
     ['BJHS', 'BJH'], [], {}),
    ('me-ms-mt-ararat', 'Mt. Ararat Middle School', 'Topsham', None,
     ['Mt. Ararat Middle School', 'Mt Ararat Middle School', 'Mount Ararat Middle School', 'Mt. Ararat MS', 'Mt Ararat MS',
      'Mt. Ararat Middle'], ['MAMS'], [], {}),
    ('me-ms-bath', 'Bath Middle School', 'Bath', None, ['Bath Middle School', 'Bath MS', 'Bath Middle', 'Bath', 'Bath Destroyers'],
     [], ['Destroyers'], {}),
    ('me-ms-woolwich', 'Woolwich Central School', 'Woolwich', None, ['Woolwich Central School', 'Woolwich Central', 'Woolwich'],
     [], [], {}),
    ('me-ms-freeport', 'Freeport Middle School', 'Freeport', None, ['Freeport Middle School', 'Freeport MS', 'Freeport Middle'],
     [], [], {}),
    ('me-ms-durham', 'Durham Community School', 'Durham', None,
     ['Durham Community School', 'Durham Middle School', 'Durham MS', 'Durham', 'Durham Middle'], [], [], {}),
    ('me-ms-greely', 'Greely Middle School', 'Cumberland', None,
     ['Greely Middle School', 'Greely MS', 'Greely Middle', 'Greely Junior High'], [], [], {}),
    ('me-ms-harrison', 'Frank H. Harrison Middle School', 'Yarmouth', None,
     ['Harrison Middle School', 'Harrison MS', 'Harrison Middle', 'Yarmouth Middle School', 'Yarmouth MS', 'Yarmouth Middle'],
     [], [], {}),
    ('me-ms-falmouth', 'Falmouth Middle School', 'Falmouth', None, ['Falmouth Middle School', 'Falmouth MS', 'Falmouth Middle'], ['FMS'],
     [], {}),
    ('me-ms-nya', 'North Yarmouth Academy (middle school)', 'Yarmouth', None, ['NYA MS', 'North Yarmouth Academy MS', 'NYA Middle School'],
     [], [], {}),
    ('me-ms-maine-coast-waldorf', 'Maine Coast Waldorf School (middle grades)', 'Freeport', None,
     ['Maine Coast Waldorf MS', 'Maine Coast MS', 'Maine Coast Waldorf Middle School'], [], [], {}),
    ('me-ms-gray-ng', 'Gray-New Gloucester Middle School', 'Gray', None,
     ['Gray-New Gloucester Middle School', 'Gray New Gloucester MS', 'Gray-New Gloucester MS', 'GNG Middle', 'GNG MS',
      'Gray New Gloucester Middle'], ['GNGMS'], [], {}),
    ('me-ms-windham', 'Windham Middle School', 'Windham', None, ['Windham Middle School', 'Windham MS', 'Windham Middle'], [], [], {}),
    ('me-ms-jordan-small', 'Jordan-Small Middle School', 'Raymond', None,
     ['Jordan-Small Middle School', 'Jordan Small Middle School', 'Jordan Small', 'Jordan-Small', 'Jordan Small MS',
      'Jordan Small Mid', 'Raymond-Jordan Small', 'Jordan Small/ Raymond'], [], [], {}),
    ('me-ms-gorham', 'Gorham Middle School', 'Gorham', None, ['Gorham Middle School', 'Gorham MS', 'Gorham Middle'], ['GMS'], [], {}),
    ('me-ms-westbrook', 'Westbrook Middle School', 'Westbrook', None,
     ['Westbrook Middle School', 'Westbrook MS', 'Westbrook Middle', 'Wescott Junior High', 'Wescott'], [], [], {}),
    ('me-ms-scarborough', 'Scarborough Middle School', 'Scarborough', None,
     ['Scarborough Middle School', 'Scarborough MS', 'Scarborough Middle', 'Scarboro Middle', 'Scarboro MS'], [], [], {}),
    ('me-ms-cape-elizabeth', 'Cape Elizabeth Middle School', 'Cape Elizabeth', None,
     ['Cape Elizabeth Middle School', 'Cape Elizabeth MS', 'Cape Elizabeth Middle'], ['CEMS'], [], {}),
    ('me-ms-mahoney', 'Mahoney Middle School', 'South Portland', None, ['Mahoney Middle School', 'Mahoney MS', 'Mahoney'], ['MAHO'], [],
     {}),
    ('me-ms-memorial-sp', 'Memorial Middle School', 'South Portland', None,
     ['Memorial Middle School', 'Memorial MS', 'Memorial'], ['MEM'], [], {}),
    ('me-ms-king', 'King Middle School', 'Portland', None, ['King Middle School', 'King MS', 'King'], ['KING', 'KNG'], [], {}),
    ('me-ms-lincoln-portland', 'Lincoln Middle School', 'Portland', None, ['Lincoln Middle School', 'Lincoln MS'], [], [], {}),
    ('me-ms-lyman-moore', 'Lyman Moore Middle School', 'Portland', None,
     ['Lyman Moore Middle School', 'Lyman Moore', 'Lyman Moore MS', 'Moore', 'Moore Middle School'], ['LYMO'], [], {}),
    ('me-ms-waynflete', 'Waynflete School (middle grades)', 'Portland', None, ['Waynflete MS', 'Waynflete Middle School'], [], [], {}),
    ('me-ms-holy-cross', 'Holy Cross School', 'South Portland', None, ['Holy Cross School', 'Holy Cross'], [], [], {}),
    ('me-ms-bonny-eagle', 'Bonny Eagle Middle School', 'Buxton', None,
     ['Bonny Eagle Middle School', 'Bonny Eagle MS', 'Bonny Eagle Middle'], ['BEMS'], [], {}),
    ('me-ms-thornton', 'Thornton Academy Middle School', 'Saco', None,
     ['Thornton Academy Middle School', 'Thornton Academy MS', 'Thornton Middle School', 'Thornton MS', 'Thornton Middle'],
     # 'TAMS' (2026-10-19): York County MS meets 2011-21, the 2011 York meet's team block spells it out ("Thornton Academy
     # Middle School 57")
     ['TAMS'], [], {}),
    # York
    ('me-ms-saco', 'Saco Middle School', 'Saco', None, ['Saco Middle School', 'Saco MS', 'Saco Middle', 'Saco'], ['SACO'], [], {}),
    ('me-ms-biddeford', 'Biddeford Middle School', 'Biddeford', None,
     ['Biddeford Middle School', 'Biddeford MS', 'Biddeford Middle'], [], [], {}),
    ('me-ms-loranger', 'Loranger Memorial School', 'Old Orchard Beach', None,
     ['Loranger Memorial School', 'Loranger Memorial', 'Loranger', 'Loranger MS', 'Loranger Middle School',
      'Old Orchard MS', 'Old Orchard Beach MS'], ['LOR'], [], {}),
    ('me-ms-massabesic', 'Massabesic Middle School', 'Waterboro', None,
     ['Massabesic Middle School', 'Massabesic MS', 'Massabesic Middle'], [], [], {}),
    ('me-ms-shapleigh', 'Shapleigh Middle School', 'Kittery', None,
     # 'Kittery' / 'Kit' (2026-10-19): printed only in York County middle-school meets 2005-2022 (smmsaa, Wells MS, York
     # County MS festival); 19-28 rows of each confirmed by their runners' other meets as Shapleigh
     ['Shapleigh Middle School', 'Shapleigh MS', 'Shapleigh Middle', 'Shapleigh School', 'Shapleigh', 'Kittery', 'Kittery MS',
      'Kittery Middle School'], ['KIT'], [],
     {'notes': "Kittery's middle school (feeds Traip). Not Shapleigh Memorial School in Shapleigh."}),
    ('me-ms-sanford', 'Sanford Middle School', 'Sanford', None,
     ['Sanford Middle School', 'Sanford MS', 'Sanford Middle', 'Sanford Junior High'], [], [], {}),
    ('me-ms-kennebunk', 'Middle School of the Kennebunks', 'Kennebunk', None,
     ['Middle School of the Kennebunks', 'Kennebunk Middle School', 'Kennebunk MS', 'Kennebunk Middle'], ['MSK'], [], {}),
    ('me-ms-wells', 'Wells Junior High School', 'Wells', None,
     ['Wells Junior High School', 'Wells Junior High', 'Wells JH', 'Wells Middle School', 'Wells MS', 'Wells Middle'], [], [], {}),
    ('me-ms-marshwood', 'Marshwood Middle School', 'Eliot', None,
     ['Marshwood Middle School', 'Marshwood MS', 'Marshwood Middle'], [], [], {}),
    ('me-ms-noble', 'Noble Middle School', 'Berwick', None, ['Noble Middle School', 'Noble MS', 'Noble Middle'], [], [], {}),
    ('me-ms-york', 'York Middle School', 'York', None, ['York Middle School', 'York MS', 'York Middle'], [], [], {}),
    ('me-ms-seacoast-christian', 'Seacoast Christian School (junior high)', 'South Berwick', None,
     ['Seacoast JH', 'Seacoast Christian JH'], [], [], {}),
    # small K-8 schools printed by name in middle-school XC meets (2026-10-19)
    ('me-ms-carrie-ricker', 'Carrie Ricker Middle School', 'Litchfield', None,
     ['Carrie Ricker Middle School', 'Carrie Ricker MS', 'Carrie Ricker M S.', 'Carrie Ricker'], [], [],
     {'notes': 'Monmouth MS meets 2008.'}),
    ('me-ms-elm-street', 'Elm Street School', 'East Machias', None, ['Elm Street School', 'Elm Street'], [], [],
     {'notes': "Airline invitationals 2024-25 ('Elm Street S')."}),
    ('me-ms-cherryfield', 'Cherryfield Elementary School', 'Cherryfield', None,
     ['Cherryfield Elementary School', 'Cherryfield School', 'Cherryfield'], [], [], {'notes': 'Airline invitational 2024.'}),
    ('me-ms-south-bristol', 'South Bristol School', 'South Bristol', None, ['South Bristol School', 'South Bristol'], [], [],
     {'notes': 'Great Salt Bay / Busline middle-school meets 2017.'}),
    ('me-ms-mirus', 'Mirus Academy', None, None, ['Mirus Academy', 'Mirus'], [], [],
     {'notes': 'Airline and Parker Pruett middle-school invitationals 2016-18; location not verified.'}),
]

# ---------------------------------------------------------------------------
# Colleges (curated; level 'college')
# ---------------------------------------------------------------------------
COLLEGES = [
    ('col-bates', 'Bates College', 'Lewiston', None, ['Bates College', 'Bates'], [], ['Bobcats'], {'state': 'ME'}),
    ('col-bowdoin', 'Bowdoin College', 'Brunswick', None, ['Bowdoin College', 'Bowdoin'], ['BOWI'], ['Polar Bears'], {'state': 'ME'}),
    ('col-colby', 'Colby College', 'Waterville', None, ['Colby College', 'Colby'], [], ['Mules'], {'state': 'ME'}),
    ('col-husson', 'Husson University', 'Bangor', None, ['Husson University', 'Husson', 'Husson College'], [], ['Eagles'], {'state': 'ME'}),
    ('col-umaine', 'University of Maine', 'Orono', None,
     ['University of Maine', 'Maine', 'UMaine', 'Univ of Maine', 'U of Maine', 'Maine Track', 'University o'], ['UM'], ['Black Bears'],
     {'state': 'ME', 'notes': "Bare 'Maine' in college meets is UMaine."}),
    ('col-usm', 'University of Southern Maine', 'Gorham', None,
     ['University of Southern Maine', 'Southern Maine', 'Southern Mai', 'So. Maine', 'Southern Maine C'], ['USM'], ['Huskies'],
     {'state': 'ME'}),
    ('col-umf', 'University of Maine at Farmington', 'Farmington', None,
     ['University of Maine at Farmington', 'Maine-Farmington', 'Maine-Farmin', 'U ME Farmington', 'MaineFarmington', 'UMaine Farmington',
      'Farmington'], ['UMF'], ['Beavers'], {'state': 'ME'}),
    ('col-umpi', 'University of Maine at Presque Isle', 'Presque Isle', None,
     ['University of Maine at Presque Isle', 'Maine-Presque Isle', 'Maine-Presqu', 'UM Presque Isle'], ['UMPI'], ['Owls'],
     {'state': 'ME'}),
    ('col-umfk', 'University of Maine at Fort Kent', 'Fort Kent', None,
     ['University of Maine at Fort Kent', 'Maine-Fort Kent', 'Maine-Fort K'], ['UMFK'], ['Bengals'], {'state': 'ME'}),
    ('col-uma', 'University of Maine at Augusta', 'Augusta', None,
     ['University of Maine at Augusta', 'Maine-Augusta', 'Maine-August'], ['UMA'], [], {'state': 'ME'}),
    ('col-mma', 'Maine Maritime Academy', 'Castine', None, ['Maine Maritime Academy', 'Maine Maritime', 'Maine Mariti', 'Maine Maratime'],
     ['MMA'], [], {'state': 'ME'}),
    ('col-thomas', 'Thomas College', 'Waterville', None, ['Thomas College', 'Thomas', 'Thomas Colle'], [], [], {'state': 'ME'}),
    ('col-sjc-maine', "Saint Joseph's College of Maine", 'Standish', None,
     ["Saint Joseph's College of Maine", "St. Joseph's", "St. Joseph's (Me.)", "St Joseph's", 'St Josephs', 'St Joes', 'ST JOES',
      "St. Joseph's College", 'St Josephs Me', "St. Joseph's (M"], [], ['Monks'], {'state': 'ME'}),
    ('col-une', 'University of New England', 'Biddeford', None,
     ['University of New England', 'U. of New England', 'U. of New En', 'U of New England', 'Univ of NE', 'U. of New Engl'], ['UNE'],
     ['Nor\'easters'], {'state': 'ME'}),
    ('col-smcc', 'Southern Maine Community College', 'South Portland', None,
     ['Southern Maine Community College', 'Southern Maine CC'], ['SMCC'], [], {'state': 'ME'}),
    ('col-cmcc', 'Central Maine Community College', 'Auburn', None, ['Central Maine Community College'], ['CMCC'], [], {'state': 'ME'}),
    ('col-colby-sawyer', 'Colby-Sawyer College', 'New London', None, ['Colby-Sawyer College', 'Colby-Sawyer', 'ColbySawyer'], [], [],
     {'state': 'NH'}),
    ('col-unh', 'University of New Hampshire', 'Durham', None,
     ['University of New Hampshire', 'New Hampshire', 'New Hampshir', 'Univ of New Hampshire'], ['UNH'], ['Wildcats'], {'state': 'NH'}),
    ('col-plymouth-state', 'Plymouth State University', 'Plymouth', None, ['Plymouth State', 'Plymouth Sta', 'Plymouth St.'], [], [],
     {'state': 'NH'}),
    ('col-keene-state', 'Keene State College', 'Keene', None, ['Keene State', 'Keene State College'], [], [], {'state': 'NH'}),
    ('col-snhu', 'Southern New Hampshire University', 'Manchester', None, ['Southern New Hampshire University'], ['SNHU'], [],
     {'state': 'NH'}),
    ('col-st-anselm', 'Saint Anselm College', 'Manchester', None, ['Saint Anselm', 'St. Anselm', 'St Anselm'], [], [], {'state': 'NH'}),
    ('col-franklin-pierce', 'Franklin Pierce University', 'Rindge', None, ['Franklin Pierce'], [], [], {'state': 'NH'}),
    ('col-dartmouth', 'Dartmouth College', 'Hanover', None, ['Dartmouth College', 'Dartmouth'], [], [], {'state': 'NH'}),
    ('col-new-england-college', 'New England College', 'Henniker', None, ['New England College'], [], [], {'state': 'NH'}),
    ('col-uvm', 'University of Vermont', 'Burlington', None, ['University of Vermont', 'Vermont'], ['UVM'], [], {'state': 'VT'}),
    ('col-middlebury', 'Middlebury College', 'Middlebury', None, ['Middlebury College', 'Middlebury'], [], [], {'state': 'VT'}),
    ('col-castleton', 'Castleton University', 'Castleton', None, ['Castleton University', 'Castleton', 'Castleton Un'], [], [], {'state': 'VT'}),
    ('col-vermont-state', 'Vermont State University', None, None, ['Vermont State', 'Vermont Stat', 'NVU-Johnson', 'Nvu-Johnson',
                                                                    'NVU- Johnson', 'Vermont Tech',
                                                                    # its Johnson campus's earlier name (NAC meets 2015-17)
                                                                    'Johnson State College', 'Johnson State', 'Johnson St.'], [], [], {'state': 'VT'}),
    ('col-uconn', 'University of Connecticut', 'Storrs', None, ['University of Connecticut', 'Connecticut', 'UConn'], [], [], {'state': 'CT'}),
    ('col-uri', 'University of Rhode Island', 'Kingston', None, ['University of Rhode Island', 'Rhode Island'], ['URI'], [], {'state': 'RI'}),
    ('col-tufts', 'Tufts University', 'Medford', None, ['Tufts University', 'Tufts'], [], [], {'state': 'MA'}),
    ('col-mit', 'Massachusetts Institute of Technology', 'Cambridge', None, ['MIT', 'M I T'], ['MIT'], [], {'state': 'MA'}),
    ('col-wpi', 'Worcester Polytechnic Institute', 'Worcester', None, ['Worcester Polytechnic Institute', 'W P I'], ['WPI'], [],
     {'state': 'MA'}),
    ('col-brandeis', 'Brandeis University', 'Waltham', None, ['Brandeis University', 'Brandeis'], [], [], {'state': 'MA'}),
    ('col-bentley', 'Bentley University', 'Waltham', None, ['Bentley University', 'Bentley'], [], [], {'state': 'MA'}),
    ('col-assumption', 'Assumption University', 'Worcester', None, ['Assumption', 'Assumption College'], [], [], {'state': 'MA'}),
    ('col-worcester-state', 'Worcester State University', 'Worcester', None, ['Worcester State', 'Worcester St'], [], [], {'state': 'MA'}),
    ('col-fitchburg-state', 'Fitchburg State University', 'Fitchburg', None, ['Fitchburg State', 'Fitchburg St', 'Fitchburg St.'], [], [],
     {'state': 'MA'}),
    ('col-westfield-state', 'Westfield State University', 'Westfield', None, ['Westfield State', 'Westfield St'], [], [], {'state': 'MA'}),
    ('col-bridgewater-state', 'Bridgewater State University', 'Bridgewater', None,
     ['Bridgewater State', 'Bridgewater St.', 'Bridgewater St', 'Bridgewater'], [], [], {'state': 'MA'}),
    ('col-framingham-state', 'Framingham State University', 'Framingham', None, ['Framingham State', 'Framingham St'], [], [], {'state': 'MA'}),
    ('col-umass-boston', 'UMass Boston', 'Boston', None, ['UMass Boston', 'Umass Boston'], [], [], {'state': 'MA'}),
    ('col-umass-dartmouth', 'UMass Dartmouth', 'Dartmouth', None, ['UMass Dartmouth', 'Umass Dartmouth', 'UMass Dartmo', 'UM-Dart'], [], [],
     {'state': 'MA'}),
    ('col-umass-amherst', 'UMass Amherst', 'Amherst', None, ['UMass Amherst', 'Umass Amherst'], [], [], {'state': 'MA'}),
    ('col-umass-lowell', 'UMass Lowell', 'Lowell', None, ['UMass Lowell', 'Umass Lowell'], [], [], {'state': 'MA'}),
    ('col-wellesley', 'Wellesley College', 'Wellesley', None, ['Wellesley College', 'Wellesley'], [], [], {'state': 'MA'}),
    ('col-williams', 'Williams College', 'Williamstown', None, ['Williams College', 'Williams'], [], [], {'state': 'MA'}),
    ('col-amherst', 'Amherst College', 'Amherst', None, ['Amherst College'], [], [], {'state': 'MA'}),
    ('col-smith', 'Smith College', 'Northampton', None, ['Smith College', 'Smith Colleg'], [], [], {'state': 'MA'}),
    ('col-mount-holyoke', 'Mount Holyoke College', 'South Hadley', None, ['Mount Holyoke', 'Mount Holyok', 'Mt. Holyoke'], [], [],
     {'state': 'MA'}),
    ('col-springfield', 'Springfield College', 'Springfield', None, ['Springfield College', 'Springfield'], [], [], {'state': 'MA'}),
    ('col-emmanuel', 'Emmanuel College', 'Boston', None, ['Emmanuel College', 'Emmanuel', 'Emmanuel (Mass.)', 'Emmanuel (Ma'], [], [],
     {'state': 'MA'}),
    ('col-regis', 'Regis College', 'Weston', None, ['Regis College', 'Regis (Mass.)', 'Regis (Mass.', 'Regis MA', 'Regis'], [], [],
     {'state': 'MA'}),
    ('col-lasell', 'Lasell University', 'Newton', None, ['Lasell', 'Lasell University'], [], [], {'state': 'MA'}),
    ('col-endicott', 'Endicott College', 'Beverly', None, ['Endicott College', 'Endicott'], [], [], {'state': 'MA'}),
    ('col-gordon', 'Gordon College', 'Wenham', None, ['Gordon College', 'Gordon'], [], [], {'state': 'MA'}),
    ('col-wheaton', 'Wheaton College', 'Norton', None, ['Wheaton College', 'Wheaton', 'Wheaton (Mass.)', 'Wheaton (Mas', 'Wheaton MA'],
     [], [], {'state': 'MA'}),
    ('col-stonehill', 'Stonehill College', 'Easton', None, ['Stonehill College', 'Stonehill'], [], [], {'state': 'MA'}),
    ('col-suffolk', 'Suffolk University', 'Boston', None, ['Suffolk University', 'Suffolk'], [], [], {'state': 'MA'}),
    ('col-nichols', 'Nichols College', 'Dudley', None, ['Nichols College', 'Nichols'], [], [], {'state': 'MA'}),
    ('col-northeastern', 'Northeastern University', 'Boston', None, ['Northeastern University', 'Northeastern'], [], [], {'state': 'MA'}),
    ('col-lesley', 'Lesley University', 'Cambridge', None, ['Lesley University', 'Lesley'], [], [], {'state': 'MA'}),
    ('col-simmons', 'Simmons University', 'Boston', None, ['Simmons University', 'Simmons'], [], [], {'state': 'MA'}),
    ('col-babson', 'Babson College', 'Wellesley', None, ['Babson College', 'Babson'], [], [], {'state': 'MA'}),
    ('col-mass-maritime', 'Massachusetts Maritime Academy', 'Buzzards Bay', None,
     ['Massachusetts Maritime Academy', 'Mass. Maritime', 'Mass. Mariti', 'Mass Maritime'], [], [], {'state': 'MA'}),
    ('col-eastern-nazarene', 'Eastern Nazarene College', 'Quincy', None, ['Eastern Nazarene'], [], [], {'state': 'MA'}),
    ('col-coast-guard', 'U.S. Coast Guard Academy', 'New London', None, ['Coast Guard Academy', 'Coast Guard'], [], [], {'state': 'CT'}),
    ('col-trinity', 'Trinity College', 'Hartford', None, ['Trinity College', 'Trinity'], [], [], {'state': 'CT'}),
    ('col-wesleyan', 'Wesleyan University', 'Middletown', None, ['Wesleyan University', 'Wesleyan'], [], [], {'state': 'CT'}),
    ('col-conn-college', 'Connecticut College', 'New London', None, ['Connecticut College'], [], [], {'state': 'CT'}),
    ('col-eastern-conn', 'Eastern Connecticut State University', 'Willimantic', None,
     ['Eastern Connecticut State', 'Eastern Conn. St.', 'Eastern Conn St', 'Eastern Conn', 'E. Conn. St.'], [], [], {'state': 'CT'}),
    ('col-southern-conn', 'Southern Connecticut State University', 'New Haven', None,
     ['Southern Connecticut State', 'So Conn State', 'So. Conn. St'], [], [], {'state': 'CT'}),
    ('col-central-conn', 'Central Connecticut State University', 'New Britain', None, ['Central Connecticut', 'Cen Conn'], [], [],
     {'state': 'CT'}),
    ('col-sacred-heart', 'Sacred Heart University', 'Fairfield', None, ['Sacred Heart University', 'Sacred Heart'], [], [], {'state': 'CT'}),
    ('col-quinnipiac', 'Quinnipiac University', 'Hamden', None, ['Quinnipiac'], [], [], {'state': 'CT'}),
    ('col-salve-regina', 'Salve Regina University', 'Newport', None, ['Salve Regina'], [], [], {'state': 'RI'}),
    ('col-roger-williams', 'Roger Williams University', 'Bristol', None, ['Roger Williams', 'Roger Willia'], [], [], {'state': 'RI'}),
    ('col-plattsburgh', 'SUNY Plattsburgh', 'Plattsburgh', None, ['Plattsburgh State', 'Plattsburgh St'], [], [], {'state': 'NY'}),
    ('col-army', 'U.S. Military Academy', 'West Point', None, ['Army', 'Army West Point'], [], [], {'state': 'NY'}),
    ('col-unb', 'University of New Brunswick', 'Fredericton', None, ['University of New Brunswick', 'UNB'], [], [], {'state': 'NB'}),
    # colleges seen in XC college meets (Husson / Bowdoin / Bates / Thomas invitationals, NAC and DIII championships, UMD,
    # Army-Maine duals), 2026-10-19; names as the results print them
    ('col-umm', 'University of Maine at Machias', 'Machias', None,
     ['University of Maine at Machias', 'Univ. Maine Machias', 'Maine-Machias', 'UMaine Machias'], [], [], {'state': 'ME'}),
    ('col-unity', 'Unity College', 'Unity', None, ['Unity College', 'Unity'], [], [], {'state': 'ME'}),
    ('col-yccc', 'York County Community College', 'Wells', None,
     ['York County Community College', 'York County CC', 'YCCC'], [], [], {'state': 'ME'}),
    ('col-kvcc', 'Kennebec Valley Community College', 'Fairfield', None,
     ['Kennebec Valley Community College', 'Kennebec Valley CC'], [], [], {'state': 'ME'}),
    ('col-lyndon', 'Northern Vermont University-Lyndon (Lyndon State College)', 'Lyndonville', None,
     ['Lyndon State College', 'Lyndon State', 'NVU-Lyndon', 'NVU- Lyndon', 'NVU Lyndon', 'NVU-Lydon'], [], [], {'state': 'VT'}),
    ('col-green-mountain', 'Green Mountain College', 'Poultney', None, ['Green Mountain College'], [], [],
     {'state': 'VT', 'notes': "Bare 'Green Mountain' is also Green Mountain Union HS (VT) and a youth club: file rules only."}),
    ('col-southern-vermont', 'Southern Vermont College', 'Bennington', None, ['Southern Vermont College'], [], [], {'state': 'VT'}),
    ('col-western-new-england', 'Western New England University', 'Springfield', None,
     ['Western New England University', 'Western New England', 'Western NE'], [], [], {'state': 'MA'}),
    ('col-elms', 'Elms College', 'Chicopee', None, ['Elms College', 'Elms'], [], [], {'state': 'MA'}),
    ('col-wentworth', 'Wentworth Institute of Technology', 'Boston', None,
     ['Wentworth Institute of Technology', 'Wentworth Institute of Tech', 'Wentworth'], [], [], {'state': 'MA'}),
    ('col-mcla', 'Massachusetts College of Liberal Arts', 'North Adams', None,
     ['Massachusetts College of Liberal Arts', 'Mass. Liberal Arts', 'MCLA'], [], [], {'state': 'MA'}),
    ('col-curry', 'Curry College', 'Milton', None, ['Curry College', 'Curry'], [], [], {'state': 'MA'}),
    ('col-wheelock', 'Wheelock College', 'Boston', None, ['Wheelock College', 'Wheelock'], [], [], {'state': 'MA'}),
    ('col-aic', 'American International College', 'Springfield', None,
     ['American International College', "American Int'l"], [], [], {'state': 'MA'}),
    ('col-mount-ida', 'Mount Ida College', 'Newton', None, ['Mount Ida College', 'Mount Ida'], [], [], {'state': 'MA'}),
    ('col-anna-maria', 'Anna Maria College', 'Paxton', None, ['Anna Maria College', 'Anna Maria'], [], [], {'state': 'MA'}),
    ('col-northern-essex', 'Northern Essex Community College', 'Haverhill', None,
     ['Northern Essex Community College', 'Northern Essex CC', 'No. Essex'], [], [], {'state': 'MA'}),
    ('col-rivier', 'Rivier University', 'Nashua', None, ['Rivier University', 'Rivier'], [], [], {'state': 'NH'}),
    ('col-bryant', 'Bryant University', 'Smithfield', None, ['Bryant University', 'Bryant'], [], [], {'state': 'RI'}),
    ('col-johnson-wales', 'Johnson & Wales University', 'Providence', None,
     ['Johnson & Wales University', 'Johnson & Wales'], [], [], {'state': 'RI'}),
    ('col-ccri', 'Community College of Rhode Island', 'Warwick', None,
     ['Community College of Rhode Island', 'CC Rhode Island'], [], [], {'state': 'RI'}),
    ('col-rpi', 'Rensselaer Polytechnic Institute', 'Troy', None, ['Rensselaer Polytechnic Institute', 'Rensselaer', 'RPI'], [], [],
     {'state': 'NY'}),
    ('col-suny-canton', 'SUNY Canton', 'Canton', None, ['SUNY Canton'], [], [], {'state': 'NY'}),
    ('col-suny-poly', 'SUNY Polytechnic Institute', 'Utica', None, ['SUNY Polytechnic Institute', 'SUNY Poly'], [], [],
     {'state': 'NY'}),
    ('col-morrisville', 'Morrisville State College', 'Morrisville', None, ['Morrisville State College', 'Morrisville State'], [], [],
     {'state': 'NY'}),
    ('col-suny-cobleskill', 'SUNY Cobleskill', 'Cobleskill', None, ['SUNY Cobleskill'], [], [], {'state': 'NY'}),
    ('col-suny-delhi', 'SUNY Delhi', 'Delhi', None, ['SUNY Delhi'], [], [], {'state': 'NY'}),
    ('col-suny-new-paltz', 'SUNY New Paltz', 'New Paltz', None, ['SUNY New Paltz', 'New Paltz St.', 'New Paltz St', 'New Paltz State'],
     [], [], {'state': 'NY'}),
    ('col-cazenovia', 'Cazenovia College', 'Cazenovia', None, ['Cazenovia College'], [], [], {'state': 'NY'}),
    ('col-adelphi', 'Adelphi University', 'Garden City', None, ['Adelphi University', 'Adelphi'], [], [], {'state': 'NY'}),
    ('col-navy', 'U.S. Naval Academy', 'Annapolis', None, ['U.S. Naval Academy', 'Naval Academy'], [], [], {'state': 'MD'}),
    ('col-salisbury', 'Salisbury University', 'Salisbury', None, ['Salisbury University'], [], [],
     {'state': 'MD', 'notes': "Bare 'Salisbury' is also Salisbury School (CT): file rules only."}),
    ('col-elmhurst', 'Elmhurst University', 'Elmhurst', None, ['Elmhurst University', 'Elmhurst College', 'Elmhurst'], [], [],
     {'state': 'IL'}),
]

# ---------------------------------------------------------------------------
# Clubs and other non-school entries
# ---------------------------------------------------------------------------
CLUBS = [
    ('club-hermon-hawks-tc', 'Hawks Track Club (Hermon youth)', 'Hermon', None,
     ['Hawks Track and Field Club', 'Hermon Track and Field Club'], ['HTC'], [], {'state': 'ME',
      'notes': "'Hawks Track Club' in HS meets is Hermon HS; HTC youth labels appear in summer meets."}),
    ('club-gorham-tc', 'Gorham Track Club', 'Gorham', None, ['Gorham TC'], [], [], {'state': 'ME'}),
    ('club-warrior-tc', 'Warrior Track Club', None, None, ['Warrior TC', 'Warrior Track Club', 'Warrior Tk Club', 'Warrior Track'], [], [],
     {'state': 'ME'}),
    ('club-augusta-track', 'Augusta Track Club', 'Augusta', None, ['Augusta Track', 'AUGUSTA TRACK'], [], [], {'state': 'ME'}),
    ('club-yes-bounders', 'Yes Bounders', None, None, ['Yes Bounders'], [], [], {'state': 'ME'}),
    ('club-lakers-tc', 'Lakers Track Club', 'Augusta', None, ['Lakers Track Club', 'Lakers Track', 'Lakers TC'], [], [],
     {'state': 'ME', 'notes': 'Augusta USATF youth club (USATF JO / Region 1 XC 2004, 2009-2012; Maine USATF 2015-2016).'}),
    # middle-school XC meets 2011-2014 (Waterville JH meets, Winthrop MS invitational): a scored team
    # "Sandy River"; every one of its runners in the summer data runs for SRTC, and they later run
    # for Mt. Blue HS (the district fields "Mt. Blue JH" from 2017). The Farmington club's fall team.
    ('club-sandy-river-tc', 'Sandy River Track Club (Farmington youth)', 'Farmington', None,
     ['Sandy River', 'Sandy R', 'Sandy River Track Club', 'Sandy River TC', 'SRTC'], [], [],
     {'state': 'ME', 'notes': "Fall middle-school XC team of the Farmington youth club, 2011-2014 (not a school)."}),
    # Winthrop MS meets 2010: recreation-department youth teams, not schools (their runners
    # later run for several high schools; summer clubs Lisbon Striders / Augusta)
    ('club-lewiston-rec', 'Lewiston Recreation (youth)', 'Lewiston', None, ['Lewiston Rec', 'Lewiston Recreation'], [], [],
     {'state': 'ME'}),
    ('club-cony-rec', 'Cony Recreation (Augusta youth)', 'Augusta', None, ['Cony Recreation', 'Cony Rec'], [], [],
     {'state': 'ME', 'notes': "Runners later at Cony HS; summer club Augusta."}),
    # Winthrop MS championships 2021-24: 'Winthrop REC' is a scored youth team printed beside Winthrop's own middle school
    # ('Winthrop MS' / 'Winthrop') in the same races: the recreation department's team, not a school
    ('club-winthrop-rec', 'Winthrop Recreation (youth)', 'Winthrop', None, ['Winthrop REC', 'Winthrop Rec', 'Winthrop Recreation'],
     [], [], {'state': 'ME'}),
]

# ---------------------------------------------------------------------------
# Out-of-state high schools that appear in Maine results (New England meets,
# invitationals). Only names that are unambiguous without a state tag are
# listed; strings printed WITH a state tag ('Cumberland - RI') get automatic
# entries from the builder, and bare strings ('Cumberland') are tied to those
# by athlete continuity.  (state, name, aliases)
# ---------------------------------------------------------------------------
_OOS_SIMPLE = [
    ('NH', 'Phillips Exeter Academy', ['Phillips Exeter', 'Phillips Exe', 'Exeter Academy']),
    ('NH', 'Exeter High School', ['Exeter', 'Exeter HS']),
    ('NH', 'Pinkerton Academy', ['Pinkerton', 'Pinkerton Ac']),
    ('NH', 'Bishop Guertin High School', ['Bishop Guertin', 'Bishop Guert', 'B. Guertin']),
    ('NH', 'Nashua High School North', ['Nashua North']),
    ('NH', 'Nashua High School South', ['Nashua South']),
    ('NH', 'Winnacunnet High School', ['Winnacunnet']),
    ('NH', 'Londonderry High School', ['Londonderry']),
    ('NH', 'Coe-Brown Northwood Academy', ['Coe-Brown', 'Coe Brown']),
    ('NH', 'Timberlane Regional High School', ['Timberlane']),
    ('NH', 'Oyster River High School', ['Oyster River']),
    ('NH', 'Kearsarge Regional High School', ['Kearsarge']),
    ('NH', 'Souhegan High School', ['Souhegan']),
    ('NH', 'Alvirne High School', ['Alvirne']),
    ('NH', 'Monadnock Regional High School', ['Monadnock']),
    ('NH', 'Mascoma Valley Regional High School', ['Mascoma Valley', 'Mascoma Vall']),
    ('NH', 'John Stark Regional High School', ['John Stark']),
    ('NH', 'Bow High School', ['Bow']),
    ('NH', 'Hollis Brookline High School', ['Hollis/Brook', 'Hollis Brookline', 'Hollis-Brookline']),
    ('NH', 'Manchester Memorial High School', ['Manchester Memorial', 'Manchester M']),
    ('NH', 'Manchester Central High School', ['Manchester Central', 'Manchester C']),
    ('NH', 'Pelham High School', ['Pelham']),
    ('NH', 'Hanover High School', ['Hanover']),
    ('MA', "The Governor's Academy", ["The Governor's Academy", 'The Governor', 'Governors Academy']),
    ('MA', 'Andover High School', ['Andover']),
    ('MA', 'Austin Preparatory School', ['Austin Prep', 'Austin']),
    ('MA', 'Central Catholic High School', ['Central Catholic', 'Central Cath']),
    ('MA', 'Tewksbury Memorial High School', ['Tewksbury']),
    ('MA', 'Amherst-Pelham Regional High School', ['Amherst-Pelham']),
    ('MA', 'Triton Regional High School', ['Triton']),
    ('MA', 'Dracut High School', ['Dracut']),
    ('MA', 'Methuen High School', ['Methuen']),
    ('MA', 'Billerica Memorial High School', ['Billerica']),
    ('MA', 'Haverhill High School', ['Haverhill']),
    ('MA', 'Chelmsford High School', ['Chelmsford']),
    ('MA', 'Lowell High School', ['Lowell']),
    ('MA', 'Peabody Veterans Memorial High School', ['Peabody']),
    ('MA', 'Somerville High School', ['Somerville']),
    ('MA', 'Reading Memorial High School', ['Reading']),
    ('MA', 'Medway High School', ['Medway']),
    ('MA', 'Newton North High School', ['Newton North']),
    ('MA', 'Whitman-Hanson Regional High School', ['Whitman-Hanson', 'Whitman-Hans']),
    ('MA', 'Natick High School', ['Natick']),
    ('MA', 'Arlington Catholic High School', ['Arlington Catholic', 'Arlington Ca']),
    ('MA', 'Bradford Christian Academy', ['Bradford Christian', 'Bradford Chr']),
    ('MA', 'Plymouth South High School', ['Plymouth South', 'Plymouth Sou']),
    ('MA', 'North Attleborough High School', ['North Attleborough', 'North Attleb']),
    ('MA', 'Greenfield High School', ['Greenfield']),
    ('RI', 'Burrillville High School', ['Burrillville']),
    ('RI', 'East Greenwich High School', ['East Greenwich', 'East Greenwich HS', 'E. Greenwich']),
    ('RI', 'Classical High School', ['Classical']),
    ('RI', 'La Salle Academy', ['La Salle', 'LaSalle Academy', 'La Salle Academy', 'LaSalle Acad', 'La Salle Aca']),
    ('RI', 'Bishop Hendricken High School', ['Bishop Hendricken', 'Bishop Hendr', 'BishopHendricken', 'Hendricken',
                                            'B.Hendricken']),
    ('RI', 'Mount Saint Charles Academy', ['Mt. St. Charles', 'Mt Saint Charles', 'Mount St Charles', 'Mt St Charles',
                                          'Mt Saint CharlesRI']),
    ('RI', 'The Wheeler School', ['The Wheeler School', 'Wheeler']),
    ('RI', 'Moses Brown School', ['Moses Brown']),
    ('RI', 'Woonsocket High School', ['Woonsocket']),
    ('RI', 'West Warwick High School', ['West Warwick']),
    ('RI', 'South Kingstown High School', ['South Kingstown', 'S.Kingstown']),
    ('RI', 'North Kingstown High School', ['North Kingstown', 'N.Kingstown', 'North Kingst']),
    ('RI', 'Cranston High School West', ['Cranston West']),
    ('RI', 'Westerly High School', ['Westerly']),
    ('RI', 'Chariho Regional High School', ['Chariho']),
    ('RI', 'Ponaganset High School', ['Ponaganset']),
    ('VT', 'Harwood Union High School', ['Harwood Union', 'Harwood']),
    ('VT', 'Essex High School', ['Essex']),
    ('VT', 'Champlain Valley Union High School', ['Champlain Valley', 'Champlain Va', 'Champlain Val', 'CVU']),
    ('VT', 'Mount Mansfield Union High School', ['Mt Mansfield', 'Mt. Mansfield', 'Mount Mansfield']),
    ('VT', 'St. Johnsbury Academy', ['St Johnsbury', 'St. Johnsbury']),
    ('VT', 'Bellows Free Academy', ['Bellows Free']),
    ('VT', 'Bellows Falls Union High School', ['Bellows Falls', 'Bellows Fall']),
    ('VT', 'Brattleboro Union High School', ['Brattleboro']),
    ('VT', 'Thetford Academy', ['Thetford Academy', 'Thetford Aca', 'Thetford']),
    ('VT', 'Mount Anthony Union High School', ['Mt Anthony', 'Mt Anthony U', 'Mount Anthony']),
    ('VT', 'South Burlington High School', ['South Burlington', 'South Burlin', 'S. Burlington']),
    ('VT', 'Colchester High School', ['Colchester']),
    ('VT', 'U-32 High School', ['U-32', 'U32']),
    ('VT', 'Burr and Burton Academy', ['Burr and Burton', 'Burr And Bur']),
    ('CT', 'Glastonbury High School', ['Glastonbury']),
    ('CT', 'Trumbull High School', ['Trumbull']),
    ('CT', 'Danbury High School', ['Danbury']),
    ('CT', 'Simsbury High School', ['Simsbury']),
    ('CT', 'E.O. Smith High School', ['E.O. Smith', 'EO Smith']),
    ('CT', 'Norwich Free Academy', ['Norwich Free Academy', 'Norwich Free']),
    ('CT', 'Staples High School', ['Staples']),
    ('CT', 'Hillhouse High School', ['Hillhouse']),
    ('CT', 'Sheehan High School', ['Sheehan']),
    ('CT', 'Naugatuck High School', ['Naugatuck']),
    ('CT', 'Amity Regional High School', ['Amity']),
    ('CT', 'Haddam-Killingworth High School', ['Haddam-Killingworth', 'Haddam-Killi']),
    ('CT', 'Joel Barlow High School', ['Joel Barlow']),
    ('CT', 'Tolland High School', ['Tolland']),
    ('CT', 'Greenwich High School', ['Greenwich']),
    ('PEI', 'Colonel Gray High School', ['Colonel Gray']),
    ('PEI', 'Charlottetown Rural High School', ['Charlottetown Rural', 'Charlottetown']),
    ('NS', 'J.H. Gillis Regional High School', ['JH Gillis', 'J.H. Gillis', 'Gillis']),
    ('NS', "King's-Edgehill School", ["King's Edgehill", "King's-Edgehill", 'Kings Edgehill']),
    ('NB', 'Fredericton High School', ['Fredericton High School', 'Fredericton']),
]


def _slug(s):
    import re as _re
    return _re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


OOS = [(f'oos-{st.lower()}-{_slug(name)}', name, None, None, aliases, [], [], {'state': st, 'bare_ok': True})
       for st, name, aliases in _OOS_SIMPLE]

SPECIAL = [
    ('x-unattached', 'Unattached', None, None,
     ['Unattached', 'Unatt', 'Unattach', 'Unattache', 'Unat', 'Unnattached', 'Unat-MAINE', 'Unatt-Maine', 'Unatt Maine', 'unatt-MAINE',
      'Unattached Maine', 'UNA', 'Unattached New E'], [], [], {'level': 'x'}),
    ('x-unknown', 'Unknown / blank', None, None, ['Unknown', 'N/A', 'None'], [], [], {'level': 'x'}),
]


# ---------------------------------------------------------------------------
# Strings that are never a school (column headers, footers, timer banners).
# ---------------------------------------------------------------------------
NOT_SCHOOLS = [
    r'^PACE$',                    # pace column header (MVC/KVAC text results 2004-2018)
    r'^Average:?$',               # team-score footer
    r'Lakers Timing',             # Hy-Tek licence banner "Lakers Timing - Contractor License"
]

# ---------------------------------------------------------------------------
# Per-file meanings of context-dependent strings, from reading the files
# (James's research, Oct 2026). Each rule: (raw strings, season or None,
# (first, last) season-year, regex on the file stem (case-insensitive), id).
# These outrank name matching and athlete evidence.
# ---------------------------------------------------------------------------
FILE_RULES = [
    # shared codes (school_catalog.shared_codes()) placed per meet, 2026-10-19: the meet's conference
    # and its runners' other meets that season settle each one
    (['FA'], 'Outdoor', (2011, 2011), r'^wellsgirls_may3$', 'me-hs-fryeburg'),            # WMC meet; 33/36 runners Fryeburg elsewhere
    (['Spruce'], 'XC', (2021, 2021), r'^cal-?xc-?championships?(boys|girls)$', 'me-ms-spruce-mountain'),   # CAL Junior High Championship; its runners Spruce Mountain MS elsewhere
    (['GREE'], 'XC', (2017, 2018), r'^MS_MEET_10_12_2017$|^MS_MEET_9_20_2018$', 'me-ms-greely'),
    (['M'], 'XC', (2009, 2009), r'^massabesicboys_(sept11|oct9)$', 'me-hs-massabesic'),   # '... @ Massabesic' (the girls' files of these meets: Massabesic)
    (['w'], 'XC', (2010, 2010), r'^messalonskeeboys_sept17$', 'me-hs-waterville'),        # every other W on the sheet is Waterville
    (['Sc'], 'XC', (2011, 2011), r'^massabesicgirls_sept9$', 'me-hs-scarborough'),        # Massabesic-Scarborough dual; 'SC' beside it
    (['N'], 'XC', (2009, 2009), r'^noble(boys|girls)_oct16$', 'me-hs-noble'),           # index: 'Noble, Marshwood, Massabesic, Sanford'
    # 2005 Ellsworth Invitational: the team-score list names Caribou, York, Hampden, Falmouth ('Fox' separately),
    # Lee, and no-score Ellsworth, Winthrop, Orono ('S' left: Sanford or Shead; 'B' left: no B team listed)
    (['C'], 'XC', (2005, 2005), r'^ellsworthinvite\.txt$', 'me-hs-caribou'),
    (['Y'], 'XC', (2005, 2005), r'^ellsworthinvite\.txt$', 'me-hs-york'),
    (['H'], 'XC', (2005, 2005), r'^ellsworthinvite\.txt$', 'me-hs-hampden'),
    (['E'], 'XC', (2005, 2005), r'^ellsworthinvite\.txt$', 'me-hs-ellsworth'),
    (['F'], 'XC', (2005, 2005), r'^ellsworthinvite\.txt$', 'me-hs-falmouth'),
    (['L'], 'XC', (2005, 2005), r'^ellsworthinvite\.txt$', 'me-hs-lee-academy'),
    (['W'], 'XC', (2005, 2005), r'^ellsworthinvite\.txt$', 'me-hs-winthrop'),
    (['O'], 'XC', (2005, 2005), r'^ellsworthinvite\.txt$', 'me-hs-orono'),
    (['FA'], 'XC', (2005, 2005), r'^fryeburg9_16\.txt$', 'me-hs-fryeburg'),           # Fryeburg's home meet
    (['Ma'], 'XC', (2006, 2006), r'^fortfosterboys10_11$', 'me-ms-massabesic'),        # 'Kittery vs. York and Massabesic' middle-school meet
    (['STN'], 'XC', (2006, 2006), r'^wolverineinvite$|^lynxinvitevarsity', 'me-hs-stearns'),   # Michael Rioux: Stearns in central9_5 and the PVC files
    (['STN'], 'XC', (2007, 2007), r'^mattanawcook9_4$', 'me-hs-stearns'),              # Elizabeth Haven: Stearns at Old Town 9/22/07
    (['Rich'], 'XC', (2007, 2007), r'^richmondmiddle(boys|girls)9_15$', 'me-ms-richmond'),   # index: Richmond, Monmouth, Durham, Valley, Litchfield, Raymond - Middle School
    (['Ray'], 'XC', (2007, 2007), r'^richmondmiddle(boys|girls)9_15$', 'me-ms-jordan-small'),   # Raymond's middle school
    (['Val'], 'XC', (2007, 2007), r'^richmondmiddle(boys|girls)9_15$', 'me-ms-upper-kennebec'),  # Valley's middle grades
    (['BC'], 'XC', (2004, 2004), r'^central7sept04girls$', 'me-hs-bangor-christian'),  # Casey McGill: Bangor Christian in pvc04jvg
    (['OH'], 'XC', (2003, 2003), r'^wtvl03[bg]$', 'me-hs-oxford-hills'),              # team list prints Oxford Hills, no Oak Hill
    (['SUN'], 'XC', (2003, 2003), r'^bucksinvite03$', 'me-hs-sumner'),
    (['UM'], 'XC', (2003, 2003), r'^bucksinvite03$', 'me-hs-sumner'),                 # Andrew Brunton: '9 Sumner 19:06.9' elsewhere that fall; a high-school meet            # 2-mile middle-school meet at GNG (Gray-NG, Whittier, Molly Ockett, St. Dom's MS)
    # 2026-10-24 unresolved-school review: codes read from each meet's own team list / its runners' other races
    (['GR'], 'XC', (2007, 2007), r'^lakeregion(boys|girls)9_14$', 'me-hs-greely'),   # Lake Region, Greely, NYA, Traip meet (sub5 index); codes GR/TR/NYA/LR. Boys twin has 11 GR rows unresolved (no
    (['TR'], 'XC', (2007, 2007), r'^lakeregion(boys|girls)9_14$', 'me-hs-traip'),   # Same four-team meet; TR=Traip Academy (3 boys rows).
    (['K'], 'XC', (2005, 2007), r'^cheverus(10_7B|boy10_5)(\.txt)?$', 'me-hs-kennebunk'),   # Kennebunk is the only K team in the meet (score list)
    (['C'], 'XC', (2005, 2007), r'^cheverus(10_7B|boy10_5)(\.txt)?$', 'me-hs-cheverus'),   # meet at Cheverus; only C team
    (['S'], 'XC', (2005, 2007), r'^cheverus(10_7B|boy10_5)(\.txt)?$', 'me-hs-sanford'),   # Sanford is the only S team in the meet
    (['W'], 'XC', (2005, 2007), r'^cheverus(10_7B|boy10_5)(\.txt)?$', 'me-hs-westbrook'),   # Westbrook is the only W team in the meet
    (['Y'], 'XC', (2009, 2009), r'^yorkcountymsboys7th8th$', 'me-ms-york'),   # Finitz, Cannata, Sweeney, Sobotka, Scontras, Bald are York HS 2010-13; York County MS festival
    (['Sf'], 'XC', (2009, 2009), r'^yorkcountymsboys7th8th$', 'me-ms-sanford'),   # Tranchemontagne, Isaac Sweeney are Sanford HS 2010-12
    (['Ki', 'K'], 'XC', (2009, 2009), r'^yorkcountymsboys7th8th$', 'me-ms-shapleigh'),   # Kittery MS; Jacob Wirth (K) is Traip Academy (Kittery) 2010+
    (['Ma'], 'XC', (2009, 2009), r'^yorkcountymsboys7th8th$', 'me-ms-massabesic'),   # York County MS festival (Kennebunk MS); Mattanawcook (Lincoln) is not a York County school. Currently resolves
    (['B'], 'XC', (2005, 2005), r'^bonnyeagle9_16$', 'me-hs-bonny-eagle'),   # Title: Kennebunk, South Portland, Bonny Eagle, Massabesic; boys score Bonny Eagle-19
    (['K'], 'XC', (2005, 2005), r'^bonnyeagle9_16$', 'me-hs-kennebunk'),   # meet teams
    (['S'], 'XC', (2005, 2005), r'^bonnyeagle9_16$', 'me-hs-south-portland'),   # S is South Portland (meet lists South Portland, not Sanford)
    (['M'], 'XC', (2005, 2005), r'^bonnyeagle9_16$', 'me-hs-massabesic'),   # meet teams
    (['M', 'Mar'], 'XC', (2010, 2010), r'^yorkmsxc%20results%202010%20MS%20(boys|girls)%20(junior|senior)$', 'me-ms-marshwood'),   # York County MS festival Fort Foster 2010; same runners in 2011-2012 files and the 2006 York County MS meets.
    (['Y'], 'XC', (2010, 2010), r'^yorkmsxc%20results%202010%20MS%20(boys|girls)%20(junior|senior)$', 'me-ms-york'),   # York County MS festival Fort Foster 2010; same runners in 2011-2012 files and the 2006 York County MS meets.
    (['W'], 'XC', (2010, 2010), r'^yorkmsxc%20results%202010%20MS%20(boys|girls)%20(junior|senior)$', 'me-ms-wells'),   # York County MS festival Fort Foster 2010; same runners in 2011-2012 files and the 2006 York County MS meets.
    (['B'], 'XC', (2010, 2010), r'^yorkmsxc%20results%202010%20MS%20(boys|girls)%20(junior|senior)$', 'me-ms-biddeford'),   # York County MS festival Fort Foster 2010; same runners in 2011-2012 files and the 2006 York County MS meets.
    (['N'], 'XC', (2010, 2010), r'^yorkmsxc%20results%202010%20MS%20(boys|girls)%20(junior|senior)$', 'me-ms-noble'),   # York County MS festival Fort Foster 2010; same runners in 2011-2012 files and the 2006 York County MS meets.
    (['Mas', 'Mass'], 'XC', (2010, 2010), r'^yorkmsxc%20results%202010%20MS%20(boys|girls)%20(junior|senior)$', 'me-ms-massabesic'),   # York County MS festival Fort Foster 2010; same runners in 2011-2012 files and the 2006 York County MS meets.
    (['Shp', 'Shap', 'shp'], 'XC', (2010, 2010), r'^yorkmsxc%20results%202010%20MS%20(boys|girls)%20(junior|senior)$', 'me-ms-shapleigh'),   # York County MS festival Fort Foster 2010; same runners in 2011-2012 files and the 2006 York County MS meets.
    (['San'], 'XC', (2010, 2010), r'^yorkmsxc%20results%202010%20MS%20(boys|girls)%20(junior|senior)$', 'me-ms-sanford'),   # York County MS festival Fort Foster 2010; same runners in 2011-2012 files and the 2006 York County MS meets.
    (['Sac'], 'XC', (2010, 2010), r'^yorkmsxc%20results%202010%20MS%20(boys|girls)%20(junior|senior)$', 'me-ms-saco'),   # York County MS festival Fort Foster 2010; same runners in 2011-2012 files and the 2006 York County MS meets.
    (['K'], 'XC', (2010, 2010), r'^yorkmsxc%20results%202010%20MS%20(boys|girls)%20(junior|senior)$', 'me-ms-kennebunk'),   # York County MS festival Fort Foster 2010; same runners in 2011-2012 files and the 2006 York County MS meets.
    (['TA'], 'XC', (2010, 2010), r'^yorkmsxc%20results%202010%20MS%20(boys|girls)%20(junior|senior)$', 'me-ms-thornton'),   # York County MS festival Fort Foster 2010; same runners in 2011-2012 files and the 2006 York County MS meets.
    (['Ma'], 'XC', (2006, 2006), r'^massabesic9_22boys$', 'me-hs-massabesic'),   # Massabesic, Gorham, McAuley, Thornton at Massabesic
    # 2026-10-24 store-team review (per-meet codes; printed misspellings within the years they occur)
    (['Canton High School'], 'XC', (2016, 2017), r'^(focboysresults16-1\.txt|girlsfocsections16\.txt|focboys2017-1\.txt|focgirlssections2017)$', 'oos-auto-ct-canton'),   # Canton-CT in neboysxc2017 lists the same runners (Sparks) -> oos-auto-ct-canton; FOC files print the
    (['Winterport'], 'XC', (2005, 2005), r'^orrington(boys|girls)\.txt$', 'me-ms-wagner'),   # Middle-school meet at Orrington; Winterport's only middle school is Wagner MS.
    (['Champlain-VT'], 'XC', (2007, 2007), r'^newengland(boys|girls)\.txt$', 'oos-vt-champlain-valley-union-high-school'),   # New England meet 2007; 'Champlain-VT' is the state-tagged short form; CVU is the only Vermont 'Champ
    (['Wal'], 'XC', (2008, 2008), r'^lakeregioninvite$', 'me-hs-maine-coast-waldorf'),   # lakeregioninvite 2008: 'Samuelson - Wal', score table lists 'Waldorf'.
    (['Egxc'], 'XC', (2005, 2005), r'^kvacgv$', 'me-hs-erskine'),   # Same runners are 'Erskine Academy' in emclassbgirls.txt 2005.
    (['BHHS'], 'XC', (2021, 2021), r'^(cboysnorth|classcboys|gsa-boys|pendales-boys-varsity|pvc-varsity-boys|ne-boys-1)\.txt$', 'me-hs-blue-hill-harbor'),   # Troy Morrison appears in the same season as 'Blue Hill Harbor' (Bucksport, Ellsworth meets) -> me-hs
    (['Val'], 'XC', (2006, 2006), r'^monmouth9_20(boys|girls)$', 'me-hs-valley'),   # Header 'Val=N/S'; Wing, T is Valley High School in classcboyswest 2007.
    (['Wisc-Jv', 'WiscJv'], 'XC', (2004, 2004), r'^girls-mvc$', 'me-hs-wiscasset'),   # girls-mvc 2004 team table has Wiscasset and the JV runners listed as Wisc-Jv.
    (['EWG'], 'XC', (2012, 2017), r'^(New%20England%20HS%20XC%20boys%20results\.txt|nexcgirls2017\.txt)$', 'oos-ri-east-greenwich-high-school'),   # nexcgirls2017 prints 'East Greenwich' beside 'EWG'.
    (['MSR MTA'], 'XC', (2019, 2019), r'^q-relay-8-jv$', 'me-hs-mt-ararat'),   # Jeffrey Remis (SR) = Mt Ararat in mtblueboys, LaLiberte-JV 2019; meet also prints Mt.B XC, BRUN.
    (['Mssm/Limestone'], 'XC', (2003, 2026), r'.', 'coop-limestone-mssm'),   # alias: 2009 emclasscgirls: 'Mssm/Limestone'; reversed order of existing alias Limestone/MSSM.
    (['C-Foxcroft Academy'], 'XC', (2003, 2026), r'.', 'me-hs-foxcroft'),   # alias: pvcboysvarsity/pvcgirlsvarsity 2009 print C-Foxcroft Academy beside C-Bangor Christian, C-
    (['CFoxcroft Academy'], 'XC', (2003, 2026), r'.', 'me-hs-foxcroft'),   # alias: store form of the above
    (['Burlintgon HS'], 'XC', (2003, 2026), r'.', 'oos-auto-vt-burlington'),   # alias: newengland boys/girls 2007; Vermont teams (Essex-VT, Harwood-VT, South Burlington).
    (['Hale Dale'], 'XC', (2003, 2026), r'.', 'me-hs-hall-dale'),   # alias: Boothbay-17-21-BOYS 2021 (HS 3-mile) print 'HALE DALE'.
    (['Orrington'], 'XC', (2005, 2005), r'^orrington(boys|girls)\.txt$', 'me-ms-center-drive'),   # 2005 Middle School Championship at Orrington (Holbrook, Glenburn, Bangor Christian...); score line '
    (['N'], 'XC', (2004, 2004), r'^smaajvg04$', 'me-hs-noble'),   # SMAA JV Champ at Cheverus girls: teams K,D,Mc,T scored; N = Ashley Chase, Cindy Beal who are Noble i
    (['N'], 'XC', (2005, 2005), r'^smaasecondsevengirls$', 'me-hs-noble'),   # SMAA 2nd-7 girls: team list Kennebunk, McAuley, TA, Deering, Scarborough, Noble(ns), Cheverus
    (['N'], 'XC', (2006, 2006), r'^(gorhamboys9_27|marshwoodboys10_13|mcauley9_15boys|spboys9_7)$', 'me-hs-noble'),   # headers: 'Gorham..Noble 109', 'Marshwood..Noble n.s.', 'Westbrook 22, Noble 34', 'South Portland 22,
    (['N'], 'XC', (2008, 2008), r'^cheverusgirls_oct3$', 'me-hs-noble'),   # header 'Noble : NS'
    (['N'], 'XC', (2009, 2009), r'^spgirls_sept11$', 'me-hs-noble'),   # sheet title 'SP Wind Noble Girls XC Results 9-11-09'; N = Samantha Pomroy, Amarinda Keys
    (['P'], 'XC', (2003, 2006), r'^(smaarelayteam|cheverus15oct04g|sanford9_8G|southportlandgirls10_13)$', 'me-hs-portland'),   # SMAA meets; header names Portland (ns in 3); 2003 relay P runners Taye/Mulageta are Portland
    (['P'], 'XC', (2006, 2006), r'^freeport9_15(boys|girls)$', 'me-hs-poland'),   # header 'York 25, Freeport 52, Poland 52, Waynflete 101'; P is the only code for Poland
    (['M-W'], 'XC', (2010, 2010), r'^nya(boys|girls)_oct15$', 'me-hs-maine-coast-waldorf'),   # header: Greely, NYA, Waynflete, Merriconeag - Waldorf; score line 'Merriconeag'
    (['Smc'], 'XC', (2005, 2005), r'^eagleclassicboys$', 'me-ms-southern-maine-catholic'),   # same meet's girls file prints Southern Maine Catholic and is mapped
    (['SMC'], 'XC', (2015, 2015), r'^6th-grade-girls-smaa-15\.txt$', 'me-ms-southern-maine-catholic'),   # SMAA 6th grade meet; boys file lists Southern Maine Catholic; F 6 SMC
    (['SMC'], 'XC', (2023, 2023), r'^ms-falmouth-ms-xc-2023$', 'me-ms-southern-maine-catholic'),   # MS meet at Falmouth; SMC is the Southern Maine Catholic team in 2022-24 MS meets
    (['Lim'], 'XC', (2004, 2004), r'^caribou1sept04$', 'coop-limestone-mssm'),   # title lists Limestone/MSSM; score list Caribou, Limestone/MSSM, Fort Kent, Madawaska; Lim is the onl
    (['Win'], 'XC', (2003, 2003), r'^wtvl03g$', 'me-hs-winslow'),   # team list 'Winslow 74'; no Winthrop in the meet
    (['Win'], 'XC', (2006, 2006), r'^monmouth9_20girls$', 'me-hs-winthrop'),   # runners Ouellette/Chu are Winthrop in MVC06girls, maranacookgirls9_1, festival
    (['Msb', 'MSB', 'MSb'], 'XC', (2007, 2007), r'^smaamiddlerelays(boys|girls)$', 'me-ms-massabesic'),   # Z. Sweatt Massabesic Middle School elsewhere; only SMAA MS school missing from the list
    (['MAC', 'MAc', 'Mac'], 'XC', (2016, 2016), r'^Girls-Cross-Country-Sanford-TA-BE-MGA-Sept9$', 'me-hs-mcauley'),   # Sanni Hackett/Chloe Cott/Grace Downey = Maine Girls Academy in ms-be-mca-ta-sanford-2016, city_meet_
    (['Mas'], 'XC', (2005, 2005), r'^yorkMSsg$', 'me-ms-massabesic'),   # York MS meet, grade MS, same file 'Mass'
    (['MAs'], 'XC', (2006, 2006), r'^marshwoodgirls10_13$', 'me-hs-massabesic'),   # header: Massabesic 33, Noble 46, Marshwood 69, Sanford 80 (HS 5K times)
    (['Mas'], 'XC', (2012, 2012), r'^massabesicboys_sept25$', 'me-hs-massabesic'),   # Troy Cloutier is Massabesic HS in 20+ meets
    (['mas'], 'XC', (2023, 2023), r'^ms-smaa-relays-2023$', 'me-hs-massabesic'),   # Aiden Grant is Massabesic HS in south-a-boys, FOC, MS-Noble etc.
    (['Messabesec'], 'XC', (2006, 2006), r'^smacrelaysboys$', 'me-ms-massabesic'),   # MS relays (Shapleigh, Kennebunk, York, Wells, Marshwood, Saco, Massabesic); 'Massabesic' in same fil
    (['SHA'], 'XC', (2011, 2011), r'^york(jrboys|srgirls)$', 'me-ms-shapleigh'),   # same festival 2010 maps Shp/Shap to Shapleigh MS; only York County school unaccounted for
    (['C-Mattanawcook'], 'XC', (2009, 2009), r'^pvcgirlsvarsity\.txt$', 'me-hs-mattanawcook'),   # PVC Championship Class C varsity; Mattanawcook Academy (Lincoln) is the PVC Class C member
    (['OTXC'], 'XC', (2006, 2006), r'^pendale', 'me-hs-old-town'),   # Pendale Invitational field = Bangor, Orono, John Bapst, Hampden, Hermon + OTXC
    (['Castine'], 'XC', (2017, 2017), r'^pvmsxc-small-school-boys\.txt$', 'me-ms-adams-castine'),   # small-school MS championship; the only school in Castine is Adams School at that level
    (['McNamara YORK'], 'XC', (2017, 2017), r'^sep-22-at-York$', 'me-hs-york'),   # source line '5 Griffin McNamara YORK 18:08' and '25 Cavin McNamara YORK'; team-score list YORK/GREEL
    (['OAK'], 'XC', (2010, 2010), r'^maranacook(boys|girls)_sept3$', 'me-hs-oak-hill'),   # Calen/J'Rae Mendall Oak Hill in kvacboys/kvacgirls/focboys/leavittboys_sept18
    (['Libby'], 'XC', (2015, 2015), r'^GorhamXCgirlsMeet10_16_15$', 'me-hs-gorham'),   # source table 'Gor Libby Hannah', 'Gor Libby Grace'
    (['Walker'], 'XC', (2015, 2015), r'^GorhamXCgirlsMeet10_16_15$', 'me-hs-windham'),   # source table 'Wind Walker Natalie'
    (['Beals', 'J - Beals'], 'XC', (2019, 2019), r'^leeboys_sept19\.txt$', 'me-hs-jonesport-beals'),   # printed 'J - Beals'
    (['ISL'], 'XC', (2007, 2007), r'^medomakboys9_21$', 'me-hs-islesboro'),   # score line 'Islesboro NS'
    (['Narraquaqus'], 'XC', (2003, 2026), r'.', 'me-hs-narraguagus'),   # alias: 2019 bucksport-boys-jv misspelling; unambiguous (HS meet, Narrag in lee Sept19 resolves to
    (['Gray-N Glouceste'], 'XC', (2003, 2026), r'.', 'me-hs-gray-ng'),   # alias: 2012 New England HS XC boys: truncated 'Gray-N Glouceste' (Will Shafer, 11) - only Gray-Ne
    (['Wisc'], 'XC', (2023, 2023), r'^(Boys|Girls)-Cross-Country-Meet-9-14-23$', 'me-ms-wiscasset'),   # middle-school league; Kai Morse is Wiscasset MS in busline/gsb/troy-howard 2023
    (['Portsmouth'], 'XC', (2023, 2023), r'^foc2023(boys|girls)overall\.txt$|^Results(boys|girls)byheat$', 'oos-auto-ri-portsmouth'),   # Sean Gray, Allie Kaull are 'Portsmouth RI' at New England 2023
    (['Deer Isle Stonni'], 'XC', (2023, 2023), r'^ellsworth-varsity-boys\.txt$', 'me-hs-deer-isle'),   # truncated column
    (['T'], 'XC', (2023, 2023), r'^thorntongirls8sept2023$', 'me-hs-thornton'),   # 'TA-Falmouth-Noble-Portland'
    (['MCW'], 'XC', (2023, 2023), r'^2023-CAPE-ELIZABETH-BOYS-XC\.txt$', 'me-hs-maine-coast-waldorf'),   # Quinn Chessa: Maine Coast Waldorf in 2023 files
    (['HALE DALE'], 'XC', (2021, 2021), r'^Boothbay-17-21-(BOYS|GIRLS)$', 'me-hs-hall-dale'),   # meet title lists Hall-Dale
    (['Conners Emer'], 'XC', (2022, 2022), r'^airline-invitation-mixed-race\.txt$', 'me-ms-conners-emerson'),   # the meet's girls file: Conners Emerson School
    (['SCC'], 'XC', (2022, 2022), r'^marshwoodboys8sept2022$', 'me-hs-seacoast-christian'),   # Aaron Geaslen; index lists Seacoast Christian
    (['SC'], 'XC', (2022, 2022), r'^SEP-15-RESULTS$', 'me-hs-seacoast-christian'),   # 'SEACOAST ns' in the team block
    (['Green'], 'XC', (2008, 2008), r'^leeinviteboys$', 'me-hs-greenville'),   # Lee Invitational (PVC field); was flapping to an automatic Greenwich CT entry
    # 2026-10-24 second read, batch 4 (2020-2021)
    (['Blue Hill'], 'XC', (2021, 2021), r'^(foc2021boyssections|focboys2021\.txt)$', 'me-hs-blue-hill-harbor'),
    (['MA'], 'XC', (2021, 2021), r'^xc-meet-results-TAMS-10-6-21$', 'me-ms-massabesic'),
    (['MD'], 'XC', (2021, 2021), r'^xc-meet-results-TAMS-10-6-21$', 'me-ms-marshwood'),   # the meet's score boxes: Md = Marshwood MS
    (['Leavitt Wheelchair'], 'XC', (2021, 2021), r'^Maranacook-Boys-9-3-21$', 'me-hs-leavitt'),
    (['Dover'], 'XC', (2020, 2020), r'^Boys-Results-Lee-Academy-Cross-Country-Meet-10_8_20-Sheet1-1$', 'me-hs-foxcroft'),
    (['Dover'], 'XC', (2020, 2020), r'^Girls-Results-Lee-Academy-Cross-Country-Meet-10_8_20-Sheet1-1$', 'me-hs-foxcroft'),
    # 2026-10-24 second read, batch 5 (2019-2020)
    (['Hogdon'], 'XC', (2020, 2020), r'^2020-houlton-xc-boys-results$', 'me-hs-hodgdon'),
    (['Mt, Ararat'], 'XC', (2019, 2019), r'^mtbluegirls$', 'me-hs-mt-ararat'),
    # 2026-10-24 second read, batch 6 (2018-2019)
    (['Wash Ac'], 'XC', (2019, 2019), r'^lee(boys|girls)_sept19\.txt$', 'me-hs-washington-academy'),
    (['Lee Ac'], 'XC', (2019, 2019), r'^lee(boys|girls)_sept19\.txt$', 'me-hs-lee-academy'),
    (['Narrag'], 'XC', (2019, 2019), r'^lee(boys|girls)_sept19\.txt$', 'me-hs-narraguagus'),
    (['J - Beals', 'J- Beals', 'J-Beals', 'Beals'], 'XC', (2019, 2019), r'^lee(boys|girls)_sept19\.txt$', 'me-hs-jonesport-beals'),
    (['WIN'], 'XC', (2019, 2019), r'^tfmm6results1colcourier1(-1)?$', 'me-ms-windham'),
    (['Ma'], 'XC', (2019, 2019), r'^thorntonms(boys|girls)_oct9$', 'me-ms-massabesic'),
    (['WSR Cape', 'MSR Cape'], 'XC', (2018, 2018), r'^Results-R-6$', 'me-hs-cape-elizabeth'),
    (['WFR Mt.B XC', 'MSO Mt.B XC'], 'XC', (2018, 2018), r'^Results-R-6$', 'me-hs-mt-blue'),
    (['WFR Bhs CC 2018', 'MFR Bhs CC 2018'], 'XC', (2018, 2018), r'^Results-R-6$', 'me-hs-brunswick'),
    (['WSR Lewiston XC', 'MJR Lewiston XC'], 'XC', (2018, 2018), r'^Results-R-6$', 'me-hs-lewiston'),
    (['WJR York High School'], 'XC', (2018, 2018), r'^Results-R-6$', 'me-hs-york'),
    (['WJR Morse High School'], 'XC', (2018, 2018), r'^Results-R-6$', 'me-hs-morse'),
    (['WSR Leavitt High School'], 'XC', (2018, 2018), r'^Results-R-6$', 'me-hs-leavitt'),
    (['WSO Mt. Ararat High'], 'XC', (2018, 2018), r'^Results-R-6$', 'me-hs-mt-ararat'),
    (['Woodland Woodchucks'], 'XC', (2018, 2018), r'^(cariboums(boys|girls)_oct3|alms.*)$', 'me-ms-woodland'),
    # 2026-10-24 second read, batch 7 (2018)
    (['Deer Isle'], 'XC', (2018, 2018), r'^(20180924_ParkerPruett_(Boys|Girls)_(results|teams)\.txt|2018ParkerPruett-combined-team-scores)$', 'me-ms-dis-elementary'),
    (['Cranberry Isles'], 'XC', (2018, 2018), r'^(20180924_ParkerPruett_(Boys|Girls)_(results|teams)\.txt|2018ParkerPruett-combined-team-scores)$', 'me-ms-islesford'),
    (['TA'], 'XC', (2018, 2018), r'^tams(boys|girls)_sept27$', 'me-ms-thornton'),
    (['EGHS'], 'XC', (2018, 2018), r'^2018-washburn-xc-boys-results$', 'me-hs-east-grand'),
    (['WIS'], 'XC', (2018, 2018), r'^Boys-9-18-Mad-Results$', 'me-hs-wisdom'),
    (['EastGrand'], 'XC', (2018, 2018), r'^Boys-9-18-Mad-Results$', 'me-hs-east-grand'),
    # 2026-10-24 second read, batch 8 (2017-2018)
    (['Lincoln High School'], 'XC', (2017, 2018), r'^(foc18boysoverall\.txt|focboys2017-1\.txt)$', 'oos-auto-ri-lincoln'),   # Festival of Champions: Lincoln RI (same runners print 'Lincoln - RI' in 2019)
    (['Lincoln'], 'XC', (2017, 2017), r'^focboyssections2017$', 'oos-auto-ri-lincoln'),
    (['Canton'], 'XC', (2017, 2017), r'^(focboyssections2017|focgirlssections2017)$', 'oos-auto-ct-canton'),
    (['Sc'], 'XC', (2017, 2017), r'^xc-meet-results-(boys-varsity|girls)-9-23-17$', 'me-hs-scarborough'),
    # 2026-10-24 second read, batch 9 (2016-2017)
    (['Castine Midd'], 'XC', (2017, 2017), r'^coastal-(boys|girls)\.txt$', 'me-ms-adams-castine'),
    (['F'], 'XC', (2016, 2016), r'^TAMS-10-12-16-(boys|girls)$', 'me-ms-friends-portland'),
    (['TA'], 'XC', (2016, 2016), r'^TAMS-10-12-16-girls$', 'me-ms-thornton'),
    # 2026-10-24 second read, batch 10 (2015-2016)
    (['Boothaby'], 'XC', (2016, 2016), r'^BoysResults$', 'me-hs-boothbay'),
    (['Iselsboro School'], 'XC', (2016, 2016), r'^camden-hills-girls\.txt$', 'me-hs-islesboro'),
    (['CH)'], 'XC', (2015, 2015), r'^2015-Pre-Season-results-$', 'me-hs-camden-hills'),
    (['MV)'], 'XC', (2015, 2015), r'^2015-Pre-Season-results-$', 'me-hs-medomak'),
    # 2026-10-24 unresolved-school review, batch 2
    (['F'], 'XC', (2004, 2004), r'^cape7oct04[bg]\.txt$', 'me-hs-falmouth'),   # Title lists Falmouth; only F team
    (['Y'], 'XC', (2004, 2004), r'^cape7oct04[bg]\.txt$', 'me-hs-yarmouth'),   # Title lists Yarmouth; only Y team
    (['W'], 'XC', (2004, 2004), r'^cape7oct04[bg]\.txt$', 'me-hs-waynflete'),   # Title lists 'Waynefleet NS'; only W team
    (['Co', 'co'], 'XC', (2006, 2006), r'^el(girls|boys)9_1$', 'me-hs-cony'),   # Team list Cony; Cony 'Co' used throughout
    (['Mo'], 'XC', (2006, 2006), r'^el(girls|boys)9_1$', 'me-hs-morse'),   # Team list Morse
    (['G'], 'XC', (2006, 2006), r'^el(girls|boys)9_1$', 'me-hs-gardiner'),   # Team list Gardiner (n.s.); only G team
    (['R'], 'XC', (2008, 2008), r'^lincoln9_26$', 'me-hs-rockland'),   # Teams Medomak Valley, Lincoln Academy, Rockland, Camden Hills; Rockland only R
    (['Y'], 'XC', (2009, 2009), r'^yorkcountymsboys6th$', 'me-ms-york'),   # File legend: York Middle School = Y
    (['Ki'], 'XC', (2009, 2009), r'^yorkcountymsboys6th$', 'me-ms-shapleigh'),   # File legend: Shapleigh School of Kittery = Ki
    (['Ke'], 'XC', (2009, 2009), r'^yorkcountymsboys6th$', 'me-ms-kennebunk'),   # File legend: Middle School of the Kennebunks = Ke
    (['Md'], 'XC', (2009, 2009), r'^yorkcountymsboys6th$', 'me-ms-marshwood'),   # File legend: Marshwood Middle School = Md
    (['Bi'], 'XC', (2009, 2009), r'^yorkcountymsboys6th$', 'me-ms-biddeford'),   # Legend B = Biddeford Middle School; Bi is the only Bi- school in the legend
    (['TA'], 'XC', (2009, 2009), r'^yorkcountymsboys6th$', 'me-ms-thornton'),   # File legend: Thornton Academy Middle School = TA (currently resolves to the high school)
    (['Md'], 'XC', (2007, 2007), r'^sacomiddle(boys|girls)10_3$', 'me-ms-marshwood'),   # Middle-school meet at Saco; Marshwood scored 31; Md = Marshwood in all York County MS files
    (['KI', 'Ki'], 'XC', (2007, 2007), r'^sacomiddle(boys|girls)10_3$', 'me-ms-shapleigh'),   # Sub5 index lists Shapleigh; team score 'Kittery 65'
    (['Ma'], 'XC', (2007, 2007), r'^sacomiddle(boys|girls)10_3$', 'me-ms-massabesic'),   # Massabesic scored 36; Mattanawcook (Lincoln) is not at a Saco MS meet
    (['TA'], 'XC', (2007, 2007), r'^sacomiddle(boys|girls)10_3$', 'me-ms-thornton'),   # Index: 'Thornton Middle School Meet'
    (['L'], 'XC', (2007, 2007), r'^elboys8_31$', 'me-hs-lewiston'),   # Meet score line: Lewiston 36 first; Noor (L) wins; only L team.
    (['B'], 'XC', (2007, 2007), r'^elboys8_31$', 'me-hs-brunswick'),   # Score line Brunswick 69; only B team (girls twin elgirls8_31 already maps B to Brunswick).
    (['Mo'], 'XC', (2007, 2007), r'^elboys8_31$', 'me-hs-morse'),   # Score line Morse 106; only Mo team (Kake, Kibler, Watson).
    (['G'], 'XC', (2007, 2007), r'^elboys8_31$', 'me-hs-gardiner'),   # Score line Gardiner ns (3 runners: Evanku, Hopkins); only G team.
    (['Y'], 'XC', (2009, 2009), r'^yorkcountymsgirls7th8th$', 'me-ms-york'),   # York County MS festival; same ruling as the boys file; Evans, Shaw, Cryan are York.
    (['Sf'], 'XC', (2009, 2009), r'^yorkcountymsgirls7th8th$', 'me-ms-sanford'),   # York County MS festival; same ruling as the boys file (Sf = Sanford MS).
    (['F'], 'XC', (2004, 2004), r'^cape7oct04[bg](\.txt)?$', 'me-hs-falmouth'),   # Title: Falmouth 28, Cape Elizabeth 31, Yarmouth 76, Waynefleet 113; only F team (Forcella, Wilson).
    (['Y'], 'XC', (2004, 2004), r'^cape7oct04[bg](\.txt)?$', 'me-hs-yarmouth'),   # Same four-team meet; only Y team.
    (['W'], 'XC', (2004, 2004), r'^cape7oct04[bg](\.txt)?$', 'me-hs-waynflete'),   # Same meet; "Waynefleet" is the fourth team and the only W.
    (['H-B'], 'XC', (2008, 2008), r'^hydegirls_oct18$', 'me-hs-hyde'),   # Teams: Hyde-Bath, Richmond High School, Hyde-Woodstock; H-B = Hyde-Bath (Maine).
    (['R'], 'XC', (2008, 2008), r'^hydegirls_oct18$', 'me-hs-richmond'),   # Same header: Richmond High School is the only R team.
    (['Maine Cathlol'], 'XC', (2011, 2011), r'^smaainvite(girls|boys)_oct25$', 'me-ms-southern-maine-catholic'),   # "SO Maine Cathlol" = Southern Maine Catholic (name truncated, SO read as grade); SMAA middle-school 
    (['LR'], 'XC', (2018, 2018), r'^MS_MEET_9_20_2018$', 'me-ms-lake-region'),         # same meet
    (['MO'], 'XC', (2015, 2017), r'^MS_MEET_9_10_2015$|^MS_MEET_9_19_2017$', 'me-ms-molly-ockett'),   # GNG middle-school meets; MO is Molly Ockett in the 2018 one
    (['JS'], 'XC', (2017, 2017), r'^MS_MEET_10_12_2017$', 'me-ms-jordan-small'),        # GNG middle-school meet; its runners 'Raymond' (Jordan-Small MS) elsewhere
    (['FA'], 'XC', (2006, 2006), r'^lakeregion10_6$|^yarmouth9_15(girls|boys)$', 'me-hs-fryeburg'),   # WMC (meet title names Fryeburg Academy)
    (['FA'], 'XC', (2011, 2011), r'^fryeburggirls_sept9$', 'me-hs-fryeburg'),          # Fryeburg's home meet
    (['FA'], 'XC', (2013, 2013), r'Presque%20Isle%20invite%209-14-2013', 'me-hs-foxcroft'),   # PVC field; 149 rows Foxcroft elsewhere
    (['FA'], 'XC', (2007, 2007), r'^central9_4$', 'me-hs-foxcroft'),                   # PVC meet at Central; Foxcroft elsewhere
    (['LCS'], None, (2003, 2013), r'^pi17may03$|^pi21may03$|Presque%20Isle%20invite%209-14-2013', 'me-hs-limestone'),  # Aroostook meets; Limestone/MSSM elsewhere
    (['Brhs', 'BRHS'], 'Indoor', (2005, 2008), r'^wmcweek3meet2$|^wmcmeet4$|^kvac2a$', 'me-hs-boothbay'),   # its runners Boothbay elsewhere (45 rows)
    (['Fhs'], 'XC', (2005, 2005), r'^wmcchamps(jv|v)(boys|girls)$', 'me-hs-freeport'),   # Falmouth prints 'Falmouth' in the same files
    (['Mad'], None, (2004, 2006), r'^mvc04g$|^monmouth9_20(girls|boys)$', 'me-hs-madison'),       # MVC meets
    (['Mad'], 'XC', (2006, 2006), r'^presqueisle9_13girls$|^caribouinvitegirlsvarsity$', 'me-hs-madawaska'),  # Aroostook meets
    (['PVHS'], 'Outdoor', (2008, 2008), r'^brewerboys5_2$|^pvcsmallboys$|^boys_orono_5\.9\.08$|^bucksportboys_may13$', 'me-hs-penobscot-valley'),  # 42 rows Penobscot Valley elsewhere
    (['MHS'], 'Indoor', (2008, 2008), r'^smaaResultsB3$|^smaaboysweek4meet2$|^ResultsSMAA3week2$|^smaaweek3meet1boys$', 'me-hs-massabesic'),  # SMAA meets
    (['Chs'], 'XC', (2021, 2021), r'^Laliberte-Junior-Varsity-2021$', 'me-hs-cony'),     # KVAC field; Cony elsewhere
    # single-letter codes at SMAA / York County meets, settled by the host and the runners' other meets
    (['M'], None, (2012, 2013), r'marshwoodboys_sept14|marshwoodboysJV_sept21|kennebunkboys_sept7|marshwoodboys_april30', 'me-hs-marshwood'),
    (['W'], 'Outdoor', (2016, 2016), r'APR-14-RESULTS', 'me-hs-wells'),
    (['WTVL'], 'Indoor', (2007, 2007), r'usmrelays', 'me-hs-waterville'),
    # 2008 Androscoggin Valley middle-school championship: every team is a middle school
    (['MAMS', 'Mams'], 'Outdoor', (2008, 2008), r'Andy-Valley_Track_Championship_2008', 'me-ms-mt-ararat'),
    (['BJH', '8t BJH', '7t BJH', '6t BJH'], 'Outdoor', (2008, 2008), r'Andy-Valley_Track_Championship_2008', 'me-ms-brunswick'),
    # 'LMS'
    (['LMS', 'Lms'], 'Outdoor', (2009, 2018),
     r'mtararatms_may15|andyvalleychamps|andyvallesmschamps|bathmiddle|trippms|Results-boys-3|Results-girls-3|'
     r'Results-BathMSmeet|Results-MAMSmeet|ResultsAVMeet|Results\.htm-LMS|Resultsmay23|ResultsMSmeet5-15|'
     r'AndyValleyScores|Tripp5-(1|10)', 'me-ms-lewiston'),
    (['LMS', 'Lms'], 'Outdoor', (2009, 2017),
     r'orono_middleschool|hampdenmiddleschool|reedsbrook.*april29|Brewer%20MS%205-9-2013|almquist.*15|Reeds-Brook-(boys|girls)',
     'me-ms-leonard'),
    (['LMS', 'Lms'], 'Outdoor', (2019, 2021), r'Scorestriple-c|results_2021_05_13-1', 'me-ms-loranger'),
    (['LMS', 'Lms'], 'Outdoor', (2021, 2021), r'ScoresCALMeet', 'me-ms-lisbon'),
    # 'Warriors'
    (['Warriors', 'WARRIORS'], None, (2003, 2006), r'wmc|classb|falmouth5_9|classc04', 'me-hs-wells'),
    (['Warriors', 'WARRIORS'], 'Outdoor', (2009, 2009), r'foxcroft_may1', 'me-hs-fort-kent'),
    (['Warriors', 'WARRIORS'], 'Outdoor', (2016, 2019), r'.', 'me-ms-rsu19'),
    # 'Tigers'
    (['Tigers', 'TIGERS'], None, (2004, 2016), r'.', 'me-hs-biddeford'),
    (['Tigers', 'TIGERS'], 'Outdoor', (2017, 2017), r'KVAC-B|Gardiner|Results-girls-7|Resultsboys-2', 'me-hs-gardiner'),
    (['Tigers', 'TIGERS'], 'Outdoor', (2017, 2017), r'Results\.AVMS-ship|Resultsmay23', 'me-ms-tripp'),
    # 2018 Lincolnville XC meet (Lincolnville.Meet_.9.20.18.{Boys,Girls}_.pdf): middle-school codes
    (['LCS'], 'XC', (2018, 2018), r'Lincolnville\.Meet', 'me-ms-lincolnville'),
    (['ICS'], 'XC', (2018, 2018), r'Lincolnville\.Meet', 'me-ms-islesboro'),
    (['CRMS'], 'XC', (2018, 2018), r'Lincolnville\.Meet', 'me-ms-camden-rockport'),
    (['THMS'], 'XC', (2018, 2018), r'Lincolnville\.Meet', 'me-ms-troy-howard'),
    (['EDS'], 'XC', (2018, 2018), r'Lincolnville\.Meet', 'me-ms-drinkwater'),
    # 'Lakers'
    (['Lakers', 'LAKERS'], None, (2006, 2010), r'wmc|foley|falmouth|lakeregion', 'me-hs-lake-region'),
    (['Lakers', 'LAKERS', 'Lakers Track'], None, (2004, 2016), r'usatf|reg1|region|\bjo\b|junior', 'club-lakers-tc'),
]

# ---------------------------------------------------------------------------
# Per-file codes (2026-10-19): single letters and short codes ('K', 'Sc', 'MW', 'Lim') printed in dual/tri meets,
# read from each meet itself. Evidence per code, in the comment above its file:
#   score N = ours   the meet's team-score block (parsed team block or the source's score table) prints N for the
#                    named school, and re-scoring that code's finishers from our rows gives the same total
#                    ('~' = within a few points: a missing or extra runner in the parse)
#   named in ...     the school is named in the meet name / team block / source, and the code fits only it
#   surnames a/b     a of the code's b runners' surnames (same gender, same school year) run for that school in
#                    its other meets (these files print surnames only, so full-name continuity can't apply)
# A code with none of these, or two fitting schools, is left out (unresolved). Key: (season, season-year, file stem).
# ---------------------------------------------------------------------------
FILE_CODES = {
    # --- read by hand (2026-10-19); entries marked * replace an earlier wrong reading of the string ---
    # 2003/XC/ftkentb03 "Fort Kent Invitational": the team block lists Washburn 187 and Limestone/MSSM 141 (no Washington
    # Academy, a Downeast school); *Wash had been Washington Academy, 4/7 surnames are Washburn runners
    ('XC', 2003, 'ftkentb03'): {'Lim': 'coop-limestone-mssm', 'Wash': 'me-hs-washburn'},
    # 2005/XC/el9_2b (EL meet): source team scores list Medomak Valley 202, Morse, Brunswick, Gardiner (no Mountain Valley);
    # *MV had been Mountain Valley, 7/7 surnames Medomak; Br 5/7 Brunswick, GA 3/3 Gardiner, Mo 6/7 Morse
    ('XC', 2005, 'el9_2b'): {'Br': 'me-hs-brunswick', 'GA': 'me-hs-gardiner', 'Mo': 'me-hs-morse', 'MV': 'me-hs-medomak'},
    # 2006/XC/greaterportlandmschamps: the file prints its own legend "School Abbreviations: BE = Bonny Eagle M.S., G = Gorham
    # M.S., K = King M.S., L = Lincoln M.S., Ma = Mahoney M.S., Me = Memorial M.S., Mo = Lyman Moore M.S., Sc = Scarborough
    # M.S., SMC = Southern Maine Catholic Schools, We = Wescott J.H.S." (*BE had been Bonny Eagle HS, *Ma Mattanawcook);
    # G 35/44 surnames Gorham MS, Sc 18/20 Scarborough MS. 'Wi' is not in the legend: left unresolved.
    ('XC', 2006, 'greaterportlandmschamps'): {
        'BE': 'me-ms-bonny-eagle', 'G': 'me-ms-gorham', 'K': 'me-ms-king', 'L': 'me-ms-lincoln-portland',
        'Ma': 'me-ms-mahoney', 'Me': 'me-ms-memorial-sp', 'Mo': 'me-ms-lyman-moore', 'Sc': 'me-ms-scarborough',
        'SMC': 'me-ms-southern-maine-catholic', 'We': 'me-ms-westbrook'},
    # 2006/XC/lawrence9_8boys/girls: source team scores list Oxford Hills (no Oak Hill); *OH had been Oak Hill, 6/7 surnames
    # Oxford Hills (boys); B 8/8 and 19/19 Brunswick, G 5/5 Gardiner
    ('XC', 2006, 'lawrence9_8boys'): {'B': 'me-hs-brunswick', 'G': 'me-hs-gardiner', 'OH': 'me-hs-oxford-hills'},
    ('XC', 2006, 'lawrence9_8girls'): {'B': 'me-hs-brunswick', 'OH': 'me-hs-oxford-hills'},
    # 2006/XC/marshwood{boys,girls}10_13 (Marshwood's home meet): source team scores Marshwood 19, Sanford 49, Massabesic 67;
    # *Mar had been Maranacook (a KVAC school), surnames 4/4 Marshwood (girls); S 7/9 Sanford, N 4/5 Noble
    ('XC', 2006, 'marshwoodboys10_13'): {'S': 'me-hs-sanford', 'Mar': 'me-hs-marshwood'},
    ('XC', 2006, 'marshwoodgirls10_13'): {'N': 'me-hs-noble', 'Mar': 'me-hs-marshwood'},
    # 2006/XC/westbrook9_27boys: source team scores Marshwood 41, Westbrook 111; *Md had been Maranacook, 7/9 surnames
    # Marshwood (Md is Marshwood in 2003 marshwood3oct03b too)
    ('XC', 2006, 'westbrook9_27boys'): {'We': 'me-hs-westbrook', 'Md': 'me-hs-marshwood'},
    # 2007/XC/ellsworthjvboys: team block lists ELLSWORTH; *El had been Edward Little (not in the meet), 4/4 surnames Ellsworth
    ('XC', 2007, 'ellsworthjvboys'): {'El': 'me-hs-ellsworth'},
    # 2008/XC/lincoln9_26 (Lincoln Academy meet): CH 5/7 surnames Camden Hills; *MV had been Mountain Valley, 15/16 surnames
    # Medomak Valley (a midcoast KVAC neighbour; Mountain Valley is in Rumford)
    ('XC', 2008, 'lincoln9_26'): {'CH': 'me-hs-camden-hills', 'MV': 'me-hs-medomak'},
    # 2008/XC/thorntonboys9_19: source team scores Cheverus 24, Windham 71; *W had been Westbrook, 9/9 surnames Windham
    ('XC', 2008, 'thorntonboys9_19'): {'W': 'me-hs-windham'},
    # 2008/XC/smmsaajuniorboys (Southern Maine middle-school meet): *Saco had been Sacopee Valley HS, 11/15 surnames Saco MS
    # (entry with the 'Bid' entries below)
    # 2010/XC/stjoes_oct8 "Boy`s Scores- Massabesic- 22; Biddeford- 45; Bonny Eagle- 65": *Ma had been Mattanawcook, 13/18
    # surnames Massabesic; Bi 5/7 Biddeford; Mc 4/4 McAuley
    ('XC', 2010, 'stjoes_oct8'): {'Bi': 'me-hs-biddeford', 'Mc': 'me-hs-mcauley', 'Ma': 'me-hs-massabesic'},
    # 2012/XC/sanford{boys,girls}_oct12: team blocks Massabesic, Marshwood, Sanford, Noble (no Maranacook); *Mar/MAR had been
    # Maranacook, 16/23 and 14/17 surnames Marshwood; Mas/MAS score 17/18 = ours; N 118~119 / 116 = ours; S 59 = ours
    ('XC', 2012, 'sanfordboys_oct12'): {'Mas': 'me-hs-massabesic', 'N': 'me-hs-noble', 'Mar': 'me-hs-marshwood',
                                        'MAr': 'me-hs-marshwood'},
    ('XC', 2012, 'sanfordgirls_oct12'): {'MAS': 'me-hs-massabesic', 'N': 'me-hs-noble', 'S': 'me-hs-sanford',
                                         'MAR': 'me-hs-marshwood'},
    # 2018/XC/LJHS-Girls (junior-high meet): *WAJH had been Waterville HS, 5/6 surnames Waterville Junior High
    ('XC', 2018, 'LJHS-Girls'): {'WAJH': 'me-ms-waterville'},
    # 'Lim' / 'LIM' in Aroostook meets 2004-2011 (Caribou, Fort Kent, Limestone, Presque Isle, Aroostook invitationals): the
    # Hy-Tek truncation of Limestone (the other 'Lim...' schools, Lincoln Academy and Lincolnville, never race in Aroostook);
    # the Limestone/MSSM co-op is applied by team_unit in its active years
    ('XC', 2004, 'cariboub1sept04'): {'Lim': 'me-hs-limestone'},
    ('XC', 2005, 'fortkent9_6B'): {'Lim': 'me-hs-limestone'},
    ('XC', 2005, 'fortkent9_6G'): {'Lim': 'me-hs-limestone'},
    ('XC', 2005, 'limestone8_30B'): {'Lim': 'me-hs-limestone'},
    ('XC', 2005, 'limestone8_30G'): {'Lim': 'me-hs-limestone'},
    ('XC', 2009, 'piinvitevarsity'): {'LIM': 'me-hs-limestone'},
    ('XC', 2011, 'aroostookinviteboys_sept16'): {'LIM': 'me-hs-limestone'},
    ('XC', 2011, 'aroostookinvitegirls'): {'LIM': 'me-hs-limestone'},
    ('Outdoor', 2011, 'aroostookboys'): {'Lim': 'me-hs-limestone'},
    # 2025 small-schools championship (elementary and middle-school girls): 'Deer Isle' is the elementary/middle school;
    # Belle Eaton ran for the high school only in the coastal meet
    ('XC', 2025, 'small-school-girls.txt'): {'Deer Isle': 'me-ms-dis-elementary'},
    # 2015/XC boys1, girls = the Scarborough Middle School Invitational (index): 'North Yarmouth A' is NYA's middle school
    ('XC', 2015, 'boys1'): {'North Yarmouth A': 'me-ms-nya'},
    ('XC', 2015, 'girls'): {'North Yarmouth A': 'me-ms-nya'},
    # 2012/XC/scarboroughinvite{boys,girls} = the Scarborough Middle School invitational: a 2-mile race whose field includes
    # Jordan Small, Cony Middle School, Memorial and North Yarmouth (NYA MS); bare town names are the middle schools (the girls'
    # race already read most of them so; the boys' race had them as high schools)
    ('XC', 2012, 'scarboroughinviteboys'): {
        'Falmouth': 'me-ms-falmouth', 'Cape': 'me-ms-cape-elizabeth', 'Greely': 'me-ms-greely', 'Bonny Eagle': 'me-ms-bonny-eagle',
        'Seacoast': 'me-ms-seacoast-christian', 'Freeport': 'me-ms-freeport', 'Gray New Gloucester': 'me-ms-gray-ng',
        'Lake Region': 'me-ms-lake-region', 'Yarmouth': 'me-ms-harrison', 'Waynflete': 'me-ms-waynflete', 'WIN': 'me-ms-windham'},
    ('XC', 2012, 'scarboroughinvitegirls'): {'Cape': 'me-ms-cape-elizabeth', 'WIN': 'me-ms-windham'},
    # 2019 MileSplit "WMC: FA, NYA, SD, Yarm @ SV": YHS (a shared code: Yarmouth / York) is Yarmouth, the only Y-school named;
    # York is an SMAA school
    ('XC', 2019, 'ms-wmc-fa-nya-sd-yarm-sv-2019'): {'YHS': 'me-hs-yarmouth'},
    # TRIPLE C MS XC @ Falmouth 2012: 'Dur' is Durham Community School (a Triple C school); its first three runners (Johnson G,
    # Decker E, Rogers E) are 'Dur' at Falmouth on 9/24 too (they are listed under 'Bonny Eagle' at the Scarborough MS invite)
    ('XC', 2012, 'ms-triple-c-ms-xc-falmouth-2012'): {'Dur': 'me-ms-durham'},
    # 2009 York County middle-school meets (Sanford): Md 6/10, 8/8, 5/6 surnames Marshwood MS; N 3/6, 7/12 Noble MS;
    # B 4/4 Biddeford MS (Y, Sa, Ke, Sf, Ki: no roster evidence, left unresolved)
    ('XC', 2009, 'yorkcountymsboys7th8th'): {'Md': 'me-ms-marshwood', 'N': 'me-ms-noble', 'B': 'me-ms-biddeford'},
    ('XC', 2009, 'yorkcountymsgirls7th8th'): {'Md': 'me-ms-marshwood', 'N': 'me-ms-noble'},
    ('XC', 2009, 'yorkcountymsgirls6th'): {'Md': 'me-ms-marshwood'},
    # 2007 SMAA middle-school junior boys: Bid 3/4 surnames Biddeford MS
    ('XC', 2007, 'smaamiddlejuniorboys10_24'): {'Bid': 'me-ms-biddeford'},
    # 2010 South Portland girls 9/17 (SMAA): No 3/4 surnames Noble (had been an automatic Vermont 'North' entry)
    ('XC', 2010, 'southportlandgirls_sept17'): {'No': 'me-hs-noble'},
    # 2010 TA middle-school meet: the source's score column reads "MSK 29, BMS 44, TAMS 58" (K's finishers score 29 = ours)
    ('XC', 2010, 'thorntonmiddleboys_sept23'): {'K': 'me-ms-kennebunk', 'B': 'me-ms-biddeford', 'TA': 'me-ms-thornton'},
    # 2011 "Middle School of the Kennebunks, Noble TAMS at York": team block "York Middle School 24, Thornton Academy Middle
    # School 57, Middle School of the Kennebunks 64, Noble Middle School 104"
    ('XC', 2011, 'yorkmsboys_oct5'): {'Y': 'me-ms-york', 'N': 'me-ms-noble'},
    # 2014 Scarborough MS invitational (MileSplit, Middle School list): 'Gray New Glouste' is Gray-New Gloucester misspelled
    ('XC', 2014, 'ms-scarborough-middle-school-invitational-2014'): {'Gray New Glouste': 'me-ms-gray-ng'},
    # 2016 TAMS home meets 9/22: the source's score column prints 'MSK 15', 'WMS 61', 'TAMS 48', 'BMS 108' (each = ours for
    # the same letter); in the 2018 TAMS meets the same letters are, by surnames, Wells MS (W 4/4) and Biddeford MS (B 14/14)
    ('XC', 2016, 'tamsboys_sept22'): {'K': 'me-ms-kennebunk', 'W': 'me-ms-wells', 'B': 'me-ms-biddeford', 'T': 'me-ms-thornton'},
    ('XC', 2016, 'tamsgirls_sept22'): {'K': 'me-ms-kennebunk', 'W': 'me-ms-wells', 'B': 'me-ms-biddeford', 'T': 'me-ms-thornton'},
    # 2007 Mt. Blue girls 9/4 (KVAC): 'Sk' - Skowhegan is the only Maine 'Sk...' school (source names Skowhegan)
    ('XC', 2007, 'mtbluegirls9_4'): {'Sk': 'me-hs-skowhegan'},
    # 2021 MVC middle-school meet "Dir, Carr, Mad, Mt V, SP, Mt Ab, Telst": 'T' is Telstar, the only T-school named
    ('XC', 2021, 'ms-mvc-dir-carr-mad-mt-v-sp-mt-mt-ab-telstar-2021'): {'T': 'me-ms-telstar', 'Mad': 'me-ms-madison'},  # Mad: Madison (an MVC school; Madawaska is in Aroostook)
    # 'Bid' in York County middle-school meets 2005-2011 (York MS, SMAA middle, smmsaa, Biddeford MS's own meets): Biddeford MS
    # (the Hy-Tek truncation; in the 2007 SMAA middle-school races its runners are Biddeford MS by continuity)
    ('XC', 2005, 'yorkMSjg'): {'Bid': 'me-ms-biddeford'},
    ('XC', 2005, 'yorkMSsb'): {'Bid': 'me-ms-biddeford'},
    ('XC', 2005, 'yorkMSsg'): {'Bid': 'me-ms-biddeford'},
    ('XC', 2007, 'smaamiddlejuniorgirls10_24'): {'Bid': 'me-ms-biddeford'},
    ('XC', 2007, 'smaamiddlerelaysgirls'): {'Bid': 'me-ms-biddeford'},
    ('XC', 2008, 'smmsaajuniorboys'): {'Saco': 'me-ms-saco', 'Bid': 'me-ms-biddeford'},
    ('XC', 2011, 'biddefordmsboys_oct12'): {'Bid': 'me-ms-biddeford'},
    ('XC', 2011, 'biddefordmsgirls_oct12'): {'Bid': 'me-ms-biddeford'},
    # Chandler relays 2006 / 2009: 'FRE A' is Freeport's A team (FRE is Freeport in the 2008 Chandler relays and the WMC meets)
    ('XC', 2006, 'chandlerrelays'): {'FRE A': 'me-hs-freeport'},
    ('XC', 2009, 'chandlerrelays'): {'FRE A': 'me-hs-freeport'},
    # 2015 Maine State (college) championship: Maine colleges only; 'U. of New' is UNE (UNH is not in the meet)
    ('XC', 2015, '2015-Maine-State-XC-meet.dab_final-results'): {'U. of New': 'col-une'},
    # 2015 NAC championship (North Atlantic Conference): Green Mountain College is an NAC member
    ('XC', 2015, '2015-NAC-Championship.dab_final-results-Men'): {'Green Mountain': 'col-green-mountain'},
    ('XC', 2015, '2015-NAC-Championship.dab_final-results-Women'): {'Green Mountain': 'col-green-mountain'},
    # 2017 UMD (Dartmouth) invitational: a college meet
    ('XC', 2017, 'UMD-Results-women-varsity'): {'Salisbury': 'col-salisbury'},
    ('XC', 2017, 'UMD-Results-Womens-sub'): {'Salisbury': 'col-salisbury', 'Naval Academ': 'col-navy', 'CC Rhode Isl': 'col-ccri'},
    # --- from the evidence script (meet evidence and surnames agree, or one alone is decisive) ---
    # 2003/XC/cheverusb24sept03: Ch=Cheverus (score 36 = ours; named in source; surnames 7/8); N=Noble (score 120 = ours; named in source; surnames 5/5)
    ('XC', 2003, 'cheverusb24sept03'): {'Ch': 'me-hs-cheverus', 'N': 'me-hs-noble'},
    # 2003/XC/cheverusg24sept03: Ch=Cheverus (surnames 3/3); N=Noble (surnames 3/3); We=Westbrook (score 34 = ours; named in source; surnames 6/7)
    ('XC', 2003, 'cheverusg24sept03'): {'Ch': 'me-hs-cheverus', 'N': 'me-hs-noble', 'We': 'me-hs-westbrook'},
    # 2003/XC/marshwood3oct03b: C=Cheverus (score 52 = ours; named in source; surnames 4/11); Md=Marshwood (score 65 = ours; named in source; surnames 5/7); Wi=Windham (score 71 = ours; named in source; surnames 4/5)
    ('XC', 2003, 'marshwood3oct03b'): {'C': 'me-hs-cheverus', 'Md': 'me-hs-marshwood', 'Wi': 'me-hs-windham'},
    # 2003/XC/smaarelayteam "2003 SMAA Relay Meet": C=Cheverus (score 16 ~ ours ; named in source; surnames 3/4)
    ('XC', 2003, 'smaarelayteam'): {'C': 'me-hs-cheverus'},
    # 2003/XC/sp25sept03: M=Massabesic (score 85 = ours; named in source; surnames 7/7); Sc=Scarborough (score 35 = ours; named in source; surnames 8/9)
    ('XC', 2003, 'sp25sept03'): {'M': 'me-hs-massabesic', 'Sc': 'me-hs-scarborough'},
    # 2003/XC/westbrook10oct03b: D=Deering (score 30 = ours; named in source; surnames 6/9); S=Sanford (score 108 ~ ours 101; named in source; surnames 5/7)
    ('XC', 2003, 'westbrook10oct03b'): {'D': 'me-hs-deering', 'S': 'me-hs-sanford'},
    # 2003/XC/westbrook10oct03g: D=Deering (score 28 = ours; named in source; surnames 7/17); S=Sanford (score 30 = ours; named in source; surnames 10/11); We=Westbrook (score 109 = ours; named in source; surnames 6/6)
    ('XC', 2003, 'westbrook10oct03g'): {'D': 'me-hs-deering', 'S': 'me-hs-sanford', 'We': 'me-hs-westbrook'},
    # 2004/XC/cheverus15oct04b: C=Cheverus (score 78 ~ ours 80; named in source; surnames 8/8); D=Deering (score 38 = ours; named in source; surnames 6/7)
    ('XC', 2004, 'cheverus15oct04b'): {'C': 'me-hs-cheverus', 'D': 'me-hs-deering'},
    # 2004/XC/cheverus15oct04g: D=Deering (score 18 = ours; named in source; surnames 1/15)
    ('XC', 2004, 'cheverus15oct04g'): {'D': 'me-hs-deering'},
    # 2004/XC/fk8sept04b "Madawaska, Limestone/MSSM, Presque Isle at Fort Kent - September 8, 20": Lim=Limestone/MSSM (surnames 2/5)
    ('XC', 2004, 'fk8sept04b'): {'Lim': 'coop-limestone-mssm'},
    # 2004/XC/fk8sept04g "Madawaska, Limestone/MSSM, Presque Isle at Fort Kent - September 8, 20": Lim=Limestone/MSSM (surnames 4/8)
    ('XC', 2004, 'fk8sept04g'): {'Lim': 'coop-limestone-mssm'},
    # 2004/XC/fortfairfieldboys25august04 "Fort Kent, Madawaska, Limestone/MSSM at Fort Fairfield - Boys": Lim=Limestone/MSSM (surnames 2/6)
    ('XC', 2004, 'fortfairfieldboys25august04'): {'Lim': 'coop-limestone-mssm'},
    # 2004/XC/fortfairfieldgirls25august04 "Fort Kent, Madawaska, Limestone/MSSM at Fort Fairfield - Girls": Lim=Limestone/MSSM (surnames 5/7)
    ('XC', 2004, 'fortfairfieldgirls25august04'): {'Lim': 'coop-limestone-mssm'},
    # 2004/XC/hancock04bv "Hancock County Championships held at Searsport High School": SEA=Searsport District (named in meet name; surnames 1/1)
    ('XC', 2004, 'hancock04bv'): {'SEA': 'me-hs-searsport'},
    # 2004/XC/kennebunk15oct04b: B=Biddeford (score 62 ~ ours ; named in source; surnames 4/4)
    ('XC', 2004, 'kennebunk15oct04b'): {'B': 'me-hs-biddeford'},
    # 2004/XC/mcauley17sept04g: M=Catherine McAuley (score 20 = ours; named in source; surnames 11/13); N=Noble (score 66 = ours; named in source; surnames 7/8); P=Portland (score 87 = ours; named in source; surnames 6/7)
    ('XC', 2004, 'mcauley17sept04g'): {'M': 'me-hs-mcauley', 'N': 'me-hs-noble', 'P': 'me-hs-portland'},
    # 2004/XC/sanford8oct04b: D=Deering (score 38 = ours; named in source; surnames 7/9); S=Sanford (score 82 = ours; named in source; surnames 7/7); W=Westbrook (score 42 = ours; named in source; surnames 8/9)
    ('XC', 2004, 'sanford8oct04b'): {'D': 'me-hs-deering', 'S': 'me-hs-sanford', 'W': 'me-hs-westbrook'},
    # 2004/XC/sanford8oct04g: D=Deering (score 19 ~ ours 15; named in source; surnames 12/16); S=Sanford (score 61 ~ ours 56; named in source; surnames 7/8); W=Westbrook (score 93 ~ ours 88; named in source; surnames 6/6)
    ('XC', 2004, 'sanford8oct04g'): {'D': 'me-hs-deering', 'S': 'me-hs-sanford', 'W': 'me-hs-westbrook'},
    # 2004/XC/smaajvb04 "SMAA JV Championship Meet at Cheverus - Boys": K=Kennebunk (score 108 ~ ours 111; named in source+team block; surnames 11/11)
    ('XC', 2004, 'smaajvb04'): {'K': 'me-hs-kennebunk'},
    # 2005/XC/biddeford10_14girls "10/14/05 Kennebunk TA @ Biddeford girls": B=Biddeford (named in meet name; surnames 2/2)
    ('XC', 2005, 'biddeford10_14girls'): {'B': 'me-hs-biddeford'},
    # 2005/XC/eagleclassicgirls "MT. ARARAT MIDDLE SCHOOL - TOPSHAM, ME": Smc=Southern Maine Catholic (combined MS team) (score 92 = ours; named in source+team block)
    ('XC', 2005, 'eagleclassicgirls'): {'Smc': 'me-ms-southern-maine-catholic'},
    # 2005/XC/edwardlittle9_16B "Boys Meet at Edward little 9-16": C=Camden Hills Regional (surnames 4/8); M=Medomak Valley (surnames 4/4; 'm' is Medomak in the girls' race)
    ('XC', 2005, 'edwardlittle9_16B'): {'C': 'me-hs-camden-hills', 'M': 'me-hs-medomak'},
    # 2005/XC/edwardlittle9_16G "Girls Meet at Edward little 3.1 miles 9-16": L=Lewiston (surnames 5/6); c=Camden Hills Regional (surnames 5/10); m=Medomak Valley (surnames 4/5)
    ('XC', 2005, 'edwardlittle9_16G'): {'L': 'me-hs-lewiston', 'c': 'me-hs-camden-hills', 'm': 'me-hs-medomak'},
    # 2005/XC/sanford9_8G "Girlss meet at Sanford, 9/08/05": S=Sanford (named in meet name; surnames 5/5)
    ('XC', 2005, 'sanford9_8G'): {'S': 'me-hs-sanford'},
    # 2005/XC/southportland9_30B "9/30/05 Marshwood, TA, Westbrook at South Portland boys": M=Marshwood (named in meet name; surnames 2/2)
    ('XC', 2005, 'southportland9_30B'): {'M': 'me-hs-marshwood'},
    # 2005/XC/southportland9_30G "9/30/05 Marshwood, TA, Westbrook at South Portland girls": M=Marshwood (named in meet name)
    ('XC', 2005, 'southportland9_30G'): {'M': 'me-hs-marshwood'},
    # 2005/XC/traip10_7 "10/7/05--BOYS": C=Cape Elizabeth (score 22/28 = ours; named in source+team block; surnames 29/37); T=Robert W. Traip Academy (score 90 = ours; named in source+team block; surnames 9/9); W=Wells (score 89 = ours; named in team block; surnames 6/7)
    ('XC', 2005, 'traip10_7'): {'C': 'me-hs-cape-elizabeth', 'T': 'me-hs-traip', 'W': 'me-hs-wells'},
    # 2006/XC/biddeford9_15boys: P=Portland (surnames 6/6)
    ('XC', 2006, 'biddeford9_15boys'): {'P': 'me-hs-portland'},
    # 2006/XC/bonnyeagle9_8boys: P=Portland (score 37 = ours; named in source; surnames 8/9); S=Sanford (score 81 = ours; named in source; surnames 9/10)
    ('XC', 2006, 'bonnyeagle9_8boys'): {'P': 'me-hs-portland', 'S': 'me-hs-sanford'},
    # 2006/XC/capeelizabeth9_8 "September 8, 2006": FRE=Freeport (score 51/84 = ours; named in team block; surnames 18/25)
    ('XC', 2006, 'capeelizabeth9_8'): {'FRE': 'me-hs-freeport'},
    # 2006/XC/cheverus9_8boys: C=Cheverus (surnames 10/10); G=Gorham (surnames 6/6)
    ('XC', 2006, 'cheverus9_8boys'): {'C': 'me-hs-cheverus', 'G': 'me-hs-gorham'},
    # 2006/XC/cheverus9_8girls: C=Cheverus (surnames 10/10); G=Gorham (surnames 10/10)
    ('XC', 2006, 'cheverus9_8girls'): {'C': 'me-hs-cheverus', 'G': 'me-hs-gorham'},
    # 2006/XC/deering9_8girls: B=Biddeford (surnames 4/4); D=Deering (surnames 6/8); M=Massabesic (surnames 5/7); W=Westbrook (surnames 7/8)
    ('XC', 2006, 'deering9_8girls'): {'B': 'me-hs-biddeford', 'D': 'me-hs-deering', 'M': 'me-hs-massabesic', 'W': 'me-hs-westbrook'},
    # 2006/XC/deeringboys10_6: De=Deering (score 54 = ours; named in source; surnames 6/7)
    ('XC', 2006, 'deeringboys10_6'): {'De': 'me-hs-deering'},
    # 2006/XC/deeringgirls10_6: De=Deering (score 73 ~ ours 72; named in source; surnames 10/15); Sc=Scarborough (score 19 = ours; named in source; surnames 10/14); No=Noble (named in source; surnames 4/6; had been an automatic Vermont 'North' entry)
    ('XC', 2006, 'deeringgirls10_6'): {'De': 'me-hs-deering', 'Sc': 'me-hs-scarborough', 'No': 'me-hs-noble'},
    # 2006/XC/elboys9_1: Br=Brunswick (surnames 6/7); Mo=Morse (surnames 6/6)
    ('XC', 2006, 'elboys9_1'): {'Br': 'me-hs-brunswick', 'Mo': 'me-hs-morse'},
    # 2006/XC/elgirls9_1: Br=Brunswick (surnames 11/14)
    ('XC', 2006, 'elgirls9_1'): {'Br': 'me-hs-brunswick'},
    # 2006/XC/freeport9_15boys: F=Freeport (surnames 4/6); Y=York (surnames 13/13)
    ('XC', 2006, 'freeport9_15boys'): {'F': 'me-hs-freeport', 'Y': 'me-hs-york'},
    # 2006/XC/freeport9_15girls: F=Freeport (surnames 6/9); W=Waynflete School (surnames 4/4); Y=York (surnames 10/11)
    ('XC', 2006, 'freeport9_15girls'): {'F': 'me-hs-freeport', 'W': 'me-hs-waynflete', 'Y': 'me-hs-york'},
    # 2006/XC/gng9_15boys: F=Falmouth (surnames 13/13); W=Wells (surnames 5/5); SD=St. Dominic (surnames 4/4; SD is St. Dominic in the girls' race)
    ('XC', 2006, 'gng9_15boys'): {'F': 'me-hs-falmouth', 'W': 'me-hs-wells', 'SD': 'me-hs-st-dominic'},
    # 2006/XC/gng9_15girls: F=Falmouth (surnames 13/15); SD=St. Dominic Academy (surnames 3/5)
    ('XC', 2006, 'gng9_15girls'): {'F': 'me-hs-falmouth', 'SD': 'me-hs-st-dominic'},
    # 2006/XC/gorhamboys9_27: G=Gorham (surnames 10/11); K=Kennebunk (surnames 8/8); P=Portland (surnames 6/6)
    ('XC', 2006, 'gorhamboys9_27'): {'G': 'me-hs-gorham', 'K': 'me-hs-kennebunk', 'P': 'me-hs-portland'},
    # 2006/XC/gorhamgirls9_27: G=Gorham (surnames 3/3); N=Noble (surnames 4/4)
    ('XC', 2006, 'gorhamgirls9_27'): {'G': 'me-hs-gorham', 'N': 'me-hs-noble'},
    # 2006/XC/kennebunk9_15boys: K=Kennebunk (surnames 8/8)
    ('XC', 2006, 'kennebunk9_15boys'): {'K': 'me-hs-kennebunk'},
    # 2006/XC/kennebunk9_15girls: M=Massabesic (surnames 6/6)
    ('XC', 2006, 'kennebunk9_15girls'): {'M': 'me-hs-massabesic'},
    # 2006/XC/lakeregioninvite "August 26th, 2006 at Lake Region": StD=St. Dominic Academy (score 99/138 ~ ours ; named in team block; surnames 1/1); Win=Windham (score 70 = ours; named in team block; surnames 6/9)
    ('XC', 2006, 'lakeregioninvite'): {'StD': 'me-hs-st-dominic', 'Win': 'me-hs-windham'},
    # 2006/XC/massabesic9_22boys: G=Gorham (score 21 = ours; named in source; surnames 9/11)
    ('XC', 2006, 'massabesic9_22boys'): {'G': 'me-hs-gorham'},
    # 2006/XC/mcauley9_15boys: W=Westbrook (surnames 6/7)
    ('XC', 2006, 'mcauley9_15boys'): {'W': 'me-hs-westbrook'},
    # 2006/XC/mcauley9_15girls: M=Catherine McAuley (surnames 10/10); N=Noble (surnames 4/4); W=Westbrook (surnames 6/7)
    ('XC', 2006, 'mcauley9_15girls'): {'M': 'me-hs-mcauley', 'N': 'me-hs-noble', 'W': 'me-hs-westbrook'},
    # 2006/XC/mcauley9_8boys "Scarborough 16, Kennebunk 46": K=Kennebunk (named in meet name; surnames 4/4)
    ('XC', 2006, 'mcauley9_8boys'): {'K': 'me-hs-kennebunk'},
    # 2006/XC/mcauley9_8girls "SCARBOROUGH-30 MCAULEY-46 KENNEBUNK-51 AT MCAULEY": M=Catherine McAuley (named in meet name; surnames 11/13)
    ('XC', 2006, 'mcauley9_8girls'): {'M': 'me-hs-mcauley'},
    # 2006/XC/monmouth9_20boys "Monmouth Boys X-C Meet": Win=Winthrop (surnames 12/14)
    ('XC', 2006, 'monmouth9_20boys'): {'Win': 'me-hs-winthrop'},
    # 2006/XC/sanford9_14boys: D=Deering (surnames 9/11); G=Gorham (surnames 12/14); S=Sanford (surnames 14/16)
    ('XC', 2006, 'sanford9_14boys'): {'D': 'me-hs-deering', 'G': 'me-hs-gorham', 'S': 'me-hs-sanford'},
    # 2006/XC/sanford9_14girls: D=Deering (surnames 10/17); G=Gorham (surnames 8/9); S=Sanford (surnames 10/10)
    ('XC', 2006, 'sanford9_14girls'): {'D': 'me-hs-deering', 'G': 'me-hs-gorham', 'S': 'me-hs-sanford'},
    # 2006/XC/scarboroughmsinviteboys "Last Completed Event": WINH=Windham MS (score 145 = ours; named in source+team block)
    ('XC', 2006, 'scarboroughmsinviteboys'): {'WINH': 'me-ms-windham'},
    # 2006/XC/scarboroughmsinvitegirls "Scarborough Middle School Invitational": WINH=Windham MS (score 50 = ours; named in source+team block)
    ('XC', 2006, 'scarboroughmsinvitegirls'): {'WINH': 'me-ms-windham'},
    # 2006/XC/smaasecond7boys "Scarborough 27, Cheverus 52, Sanford 66, Thornton Academy 98,": C=Cheverus (named in meet name; surnames 5/5); K=Kennebunk (surnames 4/5); Sa=Sanford (named in meet name; surnames 2/4); Sc=Scarborough (named in meet name; surnames 10/10)
    ('XC', 2006, 'smaasecond7boys'): {'C': 'me-hs-cheverus', 'K': 'me-hs-kennebunk', 'Sa': 'me-hs-sanford', 'Sc': 'me-hs-scarborough'},
    # 2006/XC/smaasecond7girls "Kennebunk 24, Scarborough 48, McAuley 66, Thornton Academy 98,": D=Deering (surnames 3/3); M=Catherine McAuley (named in meet name; surnames 3/3); S=Scarborough (named in meet name; surnames 4/4)
    ('XC', 2006, 'smaasecond7girls'): {'D': 'me-hs-deering', 'M': 'me-hs-mcauley', 'S': 'me-hs-scarborough'},
    # 2006/XC/southportlandboys10_13: C=Cheverus (surnames 7/10); D=Deering (surnames 3/4); P=Portland (surnames 4/5)
    ('XC', 2006, 'southportlandboys10_13'): {'C': 'me-hs-cheverus', 'D': 'me-hs-deering', 'P': 'me-hs-portland'},
    # 2006/XC/southportlandgirls10_13: C=Cheverus (surnames 5/6); D=Deering (surnames 5/5); M=Catherine McAuley (surnames 7/9)
    ('XC', 2006, 'southportlandgirls10_13'): {'C': 'me-hs-cheverus', 'D': 'me-hs-deering', 'M': 'me-hs-mcauley'},
    # 2006/XC/spboys9_7: W=Windham (surnames 5/6)
    ('XC', 2006, 'spboys9_7'): {'W': 'me-hs-windham'},
    # 2006/XC/spgirls9_7: N=Noble (surnames 6/9)
    ('XC', 2006, 'spgirls9_7'): {'N': 'me-hs-noble'},
    # 2006/XC/windham9_27boys: B=Biddeford (surnames 3/3); S=Sanford (surnames 9/11)
    ('XC', 2006, 'windham9_27boys'): {'B': 'me-hs-biddeford', 'S': 'me-hs-sanford'},
    # 2006/XC/windham9_27girls: B=Biddeford (surnames 4/4); S=Sanford (surnames 8/8)
    ('XC', 2006, 'windham9_27girls'): {'B': 'me-hs-biddeford', 'S': 'me-hs-sanford'},
    # 2006/XC/yarmouth9_15boys: Y=Yarmouth (surnames 7/8)
    ('XC', 2006, 'yarmouth9_15boys'): {'Y': 'me-hs-yarmouth'},
    # 2006/XC/yarmouth9_15girls: Y=Yarmouth (surnames 8/9)
    ('XC', 2006, 'yarmouth9_15girls'): {'Y': 'me-hs-yarmouth'},
    # 2007/XC/cape10_5 "Boys XC @ Cape Elizabeth (Gull Crest Course)": T=Robert W. Traip Academy (surnames 8/8); W=Wells (score 73 = ours; named in team block; surnames 7/10); Y=York (score 42/48 = ours; named in team block; surnames 54/58)
    ('XC', 2007, 'cape10_5'): {'T': 'me-hs-traip', 'W': 'me-hs-wells', 'Y': 'me-hs-york'},
    # 2007/XC/cape9_7 "Boys XC @ Cape Elizabeth (Gull Crest Course)": FRE=Freeport (score 62/83 = ours; named in team block; surnames 31/34)
    ('XC', 2007, 'cape9_7'): {'FRE': 'me-hs-freeport'},
    # 2007/XC/elgirls8_31: B=Brunswick (surnames 16/19); L=Lewiston (surnames 4/6)
    ('XC', 2007, 'elgirls8_31'): {'B': 'me-hs-brunswick', 'L': 'me-hs-lewiston'},
    # 2007/XC/graygirls9_7 "Richmond, Lake Region, St. Doms @ Gray-New Gloucester Team Scores:": R=Richmond (named in meet name; surnames 1/1)
    ('XC', 2007, 'graygirls9_7'): {'R': 'me-hs-richmond'},
    # 2007/XC/kennebunkgirls10_11: B=Biddeford (surnames 4/4)
    ('XC', 2007, 'kennebunkgirls10_11'): {'B': 'me-hs-biddeford'},
    # 2007/XC/marshwoodboys9_14 "Sunny, low 70's": B=Biddeford (score 97 ~ ours 88; named in source+team block; surnames 6/7); M=Marshwood (score 45 ~ ours 60; named in source+team block; surnames 9/9); P=Portland (score 45 ~ ours 40; named in source+team block; surnames 8/8)
    ('XC', 2007, 'marshwoodboys9_14'): {'B': 'me-hs-biddeford', 'M': 'me-hs-marshwood', 'P': 'me-hs-portland'},
    # 2007/XC/marshwoodgirls9_14 "Sunny, low 70's": B=Biddeford (score 72 = ours; named in source+team block; surnames 4/5); M=Marshwood (score 74 = ours; named in source+team block; surnames 7/8); P=Portland (score 75 = ours; named in source+team block; surnames 3/5); S=Scarborough (score 17 = ours; named in source+team block; surnames 13/18)
    ('XC', 2007, 'marshwoodgirls9_14'): {'B': 'me-hs-biddeford', 'M': 'me-hs-marshwood', 'P': 'me-hs-portland', 'S': 'me-hs-scarborough'},
    # 2007/XC/noblemiddle10_17: B=Biddeford MS (score 52 = ours; named in source)
    ('XC', 2007, 'noblemiddle10_17'): {'B': 'me-ms-biddeford'},
    # 2007/XC/noblemiddlegirls10_17: B=Biddeford MS (score 99 ~ ours 82; named in source)
    ('XC', 2007, 'noblemiddlegirls10_17'): {'B': 'me-ms-biddeford'},
    # 2007/XC/richmondgirls9_15 "Boothbay, Greenville, Hyde, Kents Hill, @ Richmond Team Scores:": HY=Hyde School (named in meet name)
    ('XC', 2007, 'richmondgirls9_15'): {'HY': 'me-hs-hyde'},
    # 2007/XC/richmondmiddleboys9_15 "Monmouth, Durham, Valley, Litchfield, & Raymond @ Richmond Team Scores": Dur=Durham Community School (named in meet name; surnames 1/7)
    ('XC', 2007, 'richmondmiddleboys9_15'): {'Dur': 'me-ms-durham'},
    # 2007/XC/richmondmiddlegirls9_15 "Raymond, Durham, Litchfield, Monmouth, @ Richmond Team Scores:": Dur=Durham Community School (named in meet name; surnames 3/9)
    ('XC', 2007, 'richmondmiddlegirls9_15'): {'Dur': 'me-ms-durham'},
    # 2007/XC/smaajvboys: Ch=Cheverus (score 28 = ours; named in source; surnames 11/12); Go=Gorham (score 113 = ours; named in source; surnames 6/9); K=Kennebunk (score 158 ~ ours 162; named in source; surnames 6/8)
    ('XC', 2007, 'smaajvboys'): {'Ch': 'me-hs-cheverus', 'Go': 'me-hs-gorham', 'K': 'me-hs-kennebunk'},
    # 2007/XC/smaajvgirls: D=Deering (score 132 ~ ours 112; named in source; surnames 2/5); Go=Gorham (score 129 ~ ours ; named in source; surnames 3/4); Mc=Catherine McAuley (surnames 3/4); Sc=Scarborough (score 33 ~ ours 31; named in source; surnames 11/13)
    ('XC', 2007, 'smaajvgirls'): {'D': 'me-hs-deering', 'Go': 'me-hs-gorham', 'Mc': 'me-hs-mcauley', 'Sc': 'me-hs-scarborough'},
    # 2007/XC/thorntonjv9_19 "Boys meet at Marshwood, 10/03/05": M=Marshwood (named in meet name; surnames 2/3)
    ('XC', 2007, 'thorntonjv9_19'): {'M': 'me-hs-marshwood'},
    # 2007/XC/wellsboys9_14 "These are the Boys Cross Country results 9/14/07 @ Wells. Between Well": StD=St. Dominic Academy (surnames 9/11); W=Wells (named in meet name; surnames 6/6)
    ('XC', 2007, 'wellsboys9_14'): {'StD': 'me-hs-st-dominic', 'W': 'me-hs-wells'},
    # 2007/XC/wellsgirls9_14 "These are the girls results 9/14/07 @ Wells. Between Wells, St. Doms, ": StD=St. Dominic Academy (named in meet name; surnames 5/6); W=Wells (named in meet name; surnames 3/3)
    ('XC', 2007, 'wellsgirls9_14'): {'StD': 'me-hs-st-dominic', 'W': 'me-hs-wells'},
    # 2008/XC/biddefordboys9_13 "Deering-Westbrook @ Biddeford.. 3.1 miles Boys results": B=Biddeford (score 63 = ours; named in team block; surnames 7/8); D=Deering (score 55 = ours; named in meet name+team block; surnames 5/5); M=Massabesic (surnames 7/8); W=Westbrook (named in meet name; surnames 4/6)
    ('XC', 2008, 'biddefordboys9_13'): {'B': 'me-hs-biddeford', 'D': 'me-hs-deering', 'M': 'me-hs-massabesic', 'W': 'me-hs-westbrook'},
    # 2008/XC/biddefordboys_oct17 "Biddeford, Kennebunk, & Thornton Academy- Varsity Boys": B=Biddeford (named in meet name; surnames 5/7); K=Kennebunk (named in meet name; surnames 9/10)
    ('XC', 2008, 'biddefordboys_oct17'): {'B': 'me-hs-biddeford', 'K': 'me-hs-kennebunk'},
    # 2008/XC/biddefordgirls9_13 "Massabesic- Deering - Wetbrook @ Biddeford- Girls": B=Biddeford (score 73 = ours; named in meet name+team block; surnames 6/6); D=Deering (score 36 ~ ours 55; named in meet name+source+team block; surnames 9/12); M=Massabesic (score 19 = ours; named in meet name+source+team block; surnames 6/7)
    ('XC', 2008, 'biddefordgirls9_13'): {'B': 'me-hs-biddeford', 'D': 'me-hs-deering', 'M': 'me-hs-massabesic'},
    # 2008/XC/biddefordgirls_oct17 "Biddeford, Kennebunk, & Thornton Academy-": B=Biddeford (named in meet name; surnames 4/4); K=Kennebunk (named in meet name; surnames 11/11)
    ('XC', 2008, 'biddefordgirls_oct17'): {'B': 'me-hs-biddeford', 'K': 'me-hs-kennebunk'},
    # 2008/XC/biddefordjvboys_oct17 "Biddeford, Kennebunk, & Thornton Academy- JV Boys": B=Biddeford (named in meet name; surnames 3/4); K=Kennebunk (named in meet name; surnames 13/14)
    ('XC', 2008, 'biddefordjvboys_oct17'): {'B': 'me-hs-biddeford', 'K': 'me-hs-kennebunk'},
    # 2008/XC/bonnyeagleboys9_12 "Portland, Sanford, & TA at BE, 9/12/08": P=Portland (named in meet name; surnames 7/12); S=Sanford (named in meet name; surnames 10/10)
    ('XC', 2008, 'bonnyeagleboys9_12'): {'P': 'me-hs-portland', 'S': 'me-hs-sanford'},
    # 2008/XC/bonnyeaglegirls9_12 "Portland, Sanford, & TA at BE, 9/12/08": P=Portland (named in meet name; surnames 5/6); S=Sanford (named in meet name; surnames 10/12)
    ('XC', 2008, 'bonnyeaglegirls9_12'): {'P': 'me-hs-portland', 'S': 'me-hs-sanford'},
    # 2008/XC/cheverusgirls_oct3 "Meet of October 3, 2008 at Cheverus": B=Biddeford (surnames 5/6)
    ('XC', 2008, 'cheverusgirls_oct3'): {'B': 'me-hs-biddeford'},
    # 2008/XC/freeportboys_oct17: M=Maine Coast Waldorf School (score 55 ~ ours 152; named in source; surnames 7/7)
    ('XC', 2008, 'freeportboys_oct17'): {'M': 'me-hs-maine-coast-waldorf'},
    # 2008/XC/freeportmsboys_oct16: f=Freeport MS (surnames 6/6); g=Greely MS (score 25 ~ ours 41; named in source; surnames 10/15)
    ('XC', 2008, 'freeportmsboys_oct16'): {'f': 'me-ms-freeport', 'g': 'me-ms-greely', 'c': 'me-ms-cape-elizabeth'},  # c: header "Opponents: Cape, Greely" (Freeport MS score sheet)
    # 2008/XC/freeportmsgirls_oct16: f=Freeport MS (surnames 3/3); g=Greely MS (surnames 6/8)
    ('XC', 2008, 'freeportmsgirls_oct16'): {'f': 'me-ms-freeport', 'g': 'me-ms-greely', 'c': 'me-ms-cape-elizabeth'},  # c: header "Opponents: Cape, Greely" (Freeport MS score sheet)
    # 2008/XC/kennebunkgirls9_12 "Scarboro-31 McAuley-48 Kennebunk–53 2.91miles": K=Kennebunk (named in meet name; surnames 5/5); M=Catherine McAuley (named in meet name; surnames 6/6); S=Scarborough (named in meet name; surnames 9/9)
    ('XC', 2008, 'kennebunkgirls9_12'): {'K': 'me-hs-kennebunk', 'M': 'me-hs-mcauley', 'S': 'me-hs-scarborough'},
    # 2008/XC/lakeregion9_12 "Boys Results Team": Gr=Greely (score 15/19 = ours; named in source; surnames 35/37); SD=St. Dominic Academy (surnames 12/16)
    ('XC', 2008, 'lakeregion9_12'): {'Gr': 'me-hs-greely', 'SD': 'me-hs-st-dominic'},
    # 2008/XC/lakeregioninvite: SD=St. Dominic Academy (surnames 11/16)
    ('XC', 2008, 'lakeregioninvite'): {'SD': 'me-hs-st-dominic'},
    # 2008/XC/marshwood9_24 "South Portland, Thornton, & Westbrook at Marshwood 9/24/08": M=Marshwood (named in meet name; surnames 2/11); W=Westbrook (named in meet name)
    ('XC', 2008, 'marshwood9_24'): {'M': 'me-hs-marshwood', 'W': 'me-hs-westbrook'},
    # 2008/XC/marshwoodboys9_24 "South Portland, Thornton, & Westbrook at Marshwood 9/24/08": M=Marshwood (named in meet name; surnames 10/10); W=Westbrook (named in meet name; surnames 6/6)
    ('XC', 2008, 'marshwoodboys9_24'): {'M': 'me-hs-marshwood', 'W': 'me-hs-westbrook'},
    # 2008/XC/massabesicboys9_19 "Boys Meet-9-19-08 Bonny Eagle-South Portland-Kennebunk at Massabesic": K=Kennebunk (score 87 = ours; named in meet name+team block; surnames 6/7); M=Massabesic (named in meet name; surnames 8/9)
    ('XC', 2008, 'massabesicboys9_19'): {'K': 'me-hs-kennebunk', 'M': 'me-hs-massabesic'},
    # 2008/XC/massabesicboys_oct18 "Sanford-Marshwood-Noble-at Massabesic- Boys- 10/17/08": M=Massabesic (score 17 = ours; named in meet name+team block; surnames 13/15); MW=Marshwood (named in meet name; surnames 6/8); N=Noble (named in meet name; surnames 3/5); S=Sanford (score 66 ~ ours 68; named in meet name+team block; surnames 8/9)
    ('XC', 2008, 'massabesicboys_oct18'): {'M': 'me-hs-massabesic', 'MW': 'me-hs-marshwood', 'N': 'me-hs-noble', 'S': 'me-hs-sanford'},
    # 2008/XC/massabesicgirls9_19 "Girls meet- Kennebunk-Bonny Eadgle-South Portland at Massabesic- 9-19-": K=Kennebunk (score 44 = ours; named in meet name+team block; surnames 13/13); M=Massabesic (score 40 = ours; named in meet name+team block; surnames 3/4)
    ('XC', 2008, 'massabesicgirls9_19'): {'K': 'me-hs-kennebunk', 'M': 'me-hs-massabesic'},
    # 2008/XC/massabesicgirls_oct18 "Marshwood-Noble-Sanford at Massabesic-- 10?17/08 Girls": M=Massabesic (score 21 = ours; named in meet name+team block; surnames 5/7); MW=Marshwood (score 63 = ours; named in meet name+team block; surnames 13/13); N=Noble (score 81 = ours; named in meet name+team block; surnames 6/6); S=Sanford (score 76 = ours; named in meet name+team block; surnames 10/12)
    ('XC', 2008, 'massabesicgirls_oct18'): {'M': 'me-hs-massabesic', 'MW': 'me-hs-marshwood', 'N': 'me-hs-noble', 'S': 'me-hs-sanford'},
    # 2008/XC/mcauleyboys_oct17 "Results: Boys": Ch=Cheverus (surnames 8/8); D=Deering (surnames 8/8); P=Portland (surnames 3/4)
    ('XC', 2008, 'mcauleyboys_oct17'): {'Ch': 'me-hs-cheverus', 'D': 'me-hs-deering', 'P': 'me-hs-portland'},
    # 2008/XC/mcauleygirls_oct17 "Results: Girls": Ch=Cheverus (surnames 6/6); D=Deering (surnames 9/9); Mc=Catherine McAuley (surnames 6/6); P=Portland (surnames 3/4)
    ('XC', 2008, 'mcauleygirls_oct17'): {'Ch': 'me-hs-cheverus', 'D': 'me-hs-deering', 'Mc': 'me-hs-mcauley', 'P': 'me-hs-portland'},
    # 2008/XC/messalonskee9_20: E=Erskine Academy (score 59/73 = ours; named in source+team block; surnames 19/26); G=Gardiner Area (score 57/97 = ours; named in source+team block; surnames 8/13); L=Lewiston (score 20/42 = ours; named in source+team block; surnames 11/21); M=Messalonskee (score 56 = ours; named in source+team block; surnames 14/15); S=Skowhegan Area (score 93 = ours; named in source+team block; surnames 5/10)
    ('XC', 2008, 'messalonskee9_20'): {'E': 'me-hs-erskine', 'G': 'me-hs-gardiner', 'L': 'me-hs-lewiston', 'M': 'me-hs-messalonskee', 'S': 'me-hs-skowhegan'},
    # 2008/XC/sacomiddleboys_oct15: M=Marshwood MS (score 22 = ours; named in source; surnames 13/16); S=Saco MS (score 39 = ours; named in source; surnames 11/17)
    ('XC', 2008, 'sacomiddleboys_oct15'): {'M': 'me-ms-marshwood', 'S': 'me-ms-saco'},
    # 2008/XC/sacomiddlegirls_oct15: M=Marshwood MS (surnames 10/13); S=Saco MS (surnames 9/9)
    ('XC', 2008, 'sacomiddlegirls_oct15'): {'M': 'me-ms-marshwood', 'S': 'me-ms-saco'},
    # 2008/XC/traipgirls9_12 "Place Name School Time Column3": G=Gray-New Gloucester (surnames 5/5)
    ('XC', 2008, 'traipgirls9_12'): {'G': 'me-hs-gray-ng'},
    # 2009/XC/biddefordboys_oct9: G=Gorham (score 24 = ours; named in team block; surnames 12/12)
    ('XC', 2009, 'biddefordboys_oct9'): {'G': 'me-hs-gorham'},
    # 2009/XC/biddefordgirls_oct9: B=Biddeford (score 79 = ours; named in team block; surnames 6/6); G=Gorham (score 22 = ours; named in team block; surnames 8/8)
    ('XC', 2009, 'biddefordgirls_oct9'): {'B': 'me-hs-biddeford', 'G': 'me-hs-gorham'},
    # 2009/XC/bonnyeagleboys_sept16 "Massabesic, Kennebunk, South Portland @ Bonny Eagle—At St. Joseph’s co": K=Kennebunk (score 79 = ours; named in meet name+team block; surnames 13/20)
    ('XC', 2009, 'bonnyeagleboys_sept16'): {'K': 'me-hs-kennebunk'},
    # 2009/XC/bonnyeaglegirls_sept15 "Massabesic, Kennebunk, South Portland @ BE at St. Joseph’s college": K=Kennebunk (score 83 = ours; named in meet name+team block; surnames 7/8)
    ('XC', 2009, 'bonnyeaglegirls_sept15'): {'K': 'me-hs-kennebunk'},
    # 2009/XC/caribounightboys: GHC=Greater Houlton Christian Academy (surnames 4/5)
    ('XC', 2009, 'caribounightboys'): {'GHC': 'me-hs-greater-houlton-christian'},
    # 2009/XC/cheverusboys_oct9 "SMAA XC Boys Meet": K=Kennebunk (surnames 6/6)
    ('XC', 2009, 'cheverusboys_oct9'): {'K': 'me-hs-kennebunk'},
    # 2009/XC/cheverusgirls_oct9 "SMAA XC Girls Meet": C=Cheverus (surnames 10/10); K=Kennebunk (surnames 7/7); S=Sanford (surnames 5/5)
    ('XC', 2009, 'cheverusgirls_oct9'): {'C': 'me-hs-cheverus', 'K': 'me-hs-kennebunk', 'S': 'me-hs-sanford'},
    # 2009/XC/lakeregion_sept18 "High School 9/18/2009": M=Maine Coast Waldorf School (score 43 = ours; named in team block; surnames 9/11)
    ('XC', 2009, 'lakeregion_sept18'): {'M': 'me-hs-maine-coast-waldorf'},
    # 2009/XC/marshwood_oct9 "BOYS VARSITY": MC=Catherine McAuley (score 49 = ours; named in source; surnames 6/6); MW=Marshwood (score 22/40 = ours; named in source; surnames 28/29)
    ('XC', 2009, 'marshwood_oct9'): {'MC': 'me-hs-mcauley', 'MW': 'me-hs-marshwood'},
    # 2009/XC/marshwoodboys_sept17 "VARSITY BOYS": B=Biddeford (score 86 ~ ours 89; named in source; surnames 7/8); M=Marshwood (score 26/49 = ours; named in source; surnames 18/19); P=Portland (score 75 = ours; named in source; surnames 8/9)
    ('XC', 2009, 'marshwoodboys_sept17'): {'B': 'me-hs-biddeford', 'M': 'me-hs-marshwood', 'P': 'me-hs-portland'},
    # 2009/XC/marshwoodgirls_sept17: B=Biddeford (score 89 ~ ours 93; named in source; surnames 6/6); M=Marshwood (score 83 = ours; named in source; surnames 8/8); P=Portland (score 50 = ours; named in source; surnames 6/7); S=Scarborough (score 18 = ours; named in source; surnames 16/17)
    ('XC', 2009, 'marshwoodgirls_sept17'): {'B': 'me-hs-biddeford', 'M': 'me-hs-marshwood', 'P': 'me-hs-portland', 'S': 'me-hs-scarborough'},
    # 2009/XC/massabesicboys_oct9 "Windham, Portland @ Massabesic": P=Portland (named in meet name; surnames 9/9); W=Windham (named in meet name; surnames 17/19)
    ('XC', 2009, 'massabesicboys_oct9'): {'P': 'me-hs-portland', 'W': 'me-hs-windham'},
    # 2009/XC/massabesicboys_sept11 "Deering, Biddeford, Westbrook @Massabesic": B=Biddeford (score 82 ~ ours 89; named in meet name+team block; surnames 9/10); D=Deering (score 65 ~ ours 62; named in meet name+team block; surnames 8/11); W=Westbrook (score 65 ~ ours 62; named in meet name+team block; surnames 9/10)
    ('XC', 2009, 'massabesicboys_sept11'): {'B': 'me-hs-biddeford', 'D': 'me-hs-deering', 'W': 'me-hs-westbrook'},
    # 2009/XC/massabesicgirls_oct9 "Windham, Portland @ Massabesic": P=Portland (named in meet name; surnames 5/6); W=Windham (named in meet name; surnames 12/15)
    ('XC', 2009, 'massabesicgirls_oct9'): {'P': 'me-hs-portland', 'W': 'me-hs-windham'},
    # 2009/XC/massabesicgirls_sept11 "Deering , Biddeford , Westbrook @ Massabesic": B=Biddeford (named in meet name; surnames 8/8); D=Deering (named in meet name; surnames 10/12); W=Westbrook (named in meet name; surnames 1/1)
    ('XC', 2009, 'massabesicgirls_sept11'): {'B': 'me-hs-biddeford', 'D': 'me-hs-deering', 'W': 'me-hs-westbrook'},
    # 2009/XC/nobleboys_oct16: MW=Marshwood (score 49 ~ ours 46; named in source; surnames 15/18); S=Sanford (score 70 ~ ours 66; named in source; surnames 10/10)
    ('XC', 2009, 'nobleboys_oct16'): {'MW': 'me-hs-marshwood', 'S': 'me-hs-sanford'},
    # 2009/XC/noblegirls_oct16: MW=Marshwood (score 69 ~ ours 68; named in source; surnames 10/10); S=Sanford (score 54 = ours; named in source; surnames 10/13)
    ('XC', 2009, 'noblegirls_oct16'): {'MW': 'me-hs-marshwood', 'S': 'me-hs-sanford'},
    # 2009/XC/nyaboys_oct16 "XC Meet Results": M=Maine Coast Waldorf School (surnames 7/9)
    ('XC', 2009, 'nyaboys_oct16'): {'M': 'me-hs-maine-coast-waldorf'},
    # 2009/XC/nyagirls_oct16 "XC Meet Results": F=Freeport (surnames 5/5)
    ('XC', 2009, 'nyagirls_oct16'): {'F': 'me-hs-freeport'},
    # 2009/XC/sacomiddleboys_oct14: M=Marshwood MS (score 45 = ours; named in source); N=Noble MS (score 97 = ours; named in source); S=Saco MS (score 80 = ours; named in source); W=Wells Junior (score 21 = ours; named in source; surnames 16/19)
    ('XC', 2009, 'sacomiddleboys_oct14'): {'M': 'me-ms-marshwood', 'N': 'me-ms-noble', 'S': 'me-ms-saco', 'W': 'me-ms-wells'},
    # 2009/XC/sacomiddlegirls_oct14: M=Marshwood MS (score 31 ~ ours 21; named in source); N=Noble MS (score 78 ~ ours 63; named in source); S=Saco MS (score 65 ~ ours 49; named in source); W=Wells Junior (score 47 ~ ours ; named in source; surnames 3/4)
    ('XC', 2009, 'sacomiddlegirls_oct14'): {'M': 'me-ms-marshwood', 'N': 'me-ms-noble', 'S': 'me-ms-saco', 'W': 'me-ms-wells'},
    # 2009/XC/sanfordboys_sept11 "Sanford, B onny Eagle, Thorn": P=Portland (score 41 = ours; named in team block; surnames 10/11); S=Sanford (score 50 = ours; named in meet name+team block; surnames 11/11)
    ('XC', 2009, 'sanfordboys_sept11'): {'P': 'me-hs-portland', 'S': 'me-hs-sanford'},
    # 2009/XC/sanfordgirls_sept11 "Sanford, Bonny Eagle, Thornt": P=Portland (score 67 = ours; named in team block; surnames 4/5); S=Sanford (score 79 = ours; named in meet name+team block; surnames 12/13)
    ('XC', 2009, 'sanfordgirls_sept11'): {'P': 'me-hs-portland', 'S': 'me-hs-sanford'},
    # 2009/XC/thorntonmiddleboys_sept23: B=Biddeford MS (score 87 = ours; named in source); S=Saco MS (score 89 ~ ours 73; named in source)
    ('XC', 2009, 'thorntonmiddleboys_sept23'): {'B': 'me-ms-biddeford', 'S': 'me-ms-saco', 'K': 'me-ms-kennebunk'},  # K: source score column 'MSK 48' = ours
    # 2009/XC/thorntonmiddlegirls_sept23: B=Biddeford MS (score 98 = ours; named in source); S=Saco MS (score 72 = ours; named in source)
    ('XC', 2009, 'thorntonmiddlegirls_sept23'): {'B': 'me-ms-biddeford', 'S': 'me-ms-saco', 'K': 'me-ms-kennebunk'},  # K: 'MSK 22' = ours
    # 2009/XC/yarmouthboys_sept11 "Freeport 46": MER=Maine Coast Waldorf School (score 73 = ours; named in source; surnames 9/9)
    ('XC', 2009, 'yarmouthboys_sept11'): {'MER': 'me-hs-maine-coast-waldorf'},
    # 2009/XC/yarmouthgirls_sept11 "Freeport 31": FRE=Freeport (score 31 = ours; named in meet name+source; surnames 6/6)
    ('XC', 2009, 'yarmouthgirls_sept11'): {'FRE': 'me-hs-freeport'},
    # 2010/XC/Wellsboys_sept16 "Wells, Gray New Gloucester, Traip @ Wells 09-16-2010 Boys": G=Gray-New Gloucester (named in meet name; surnames 8/8); T=Robert W. Traip Academy (score 73 ~ ours 71; named in meet name+source; surnames 2/5); W=Wells (score 35 = ours; named in meet name+source; surnames 5/5)
    ('XC', 2010, 'Wellsboys_sept16'): {'G': 'me-hs-gray-ng', 'T': 'me-hs-traip', 'W': 'me-hs-wells'},
    # 2010/XC/Wellsgirls_sept16 "Wells, Gray New Gloucester, Traip @ Wells 09-16-2010 Girls": G=Gray-New Gloucester (named in meet name; surnames 6/8); T=Robert W. Traip Academy (named in meet name; surnames 4/4)
    ('XC', 2010, 'Wellsgirls_sept16'): {'G': 'me-hs-gray-ng', 'T': 'me-hs-traip'},
    # 2010/XC/biddefordboys_sept29 "SMAA Cross Country Sanford, Portland and Scarborough @ Biddeford 9/29/": P=Portland (named in meet name; surnames 8/8)
    ('XC', 2010, 'biddefordboys_sept29'): {'P': 'me-hs-portland'},
    # 2010/XC/biddefordgirls_sept29 "SMAA Cross Country Sanford, Portland and Scarborough @ Biddeford 9/29/": B=Biddeford (named in meet name; surnames 4/4); P=Portland (named in meet name; surnames 8/8); S=Sanford (named in meet name; surnames 7/11); Sc=Scarborough (named in meet name; surnames 15/18)
    ('XC', 2010, 'biddefordgirls_sept29'): {'B': 'me-hs-biddeford', 'P': 'me-hs-portland', 'S': 'me-hs-sanford', 'Sc': 'me-hs-scarborough'},
    # 2010/XC/marshwoodgirls_sept8 "GIRLS RESULTS 9/8/10 Marshwood, Scarborough,": M=Marshwood (score 73 = ours; named in meet name+team block; surnames 6/6); S=Scarborough (score 38 = ours; named in meet name+team block; surnames 16/20)
    ('XC', 2010, 'marshwoodgirls_sept8'): {'M': 'me-hs-marshwood', 'S': 'me-hs-scarborough'},
    # 2010/XC/nyagirls_oct15 "Royal River Park": G=Greely (score 78 = ours; named in team block; surnames 10/11); W=Waynflete School (score 44 = ours; named in team block; surnames 5/10)
    ('XC', 2010, 'nyagirls_oct15'): {'G': 'me-hs-greely', 'W': 'me-hs-waynflete'},
    # 2010/XC/sanfordboys_sept11 "Kennebunk, Gorham @ Sanford": S=Sanford (named in meet name; surnames 8/8)
    ('XC', 2010, 'sanfordboys_sept11'): {'S': 'me-hs-sanford'},
    # 2010/XC/sanfordboys_sept17 "Deering, Bonny Eagle @ Sanford": D=Deering (score 28 = ours; named in meet name+team block; surnames 6/8)
    ('XC', 2010, 'sanfordboys_sept17'): {'D': 'me-hs-deering'},
    # 2010/XC/sanfordboysjv_sept11 "Kennebunk, Gorham @ Sanford": S=Sanford (named in meet name; surnames 7/7)
    ('XC', 2010, 'sanfordboysjv_sept11'): {'S': 'me-hs-sanford'},
    # 2010/XC/sanfordgirls_sept11 "Kennebunk, Macauley, Gorham @ Sanford": S=Sanford (named in meet name; surnames 10/12)
    ('XC', 2010, 'sanfordgirls_sept11'): {'S': 'me-hs-sanford'},
    # 2010/XC/sanfordgirls_sept17 "Deering, Bonny Eagle @ Sanford": D=Deering (score 47 = ours; named in meet name+team block; surnames 4/7); S=Sanford (score 55 = ours; named in meet name+team block; surnames 6/7)
    ('XC', 2010, 'sanfordgirls_sept17'): {'D': 'me-hs-deering', 'S': 'me-hs-sanford'},
    # 2011/XC/bonnyeagle_sept16 "Boys 5000 Meters": McA=Catherine McAuley (surnames 7/8)
    ('XC', 2011, 'bonnyeagle_sept16'): {'McA': 'me-hs-mcauley'},
    # 2011/XC/kennebunk_oct7 "COURSE LENGTH approx. 2.92 miles": K=Kennebunk (surnames 8/9); P=Portland (surnames 5/8)
    ('XC', 2011, 'kennebunk_oct7'): {'K': 'me-hs-kennebunk', 'P': 'me-hs-portland'},
    # 2011/XC/massabesicboys_sept21 "Bonny Eagle, Cheveru,Kennebunk @ Massabesic_x000D_Boys Meet": C=Cheverus (score 33 = ours; named in meet name+team block; surnames 15/16); K=Kennebunk (named in meet name; surnames 18/18)
    ('XC', 2011, 'massabesicboys_sept21'): {'C': 'me-hs-cheverus', 'K': 'me-hs-kennebunk'},
    # 2011/XC/massabesicboys_sept9 "South Portland, Scarborough @ Massabesic": M=Massabesic (score 61 = ours; named in meet name+team block; surnames 8/8); SC=Scarborough (score 15 ~ ours 24; named in meet name+team block; surnames 6/8)
    ('XC', 2011, 'massabesicboys_sept9'): {'M': 'me-hs-massabesic', 'SC': 'me-hs-scarborough'},
    # 2011/XC/massabesicgirls_sept21 "Bonny Eagle, Cheverus, Kennebunk @ Massabesic_x000D_Girls meet_x000D_": C=Cheverus (score 28 ~ ours 27; named in meet name+source+team block; surnames 10/13); K=Kennebunk (score 77 ~ ours 75; named in meet name+source+team block; surnames 9/12); M=Massabesic (score 52 ~ ours 48; named in source+team block; surnames 12/13)
    ('XC', 2011, 'massabesicgirls_sept21'): {'C': 'me-hs-cheverus', 'K': 'me-hs-kennebunk', 'M': 'me-hs-massabesic'},
    # 2011/XC/massabesicgirls_sept9 "South Portland, Scarborough @ Massabesic": M=Massabesic (score 20 = ours; named in meet name+team block; surnames 10/12); SC=Scarborough (score 75 = ours; named in meet name+team block; surnames 7/8)
    ('XC', 2011, 'massabesicgirls_sept9'): {'M': 'me-hs-massabesic', 'SC': 'me-hs-scarborough'},
    # 2011/XC/poland_sept2 "Poland Regional High School": P=Poland Regional (score 90/111 = ours; named in meet name+source+team block; surnames 11/11)
    ('XC', 2011, 'poland_sept2'): {'P': 'me-hs-poland'},
    # 2011/XC/poland_sept30 "Poland Regional High School": P=Poland Regional (score 31/60 = ours; named in meet name+source+team block; surnames 14/14); W=Waynflete School (score 17/26 = ours; named in source+team block; surnames 18/18)
    ('XC', 2011, 'poland_sept30'): {'P': 'me-hs-poland', 'W': 'me-hs-waynflete'},
    # 2011/XC/sanfordboys_sept23 "Deering, Scarborough, Biddeford @ Sanford": B=Biddeford (named in meet name; surnames 9/9); D=Deering (score 57 = ours; named in meet name+team block; surnames 14/14); SC=Scarborough (named in meet name; surnames 20/20)
    ('XC', 2011, 'sanfordboys_sept23'): {'B': 'me-hs-biddeford', 'D': 'me-hs-deering', 'SC': 'me-hs-scarborough'},
    # 2011/XC/sanfordgirls_sept23 "Deering, Scarborough, Biddeford @ Sanford": B=Biddeford (named in meet name; surnames 2/3); D=Deering (score 71 ~ ours 63; named in meet name+team block); SA=Sanford (score 35 = ours; named in meet name+team block; surnames 10/12); SC=Scarborough (named in meet name; surnames 6/9)
    ('XC', 2011, 'sanfordgirls_sept23'): {'B': 'me-hs-biddeford', 'D': 'me-hs-deering', 'SA': 'me-hs-sanford', 'SC': 'me-hs-scarborough'},
    # 2011/XC/yorkjrboys "Jr Boys Middle School Cross Country Festival at Fort Foster": Y=York MS (surnames 3/3)
    ('XC', 2011, 'yorkjrboys'): {'Y': 'me-ms-york'},
    # 2011/XC/yorkmsgirls_oct5 "Middle School of the Kennebunks, Noble TAMS at York": Y=York MS (named in meet name; surnames 12/18)
    ('XC', 2011, 'yorkmsgirls_oct5'): {'Y': 'me-ms-york'},
    # 2012/XC/falmouthms_oct10 ", Cape Elizabeth, Friends @ Falmouth": Y=Frank H. Harrison MS (surnames 4/7)
    ('XC', 2012, 'falmouthms_oct10'): {'Y': 'me-ms-harrison'},
    # 2012/XC/falmouthms_sept24 "GNG @Falmouth 2.0 miles sunny, coool, dry": Dur=Durham Community School (surnames 4/8)
    ('XC', 2012, 'falmouthms_sept24'): {'Dur': 'me-ms-durham'},
    # 2012/XC/kennebunkboys_sept19 "Kennebunk - Boys XC Meet": C=Cheverus (score 50 = ours; named in source; surnames 17/17); K=Kennebunk (named in meet name; surnames 14/14); M=Massabesic (score 30 = ours; named in source; surnames 15/15)
    ('XC', 2012, 'kennebunkboys_sept19'): {'C': 'me-hs-cheverus', 'K': 'me-hs-kennebunk', 'M': 'me-hs-massabesic'},
    # 2012/XC/kennebunkgirls_sept19 "Kennebunk - Girls XC Me": C=Cheverus (surnames 7/7); M=Massabesic (surnames 10/10)
    ('XC', 2012, 'kennebunkgirls_sept19'): {'C': 'me-hs-cheverus', 'M': 'me-hs-massabesic'},
    # 2012/XC/kennebunkgirls_sept7 "Girls XC Meet @ Kennebunk": W=Westbrook (surnames 6/8)
    ('XC', 2012, 'kennebunkgirls_sept7'): {'W': 'me-hs-westbrook'},
    # 2012/XC/marshwoodboysJV_sept21 "Race Results - JV Boys 9/21/12 at Marshwood": G=Gorham (surnames 6/8); T=Thornton Academy (surnames 8/11)
    ('XC', 2012, 'marshwoodboysJV_sept21'): {'G': 'me-hs-gorham', 'T': 'me-hs-thornton'},
    # 2012/XC/marshwoodboys_sept14 "Race Results - Boys 9/14/12 at Marshwood": P=Portland (surnames 10/10); S=Scarborough (surnames 16/17)
    ('XC', 2012, 'marshwoodboys_sept14'): {'P': 'me-hs-portland', 'S': 'me-hs-scarborough'},
    # 2012/XC/marshwoodboys_sept21 "Race Results - Boys Varsity 9/21/12 at Marshwood": G=Gorham (surnames 7/7); T=Thornton Academy (surnames 6/6)
    ('XC', 2012, 'marshwoodboys_sept21'): {'G': 'me-hs-gorham', 'T': 'me-hs-thornton'},
    # 2012/XC/marshwoodgirls_sept14 "Race Results - Girls 9/14/12 at Marshwood": M=Marshwood (named in meet name; surnames 11/12); P=Portland (surnames 8/12); S=Scarborough (surnames 4/5)
    ('XC', 2012, 'marshwoodgirls_sept14'): {'M': 'me-hs-marshwood', 'P': 'me-hs-portland', 'S': 'me-hs-scarborough'},
    # 2012/XC/marshwoodgirls_sept21 "At Marshwood": M=Marshwood (named in meet name; surnames 9/10); MC=Catherine McAuley (surnames 5/6); T=Thornton Academy (surnames 11/13)
    ('XC', 2012, 'marshwoodgirls_sept21'): {'M': 'me-hs-marshwood', 'MC': 'me-hs-mcauley', 'T': 'me-hs-thornton'},
    # 2012/XC/nya_oct5 "Place Name Time Team Points": F=Freeport (score 27 = ours; named in team block; surnames 19/29); M=Maine Coast Waldorf School (score 51 = ours; named in team block; surnames 9/12)
    ('XC', 2012, 'nya_oct5'): {'F': 'me-hs-freeport', 'M': 'me-hs-maine-coast-waldorf'},
    # 2012/XC/polandboys_august31 "Poland Regional": F=Freeport (score 24 = ours; named in source+team block; surnames 19/20); P=Poland Regional (score 105 = ours; named in meet name+source+team block; surnames 9/9); W=Waynflete School (score 57 = ours; named in source+team block; surnames 9/10); Y=Yarmouth (score 53 = ours; named in source+team block; surnames 16/16)
    ('XC', 2012, 'polandboys_august31'): {'F': 'me-hs-freeport', 'P': 'me-hs-poland', 'W': 'me-hs-waynflete', 'Y': 'me-hs-yarmouth'},
    # 2012/XC/polandboys_sept28 "Poland Regional": F=Freeport (score 33 = ours; named in source+team block; surnames 18/19); P=Poland Regional (score 113 = ours; named in meet name+source+team block; surnames 7/7)
    ('XC', 2012, 'polandboys_sept28'): {'F': 'me-hs-freeport', 'P': 'me-hs-poland'},
    # 2012/XC/polandgirls_august31 "Poland Regional": F=Freeport (score 57 = ours; named in source+team block; surnames 6/10); P=Poland Regional (score 84 ~ ours 86; named in meet name+source+team block; surnames 6/6); W=Waynflete School (score 73 ~ ours 72; named in source+team block; surnames 6/8)
    ('XC', 2012, 'polandgirls_august31'): {'F': 'me-hs-freeport', 'P': 'me-hs-poland', 'W': 'me-hs-waynflete'},
    # 2012/XC/polandgirls_sept28 "Poland Regiona": F=Freeport (score 34 = ours; named in source+team block; surnames 4/9); P=Poland Regional (score 79 ~ ours 77; named in meet name+source+team block; surnames 7/7)
    ('XC', 2012, 'polandgirls_sept28'): {'F': 'me-hs-freeport', 'P': 'me-hs-poland'},
    # 2012/XC/sanfordboys_sept14 "BONNY EAGLE@SANFORD": B=Bonny Eagle (named in meet name; surnames 12/12)
    ('XC', 2012, 'sanfordboys_sept14'): {'B': 'me-hs-bonny-eagle'},
    # 2012/XC/sanfordgirls_sept14 "MacAuley, Bonny Eagle @ Sanford": B=Bonny Eagle (named in meet name; surnames 13/13); M=Catherine McAuley (surnames 6/7); S=Sanford (score 46 = ours; named in meet name+team block; surnames 15/16)
    ('XC', 2012, 'sanfordgirls_sept14'): {'B': 'me-hs-bonny-eagle', 'M': 'me-hs-mcauley', 'S': 'me-hs-sanford'},
    # 2012/XC/southportlandboys_sept14 "Boys SMAA Cross Country Meet_x000D_2.63 miles @ SP Municipal Golf Cour": G=Gorham (surnames 13/14); K=Kennebunk (surnames 10/11)
    ('XC', 2012, 'southportlandboys_sept14'): {'G': 'me-hs-gorham', 'K': 'me-hs-kennebunk'},
    # 2013/XC/southportland_sept20 "Girls Individual Results": D=Deering (score 93 = ours; named in team block; surnames 19/20)
    ('XC', 2013, 'southportland_sept20'): {'D': 'me-hs-deering'},
    # 2016/XC/Boys-meet-results.102F62F16-@-Marshwood-Sheet1 "Meet Results Deering, Scarborough & Thornton Academy @ Marshwood": D=Deering (named in meet name; surnames 13/14); M=Marshwood (named in meet name; surnames 13/13); S=Scarborough (named in meet name; surnames 24/25); T=Thornton Academy (named in meet name; surnames 9/10)
    ('XC', 2016, 'Boys-meet-results.102F62F16-@-Marshwood-Sheet1'): {'D': 'me-hs-deering', 'M': 'me-hs-marshwood', 'S': 'me-hs-scarborough', 'T': 'me-hs-thornton'},
    # 2016/XC/Girls-meet-results.102F62F16-@-Marshwood-Sheet1 "Meet Results Deering, Scarborough & Thornton Academy @ Marshwood": D=Deering (named in meet name; surnames 8/12); M=Marshwood (named in meet name; surnames 12/12); S=Scarborough (named in meet name; surnames 7/9); T=Thornton Academy (named in meet name; surnames 9/11)
    ('XC', 2016, 'Girls-meet-results.102F62F16-@-Marshwood-Sheet1'): {'D': 'me-hs-deering', 'M': 'me-hs-marshwood', 'S': 'me-hs-scarborough', 'T': 'me-hs-thornton'},
    # 2016/XC/TAMS-10-12-16-boys: M=Marshwood MS (score 15 = ours; named in source)
    ('XC', 2016, 'TAMS-10-12-16-boys'): {'M': 'me-ms-marshwood'},
    # 2016/XC/TAMS-10-12-16-girls: M=Marshwood MS (score 33 ~ ours 28; named in source)
    ('XC', 2016, 'TAMS-10-12-16-girls'): {'M': 'me-ms-marshwood', 'T': 'me-ms-thornton'},  # T: the host, 'TAMS' in the score column
    # 2016/XC/capeboys_sept2 "Meet: WMC Regular Season Meet #1": MC=Maine Coast Waldorf School (score 49 = ours; named in source+team block; surnames 9/12); Y=Yarmouth (score 38 = ours; named in source+team block; surnames 15/25)
    ('XC', 2016, 'capeboys_sept2'): {'MC': 'me-hs-maine-coast-waldorf', 'Y': 'me-hs-yarmouth'},
    # 2016/XC/capegirls_sept2 "Meet: WMC Regular Season Meet #1": MC=Maine Coast Waldorf School (score 80 = ours; named in source+team block; surnames 7/9); Y=Yarmouth (score 25 = ours; named in source+team block; surnames 6/8)
    ('XC', 2016, 'capegirls_sept2'): {'MC': 'me-hs-maine-coast-waldorf', 'Y': 'me-hs-yarmouth'},
    # 2017/XC/MS_MEET_10_12_2017 "BOYS NAME School Place Time Score TEAM TEAM SCORE": MCW=Maine Coast Waldorf School (middle grades) (surnames 24/25); WAY=Waynflete School (middle grades) (surnames 8/9)
    ('XC', 2017, 'MS_MEET_10_12_2017'): {'MCW': 'me-ms-maine-coast-waldorf', 'WAY': 'me-ms-waynflete'},
    # 2017/XC/XC-race-results-Boys-@-Marshwood-Sheet1 "Falmouth, Marshwood, Portland and Sanford @ Marshwood": F=Falmouth (score 24 = ours; named in meet name+team block; surnames 17/19); M=Marshwood (score 60 = ours; named in meet name+team block; surnames 10/11); P=Portland (score 60 = ours; named in meet name+team block; surnames 11/15); S=Sanford (score 97 = ours; named in meet name+team block; surnames 7/7)
    ('XC', 2017, 'XC-race-results-Boys-@-Marshwood-Sheet1'): {'F': 'me-hs-falmouth', 'M': 'me-hs-marshwood', 'P': 'me-hs-portland', 'S': 'me-hs-sanford'},
    # 2017/XC/XC-race-results-Girls-@-Marshwood-Sheet1 "Falmouth, Marshwood, Portland and Sanford @ Marshwood": F=Falmouth (score 24 = ours; named in meet name+team block; surnames 12/14); M=Marshwood (score 33 = ours; named in meet name+team block; surnames 13/13); P=Portland (score 93 = ours; named in meet name+team block; surnames 7/7); S=Sanford (score 101 = ours; named in meet name+team block; surnames 4/5)
    ('XC', 2017, 'XC-race-results-Girls-@-Marshwood-Sheet1'): {'F': 'me-hs-falmouth', 'M': 'me-hs-marshwood', 'P': 'me-hs-portland', 'S': 'me-hs-sanford'},
    # 2018/XC/MS_MEET_9_20_2018 "BOYS NAME School Place Time Score TEAM TEAM SCORE": MO=Molly Ockett MS (surnames 11/11); DOMS=St. Dominic middle grades (a WMC middle-school meet: GNG, WMS Whittier, MO, BATH are all middle schools)
    ('XC', 2018, 'MS_MEET_9_20_2018'): {'MO': 'me-ms-molly-ockett', 'DOMS': 'me-ms-st-dominic'},
    # 2018/XC/XC-race-results-@-Marshwood-Boys-Sheet1 "Biddeford, Gorham, Marshwood & Scarborough @ Marshwood": B=Biddeford (score 74 = ours; named in meet name+team block; surnames 11/12); G=Gorham (score 68 = ours; named in meet name+team block; surnames 13/13); M=Marshwood (score 84 = ours; named in meet name+team block; surnames 15/15); S=Scarborough (score 17 = ours; named in meet name+team block; surnames 23/24)
    ('XC', 2018, 'XC-race-results-@-Marshwood-Boys-Sheet1'): {'B': 'me-hs-biddeford', 'G': 'me-hs-gorham', 'M': 'me-hs-marshwood', 'S': 'me-hs-scarborough'},
    # 2018/XC/XC-race-results-@-Marshwood-Girls-Sheet1 "Biddeford, Gorham, Marshwood & Scarborough @ Marshwood": B=Biddeford (score 96 = ours; named in meet name+team block; surnames 5/6); G=Gorham (score 64 = ours; named in meet name+team block; surnames 11/11); M=Marshwood (score 40 = ours; named in meet name+team block; surnames 19/19); S=Scarborough (score 32 = ours; named in meet name+team block; surnames 13/16)
    ('XC', 2018, 'XC-race-results-@-Marshwood-Girls-Sheet1'): {'B': 'me-hs-biddeford', 'G': 'me-hs-gorham', 'M': 'me-hs-marshwood', 'S': 'me-hs-scarborough'},
    # 2018/XC/bonnyeaglegirls_sept21: D=Deering (score 79 = ours; named in source+team block; surnames 1/5); F=Falmouth (score 17 = ours; named in source+team block; surnames 15/16); W=Westbrook (score 56 = ours; named in source+team block; surnames 8/8)
    ('XC', 2018, 'bonnyeaglegirls_sept21'): {'D': 'me-hs-deering', 'F': 'me-hs-falmouth', 'W': 'me-hs-westbrook'},
    # 2018/XC/tamsboys_sept27: B=Biddeford MS (score 70 = ours; named in source; surnames 12/14); K=Middle School of the Kennebunks (score 20 = ours; named in source; surnames 15/17); W=Wells Junior (score 66 = ours; named in source; surnames 8/10)
    ('XC', 2018, 'tamsboys_sept27'): {'B': 'me-ms-biddeford', 'K': 'me-ms-kennebunk', 'W': 'me-ms-wells'},
    # 2018/XC/tamsgirls_sept27: B=Biddeford MS (score 79 ~ ours 74; named in source; surnames 10/11); K=Middle School of the Kennebunks (score 15 = ours; named in source; surnames 28/29); W=Wells Junior (surnames 4/4)
    ('XC', 2018, 'tamsgirls_sept27'): {'B': 'me-ms-biddeford', 'K': 'me-ms-kennebunk', 'W': 'me-ms-wells'},
    # 2019/XC/BHS-X-Country_HomeMeet_9.27.19-2: B=Biddeford (surnames 15/15); M=Massabesic (surnames 17/22); S=Scarborough (surnames 23/32)
    ('XC', 2019, 'BHS-X-Country_HomeMeet_9.27.19-2'): {'B': 'me-hs-biddeford', 'M': 'me-hs-massabesic', 'S': 'me-hs-scarborough'},
    # 2019/XC/MS_MEET_9_19_2019 "BOYS NAME School Place Time Score TEAM TEAM SCORE": JS=Jordan-Small MS (surnames 17/26)
    ('XC', 2019, 'MS_MEET_9_19_2019'): {'JS': 'me-ms-jordan-small'},
    # 2019/XC/XC-race-results-@-Marshwood-Boys-Sheet1-1 "Gorham, Kennebunk, Marshwood, Noble, Windham @ Marshwood": G=Gorham (score 86 = ours; named in meet name+team block; surnames 10/11); K=Kennebunk (score 15 = ours; named in meet name+team block; surnames 24/27); M=Marshwood (score 46 = ours; named in meet name+team block; surnames 23/23); N=Noble (score 101 = ours; named in meet name+team block; surnames 11/12); W=Windham (score 130 = ours; named in meet name+team block; surnames 9/11)
    ('XC', 2019, 'XC-race-results-@-Marshwood-Boys-Sheet1-1'): {'G': 'me-hs-gorham', 'K': 'me-hs-kennebunk', 'M': 'me-hs-marshwood', 'N': 'me-hs-noble', 'W': 'me-hs-windham'},
    # 2019/XC/XC-race-results-@-Marshwood-Girls-Sheet1-2 "Gorham, Kennebunk, Marshwood, Noble, Windham @ Marshwood": G=Gorham (score 76 = ours; named in meet name+team block; surnames 7/7); K=Kennebunk (score 107 = ours; named in meet name+team block; surnames 17/19); M=Marshwood (score 30 = ours; named in meet name+team block; surnames 16/16); N=Noble (score 110 = ours; named in meet name+team block; surnames 7/7)
    ('XC', 2019, 'XC-race-results-@-Marshwood-Girls-Sheet1-2'): {'G': 'me-hs-gorham', 'K': 'me-hs-kennebunk', 'M': 'me-hs-marshwood', 'N': 'me-hs-noble'},
    # 2019/XC/thorntonmsboys_oct9: B=Biddeford MS (score 86 ~ ours 68; named in source; surnames 13/14); M=Marshwood MS (surnames 12/16)
    ('XC', 2019, 'thorntonmsboys_oct9'): {'B': 'me-ms-biddeford', 'M': 'me-ms-marshwood'},
    # 2019/XC/thorntonmsgirls_oct9: B=Biddeford MS (score 93 = ours; named in source; surnames 7/8); M=Marshwood MS (surnames 21/25)
    ('XC', 2019, 'thorntonmsgirls_oct9'): {'B': 'me-ms-biddeford', 'M': 'me-ms-marshwood'},
    # 2021/XC/MS_MEET_10_5_2021 "BOYS NAME School Place Time Score TEAM TEAM SCORE": JS=Jordan-Small MS (surnames 7/13); DOMS=St. Dominic middle grades (WMC middle-school meet: GNG, JS, GREE are middle schools)
    ('XC', 2021, 'MS_MEET_10_5_2021'): {'JS': 'me-ms-jordan-small', 'DOMS': 'me-ms-st-dominic'},
}

# Out-of-state schools printed 'Town, ST' at the Festival of Champions (2004-05 festival heats, 2022 FOC). The resolver reads
# 'Word, Word' as a name glued into the school cell (debris), so these exact strings are placed here.
FILE_RULES += [
    (['Cumberland, RI'], 'XC', (2004, 2005), r'^festival', 'oos-auto-ri-cumberland'),
    # 2003 prints bare 'Cumberland': its runners (Holgate, McGinnis, Turcotte) are 'Cumberland, RI' in 2004
    (['Cumberland'], 'XC', (2003, 2003), r'^festival(boys|girls)', 'oos-auto-ri-cumberland'),
    (['Canton, CT'], 'XC', (2005, 2005), r'^festival', 'oos-auto-ct-canton'),
    (['Westerly, RI'], 'XC', (2004, 2004), r'^festival', 'oos-ri-westerly-high-school'),
    (['Burrillville, RI'], 'XC', (2022, 2022), r'^foc', 'oos-ri-burrillville-high-school'),
    (['Wheeler, RI'], 'XC', (2022, 2022), r'^foc', 'oos-ri-the-wheeler-school'),
]

FILE_RULES += [([raw], season, (year, year), '^' + _re.escape(stem) + '$', sid)
               for (season, year, stem), codes in FILE_CODES.items() for raw, sid in codes.items()]
