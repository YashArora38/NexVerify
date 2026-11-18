"""Build app/data/linkintel.json and app/data/public_suffixes.txt.

linkintel.json is the single source of truth for the link checks. The Python
backend (app/linkintel.py) and the preview page (preview/linkintel.js) both read it,
so both give the same answer for the same link.

Edit the lists below, then run:  python tools/build_linkdata.py
"""
from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "app" / "data"

# ---------------------------------------------------------------------------
# Restricted Indian zones. Only the named body can register a name here, so the
# zone itself proves who owns the site.
# ---------------------------------------------------------------------------
ZONES = {
    "bank.in": {"kind": "bank", "verified": True,
                "en": "Indian bank address (.bank.in). Only RBI-regulated banks can get one.",
                "hi": "भारतीय बैंक का पता (.bank.in)। यह सिर्फ़ RBI के नियम वाले बैंकों को मिलता है।"},
    "fin.in": {"kind": "nbfc", "verified": True,
               "en": "Indian financial-company address (.fin.in), reserved for RBI-regulated entities.",
               "hi": "भारतीय वित्तीय कंपनी का पता (.fin.in), सिर्फ़ RBI के नियम वाली संस्थाओं के लिए।"},
    "gov.in": {"kind": "government", "verified": True,
               "en": "Government of India address (.gov.in). Only government bodies can get one.",
               "hi": "भारत सरकार का पता (.gov.in)। यह सिर्फ़ सरकारी संस्थाओं को मिलता है।"},
    "nic.in": {"kind": "government", "verified": True,
               "en": "Government of India address (.nic.in), run by the National Informatics Centre.",
               "hi": "भारत सरकार का पता (.nic.in), NIC द्वारा चलाया जाता है।"},
    "mil.in": {"kind": "government", "verified": True,
               "en": "Indian armed forces address (.mil.in).", "hi": "भारतीय सेना का पता (.mil.in)।"},
    "ac.in": {"kind": "education", "verified": False,
              "en": "Indian academic institution address (.ac.in).", "hi": "भारतीय शिक्षण संस्थान का पता (.ac.in)।"},
    "edu.in": {"kind": "education", "verified": False,
               "en": "Indian educational institution address (.edu.in).", "hi": "भारतीय शिक्षण संस्थान का पता (.edu.in)।"},
    "res.in": {"kind": "education", "verified": False,
               "en": "Indian research institution address (.res.in).", "hi": "भारतीय शोध संस्थान का पता (.res.in)।"},
}

# ---------------------------------------------------------------------------
# Brands people impersonate.
#   official : domains the brand owns (registrable domains, or exact hosts)
#   tokens   : words that name the brand when they stand alone in an address
#              ("sbi" in sbi-kyc.com). Short or common words only match whole pieces.
#   fused    : longer, distinctive spellings that name the brand even when glued
#              to other letters ("onlinesbi" in onlinesbiupdate.com)
#   look     : extra spellings to test for lookalikes (official labels are added
#              automatically)
# ---------------------------------------------------------------------------
B = []


CCTLD_BRANDS = {"google", "amazon", "ebay", "yahoo", "microsoft", "apple", "meta", "dhl", "hsbc", "aliexpress", "booking", "airbnb", "citi", "indeed"}


def brand(id, name, kind, official, tokens=(), fused=(), look=(), region="in", weak=()):
    """weak: everyday words that name the brand only next to login / prize / service words
    ("axis-rewardpoints.in"), never on their own ("praxis.com", "axis-tech.com")."""
    B.append({"id": id, "name": name, "kind": kind, "region": region, "intl": id in CCTLD_BRANDS,
              "official": sorted(set(official)), "tokens": list(tokens), "fused": list(fused), "look": list(look), "weak": list(weak)})


# --- Indian banks ------------------------------------------------------------
brand("sbi", "State Bank of India (SBI)", "bank",
      ["sbi.co.in", "sbi.bank.in", "onlinesbi.com", "sbicard.com", "sbilife.co.in",
       "sbimf.com", "sbisecurities.in", "sbigeneral.in", "sbicaps.com", 
       "sbipensionfunds.com", "sbifoundation.in"],
      tokens=["sbi", "yono"], fused=["onlinesbi", "statebankofindia", "statebank", "yonosbi", "sbiyono", "sbionline", "sbinetbanking", "sbibank"],
      look=["onlinesbi", "statebank"])
brand("hdfc", "HDFC Bank", "bank",
      ["hdfcbank.com", "hdfc.bank.in", "hdfcbank.bank.in", "hdfc.com", "hdfclife.com", "hdfcergo.com", "hdfcfund.com", "hdfcsec.com",
       "hdfcsky.com", "hdfccredila.com"],
      tokens=["hdfc"], fused=["hdfcbank", "hdfcnetbanking"], look=["hdfcbank"])
brand("icici", "ICICI Bank", "bank",
      ["icicibank.com", "icici.bank.in", "icicibank.bank.in", "icicidirect.com", "iciciprulife.com", "icicilombard.com",
       "icicipruamc.com", "icicisecurities.com", "icicihfc.com"],
      tokens=["icici"], fused=["icicibank", "icicinet"], look=["icicibank", "icicidirect"])
brand("axis", "Axis Bank", "bank",
      ["axisbank.com", "axis.bank.in", "axisbank.bank.in", "axismf.com", "axisdirect.in", "axismaxlife.com", "axisfinance.in"],
      tokens=[], fused=["axisbank"], look=["axisbank"], weak=["axis"])
brand("kotak", "Kotak Mahindra Bank", "bank",
      ["kotak.com", "kotak.bank.in", "kotakbank.bank.in", "kotaksecurities.com", "kotakmf.com", "kotaklife.com",
       "kotakcherry.com", "kotakneo.com"],
      tokens=["kotak"], fused=["kotakbank", "kotak811", "kotakmahindra"], look=["kotakbank"])
brand("pnb", "Punjab National Bank (PNB)", "bank",
      ["pnbindia.in", "pnb.bank.in", "netpnb.com", "pnbhousing.com", "pnbmetlife.com"],
      tokens=["pnb"], fused=["pnbindia", "punjabnationalbank", "netpnb"], look=["pnbindia"])
brand("bob", "Bank of Baroda", "bank", weak=["bob", "baroda"], official=
      ["bankofbaroda.in", "bankofbaroda.com", "bob.bank.in", "bankofbaroda.bank.in", "bobcard.co.in", "bobfinancial.com", "bobibanking.com"],
      tokens=[], fused=["bankofbaroda", "barodabank", "bobibanking", "bobworld"], look=["bankofbaroda"])
brand("canara", "Canara Bank", "bank", ["canarabank.com", "canara.bank.in", "canarabank.bank.in", "canarahsbclife.com"],
      tokens=["canara"], fused=["canarabank"], look=["canarabank"])
brand("unionbank", "Union Bank of India", "bank", ["unionbankofindia.co.in", "unionbank.bank.in", "unionbankonline.co.in", "unionbankofindia.bank.in"],
      tokens=["unionbank"], fused=["unionbankofindia", "unionbankonline", "unionbank"], look=["unionbankofindia"], weak=["union"])
brand("boi", "Bank of India", "bank", ["bankofindia.co.in", "boi.bank.in", "bankofindia.bank.in"],
      fused=["bankofindia"], look=["bankofindia"])
brand("indianbank", "Indian Bank", "bank", ["indianbank.in", "indianbank.bank.in", "indianbank.net.in"], fused=["indianbank"], look=["indianbank"])
brand("centralbank", "Central Bank of India", "bank", ["centralbankofindia.co.in", "centralbank.bank.in"],
      fused=["centralbankofindia"], look=["centralbankofindia"])
brand("iob", "Indian Overseas Bank", "bank", ["iob.in", "iob.bank.in", "iobnet.co.in"], fused=["indianoverseasbank"], look=[])
brand("uco", "UCO Bank", "bank", ["ucobank.com", "uco.bank.in", "ucobank.bank.in"], fused=["ucobank"], look=["ucobank"])
brand("mahabank", "Bank of Maharashtra", "bank", ["bankofmaharashtra.in", "mahabank.bank.in", "bankofmaharashtra.bank.in"],
      fused=["bankofmaharashtra", "mahabank"], look=["bankofmaharashtra"])
brand("psb", "Punjab & Sind Bank", "bank", ["punjabandsindbank.co.in", "psb.bank.in"], fused=["punjabandsindbank"], look=[])
brand("indusind", "IndusInd Bank", "bank", ["indusind.com", "indusind.bank.in"], tokens=["indusind"], fused=["indusindbank"], look=["indusind"])
brand("yesbank", "Yes Bank", "bank", ["yesbank.in", "yes.bank.in", "yesbank.bank.in"], fused=["yesbank"], look=["yesbank"])
brand("idfc", "IDFC FIRST Bank", "bank", ["idfcfirstbank.com", "idfcfirst.bank.in", "idfcfirstbank.bank.in"],
      tokens=["idfc"], fused=["idfcfirst", "idfcbank"], look=["idfcfirstbank"])
brand("federal", "Federal Bank", "bank", ["federalbank.co.in", "federal.bank.in", "federalbank.bank.in"], fused=["federalbank"], look=["federalbank"])
brand("rbl", "RBL Bank", "bank", ["rblbank.com", "rbl.bank.in", "rblbank.bank.in"], fused=["rblbank"], look=["rblbank"])
brand("idbi", "IDBI Bank", "bank", ["idbibank.in", "idbi.bank.in", "idbibank.bank.in", "idbi.com"], tokens=["idbi"], fused=["idbibank"], look=["idbibank"])
brand("bandhan", "Bandhan Bank", "bank", ["bandhanbank.com", "bandhan.bank.in", "bandhanbank.bank.in"], tokens=["bandhan"], fused=["bandhanbank"], look=["bandhanbank"])
brand("aubank", "AU Small Finance Bank", "bank", ["aubank.in", "au.bank.in", "aubank.bank.in"], fused=["aubank"], look=[])
brand("southindian", "South Indian Bank", "bank", ["southindianbank.com", "southindianbank.bank.in"], fused=["southindianbank"], look=["southindianbank"])
brand("kvb", "Karur Vysya Bank", "bank", ["kvb.co.in", "kvb.bank.in"], fused=["karurvysya"], look=[])
brand("karnataka", "Karnataka Bank", "bank", ["karnatakabank.com", "karnatakabank.bank.in"], fused=["karnatakabank"], look=["karnatakabank"])
brand("ippb", "India Post Payments Bank", "bank", ["ippbonline.com", "ippb.bank.in", "ippbonline.bank.in"], tokens=["ippb"], fused=["ippbonline"], look=["ippbonline"])

# --- Regulators and government bodies (sites outside .gov.in included) -----------
brand("rbi", "Reserve Bank of India (RBI)", "regulator", ["rbi.org.in", "rbi.bank.in", "rbidocs.rbi.org.in", "cms.rbi.org.in", "sachet.rbi.org.in"],
      tokens=["rbi"], fused=["reservebank", "reservebankofindia"], look=[])
brand("sebi", "SEBI", "regulator", ["sebi.gov.in", "scores.sebi.gov.in", "scores.gov.in"], tokens=["sebi"], fused=[], look=[])
brand("npci", "NPCI / UPI", "payment", ["npci.org.in", "bhimupi.org.in", "upichalega.com"], tokens=["npci", "bhim"], fused=["bhimupi"], look=[])
brand("uidai", "UIDAI (Aadhaar)", "government", ["uidai.gov.in", "myaadhaar.uidai.gov.in"], tokens=["uidai", "aadhaar", "aadhar"], fused=["myaadhaar", "aadhaarcard", "aadharcard"], look=[])
brand("incometax", "Income Tax Department", "government", ["incometax.gov.in", "incometaxindia.gov.in", "incometaxindiaefiling.gov.in"],
      tokens=["incometax"], fused=["incometax", "incometaxindia", "itrefund", "taxrefund"], look=["incometaxindia"])
brand("gst", "GST portal", "government", ["gst.gov.in"], tokens=[], fused=["gstportal"], look=[])
brand("epfo", "EPFO", "government", ["epfindia.gov.in", "unifiedportal-mem.epfindia.gov.in"], tokens=["epfo", "epf", "uan"], fused=["epfindia", "epfoindia"], look=["epfindia"])
brand("pmkisan", "PM-Kisan", "government", ["pmkisan.gov.in"], tokens=["pmkisan"], fused=["pmkisan"], look=[])
brand("parivahan", "Parivahan / e-Challan", "government", ["parivahan.gov.in", "echallan.parivahan.gov.in"],
      tokens=["parivahan", "echallan"], fused=["parivahan", "echallan", "mparivahan"], look=["parivahan"])
brand("indiapost", "India Post", "government", ["indiapost.gov.in", "ippbonline.com"], tokens=["indiapost", "speedpost"], fused=["indiapost", "speedpost"], look=["indiapost"])
brand("passport", "Passport Seva", "government", ["passportindia.gov.in"], tokens=["passportseva"], fused=["passportindia", "passportseva"], look=["passportindia"])
brand("digilocker", "DigiLocker", "government", ["digilocker.gov.in"], tokens=["digilocker"], fused=["digilocker"], look=["digilocker"])
brand("cybercrime", "National Cyber Crime Portal", "government", ["cybercrime.gov.in"], tokens=[], fused=["cybercrime"], look=[])
brand("irctc", "IRCTC", "government", ["irctc.co.in", "irctctourism.com", "irctc.com"], tokens=["irctc"], fused=["irctc"], look=["irctc"])
brand("lic", "LIC of India", "insurance", ["licindia.in", "licindia.com", "lichousing.com", "licmf.com"], tokens=["lic"], fused=["licindia"], look=["licindia"])
brand("nsdl", "NSDL / Protean (PAN)", "government", ["nsdl.co.in", "nsdl.com", "protean-tinpan.com", "proteantech.in", "utiitsl.com"],
      tokens=["nsdl", "utiitsl"], fused=["nsdl", "panupdate", "pancardupdate"], look=[])
brand("electricity", "Electricity boards", "utility",
      ["bescom.co.in", "bescom.karnataka.gov.in", "mahadiscom.in", "adanielectricity.com", "torrentpower.com", "bsesdelhi.com", "tpddl.com", "cesc.co.in", "tnebltd.gov.in", "kseb.in", "uppcl.org", "pspcl.in"],
      tokens=["bescom", "mahadiscom", "tneb", "kseb", "uppcl", "bses"], fused=["electricitybill", "mahadiscom", "bescom"], look=[])
brand("nse", "NSE", "exchange", ["nseindia.com", "nse.co.in"], tokens=[], fused=["nseindia"], look=["nseindia"])
brand("bse", "BSE", "exchange", ["bseindia.com", "bsebti.com"], tokens=[], fused=["bseindia"], look=["bseindia"])

# --- Payments, fintech, brokers, NBFCs ------------------------------------------
brand("paytm", "Paytm", "payment", ["paytm.com", "paytmbank.com", "paytmmoney.com", "paytmmall.com", "paytm.me"],
      tokens=["paytm"], fused=["paytm"], look=["paytm"])
brand("phonepe", "PhonePe", "payment", ["phonepe.com", "phon.pe", "share.market"], tokens=["phonepe"], fused=["phonepe"], look=["phonepe"])
brand("googlepay", "Google Pay", "payment", ["pay.google.com"], tokens=["gpay"], fused=["googlepay"], look=["googlepay"])
brand("amazonpay", "Amazon Pay", "payment", ["amazonpay.in", "amazonpay.com"], tokens=[], fused=["amazonpay"], look=["amazonpay"])
brand("mobikwik", "MobiKwik", "payment", ["mobikwik.com"], tokens=["mobikwik"], fused=["mobikwik"], look=["mobikwik"])
brand("freecharge", "Freecharge", "payment", ["freecharge.in", "freecharge.com"], tokens=["freecharge"], fused=["freecharge"], look=["freecharge"])
brand("cred", "CRED", "payment", ["cred.club"], tokens=[], fused=["credclub"], look=[])
brand("razorpay", "Razorpay", "payment", ["razorpay.com", "razorpay.me", "razorpay.in", "rzp.io"], tokens=["razorpay"], fused=["razorpay"], look=["razorpay"])
brand("bharatpe", "BharatPe", "payment", ["bharatpe.com", "bharatpe.in"], tokens=["bharatpe"], fused=["bharatpe"], look=["bharatpe"])
brand("zerodha", "Zerodha", "broker", ["zerodha.com", "kite.trade"], tokens=["zerodha"], fused=["zerodha"], look=["zerodha"])
brand("groww", "Groww", "broker", ["groww.in"], tokens=["groww"], fused=["groww"], look=[])
brand("upstox", "Upstox", "broker", ["upstox.com", "rksv.in"], tokens=["upstox"], fused=["upstox"], look=["upstox"])
brand("angelone", "Angel One", "broker", ["angelone.in", "angelbroking.com"], tokens=["angelone"], fused=["angelone", "angelbroking"], look=["angelone", "angelbroking"])
brand("smallcase", "smallcase", "broker", ["smallcase.com"], tokens=["smallcase"], fused=["smallcase"], look=["smallcase"])
brand("bajaj", "Bajaj Finance / Bajaj Finserv", "nbfc", ["bajajfinserv.in", "bajajfinance.in", "bajaj.fin.in", "bajajallianz.com", "bajajfinservmarkets.in", "bajajauto.com", "bajajallianzlife.com", "bajajhousingfinance.in"],
      tokens=[], fused=["bajajfinserv", "bajajfinance"], look=["bajajfinserv"])
brand("moneyview", "Moneyview", "nbfc", ["moneyview.in"], tokens=["moneyview"], fused=["moneyview"], look=["moneyview"])
brand("kreditbee", "KreditBee", "nbfc", ["kreditbee.in"], tokens=["kreditbee"], fused=["kreditbee"], look=["kreditbee"])
brand("navi", "Navi", "nbfc", ["navi.com"], tokens=[], fused=[], look=[])
brand("tatacapital", "Tata Capital", "nbfc", ["tatacapital.com"], tokens=[], fused=["tatacapital"], look=["tatacapital"])
brand("muthoot", "Muthoot Finance", "nbfc", ["muthootfinance.com", "muthoot.com"], tokens=["muthoot"], fused=["muthoot"], look=["muthootfinance"])
brand("jar", "Jar (gold savings)", "nbfc", ["myjar.app", "jar.money"], tokens=[], fused=[], look=[])
brand("wazirx", "WazirX", "crypto", ["wazirx.com"], tokens=["wazirx"], fused=["wazirx"], look=["wazirx"])
brand("coindcx", "CoinDCX", "crypto", ["coindcx.com"], tokens=["coindcx"], fused=["coindcx"], look=["coindcx"])

# --- Shopping, delivery, telecom, travel, jobs ----------------------------------
brand("amazon", "Amazon", "ecommerce",
      ["amazon.in", "amazon.com", "amazon.co.uk", "amazon.ae", "amazon.de", "amazon.ca", "amazon.com.au", "amazon.sg", "amazon.jobs",
       "amazon.co.jp", "amazon.fr", "amazon.it", "amazon.es", "amazon.nl", "amazon.com.br", "amazon.com.mx", "amazon.sa", "amazon.eg", "amazon.com.tr",
       "amazon.pl", "amazon.se", "amazon.science", "amazonpay.in", "primevideo.com", "aboutamazon.com", "aboutamazon.in", "a.co", "amzn.to", "amzn.in",
       "media-amazon.com", "ssl-images-amazon.com", "audible.com", "audible.in", "amazonpay.com"],
      tokens=["amazon", "amzn"], fused=["amazon"], look=["amazon"], region="global")
brand("flipkart", "Flipkart", "ecommerce", ["flipkart.com", "flipkartcareers.com", "flipkart.net", "fkrt.it", "shopsy.in", "flipkartwholesale.com", "flixcart.com"],
      tokens=["flipkart"], fused=["flipkart"], look=["flipkart"])
brand("meesho", "Meesho", "ecommerce", ["meesho.com"], tokens=["meesho"], fused=["meesho"], look=["meesho"])
brand("myntra", "Myntra", "ecommerce", ["myntra.com", "myntassets.com"], tokens=["myntra"], fused=["myntra"], look=["myntra"])
brand("jio", "Jio", "telecom", ["jio.com", "jiomart.com", "jiocinema.com", "jiosaavn.com", "jiohotstar.com", "ril.com"],
      tokens=["jio"], fused=["myjio", "jiofiber", "jiomart", "jiorecharge"], look=["jiomart"])
brand("airtel", "Airtel", "telecom", ["airtel.in", "airtel.com", "airtelxstream.in", "airtelpaymentsbank.com", "airtel.africa"], tokens=["airtel"], fused=["airtel"], look=["airtel"])
brand("vi", "Vi (Vodafone Idea)", "telecom", ["myvi.in", "vodafoneidea.com"], tokens=[], fused=["vodafoneidea", "myvi"], look=[])
brand("bsnl", "BSNL", "telecom", ["bsnl.co.in", "bsnl.in"], tokens=["bsnl"], fused=["bsnl"], look=[])
brand("tataplay", "Tata Play", "telecom", ["tataplay.com", "tatasky.com"], tokens=[], fused=["tataplay", "tatasky"], look=["tataplay"])
brand("swiggy", "Swiggy", "ecommerce", ["swiggy.com"], tokens=["swiggy"], fused=["swiggy"], look=["swiggy"])
brand("zomato", "Zomato", "ecommerce", ["zomato.com", "eternal.com", "blinkit.com"], tokens=["zomato"], fused=["zomato"], look=["zomato"])
brand("naukri", "Naukri", "jobs", ["naukri.com", "naukrigulf.com", "infoedge.in"], tokens=["naukri"], fused=["naukri"], look=["naukri"])
brand("indeed", "Indeed", "jobs", ["indeed.com", "indeed.co.in"], tokens=["indeed"], fused=[], look=[], region="global")
brand("internshala", "Internshala", "jobs", ["internshala.com"], tokens=["internshala"], fused=["internshala"], look=["internshala"])
brand("tcs", "TCS", "jobs", ["tcs.com", "tata.com", "tcsion.com"], tokens=["tcs"], fused=["tcsion"], look=[])
brand("tata", "Tata group", "other", ["tata.com", "tatamotors.com", "tatasteel.com", "tatapower.com", "tataaig.com", "tatacliq.com", "tataneu.com", "tatadigital.com", "tatacapital.com", "tatanexarc.com", "tataplay.com", "tcs.com", "titan.co.in", "tanishq.co.in", "tatacommunications.com", "tatamotorsfinance.com", "tataev.com"],
      tokens=[], fused=["tatamotors", "tatasteel", "tataneu", "tatacliq"], look=["tatamotors"])
brand("reliance", "Reliance", "other", ["ril.com", "relianceretail.com", "reliancedigital.in", "jio.com", "ajio.com", "reliancegeneral.co.in", "reliancefoundation.org"],
      tokens=[], fused=["reliancedigital", "relianceretail"], look=["reliancedigital"])
brand("makemytrip", "MakeMyTrip", "travel", ["makemytrip.com"], tokens=["makemytrip", "mmt"], fused=["makemytrip"], look=["makemytrip"])
brand("indigo", "IndiGo", "travel", ["goindigo.in"], tokens=[], fused=["goindigo"], look=["goindigo"])
brand("airindia", "Air India", "travel", ["airindia.com", "airindia.in", "airindiaexpress.com"], tokens=[], fused=["airindia"], look=["airindia"])
brand("kbc", "KBC (Kaun Banega Crorepati)", "media", ["sonyliv.com", "setindia.com", "sonypicturesnetworks.com"], tokens=["kbc"], fused=["kaunbanegacrorepati", "kbclottery", "kbclucky"], look=[])
brand("dream11", "Dream11", "other", ["dream11.com"], tokens=["dream11"], fused=["dream11"], look=["dream11"])

# --- Global brands that dominate phishing feeds ----------------------------------
G = "global"
brand("google", "Google", "tech",
      ["google.com", "google.co.in", "youtube.com", "youtu.be", "gstatic.com", "googleapis.com", "android.com", "gmail.com", "withgoogle.com",
       "googleblog.com", "goo.gl", "g.co", "google.co.uk", "googlevideo.com", "ggpht.com", "googletagmanager.com", "google-analytics.com", "googlesyndication.com",
       "doubleclick.net", "blogger.com", "chrome.com", "chromium.org", "googlesource.com", "googleadservices.com", "youtube-nocookie.com", "ytimg.com", "googlemail.com"],
      tokens=["google", "gmail", "youtube"], fused=["google", "gmail", "youtube"], look=["google", "gmail", "youtube"], region=G)
brand("microsoft", "Microsoft", "tech",
      ["microsoft.com", "live.com", "outlook.com", "office.com", "office365.com", "microsoftonline.com", "sharepoint.com", "onedrive.com", "onenote.com", "bing.com",
       "skype.com", "xbox.com", "msn.com", "windows.com", "azure.com", "msft.net", "hotmail.com", "microsoft365.com", "1drv.ms", "aka.ms", "visualstudio.com", "msauth.net", "msftauth.net"],
      tokens=["microsoft", "office365", "hotmail", "onedrive", "sharepoint", "msoffice", "o365", "outlookweb", "owa"], fused=["microsoft", "office365", "hotmail", "onedrive", "sharepoint", "microsoftonline", "outlookweb", "outlooklogin", "outlookmail"],
      look=["microsoft", "outlook", "hotmail", "office"], region=G)
brand("apple", "Apple", "tech", ["apple.com", "icloud.com", "me.com", "mzstatic.com", "apple.co", "itunes.com", "cdn-apple.com"],
      tokens=["icloud", "appleid", "itunes"], fused=["icloud", "appleid", "itunes", "applesupport", "applecare"], look=["icloud"], region=G)
brand("meta", "Facebook / Meta", "social",
      ["facebook.com", "fb.com", "fb.me", "facebook.net", "fbcdn.net", "messenger.com", "meta.com", "instagram.com", "whatsapp.com", "whatsapp.net", "wa.me", "threads.net", "metastatus.com", "oculus.com", "fbsbx.com", "cdninstagram.com", "ig.me"],
      tokens=["facebook", "instagram", "whatsapp", "fb", "insta"], fused=["facebook", "instagram", "whatsapp", "metabusiness", "businessmeta", "metaverified", "fbbusiness"],
      look=["facebook", "instagram", "whatsapp"], region=G)
brand("linkedin", "LinkedIn", "social", ["linkedin.com", "lnkd.in", "licdn.com"], tokens=["linkedin"], fused=["linkedin"], look=["linkedin"], region=G)
brand("x", "X (Twitter)", "social", ["x.com", "twitter.com", "t.co", "twimg.com"], tokens=["twitter"], fused=["twitter"], look=["twitter"], region=G)
brand("telegram", "Telegram", "social", ["telegram.org", "t.me", "telegram.me", "telegra.ph", "telesco.pe", "tdesktop.com"], tokens=["telegram"], fused=["telegram"], look=["telegram"], region=G)
brand("netflix", "Netflix", "media", ["netflix.com", "netflix.net", "nflxext.com", "nflximg.net", "nflxvideo.net", "nflxso.net", "netflixtechblog.com", "fast.com"],
      tokens=["netflix"], fused=["netflix"], look=["netflix"], region=G)
brand("paypal", "PayPal", "payment", ["paypal.com", "paypal.me", "paypalobjects.com", "paypal-community.com", "braintreegateway.com", "venmo.com", "xoom.com"],
      tokens=["paypal"], fused=["paypal"], look=["paypal"], region=G)
brand("ebay", "eBay", "ecommerce", ["ebay.com", "ebay.co.uk", "ebay.de", "ebay.in", "ebaystatic.com", "ebayimg.com"], tokens=["ebay"], fused=[], look=[], region=G)
brand("dhl", "DHL", "delivery", ["dhl.com", "dhl.de", "dhl.co.uk", "dhlparcel.nl", "dhl.nl", "dpdhl.com"], tokens=["dhl"], fused=["dhlexpress", "dhlparcel"], look=[], region=G)
brand("fedex", "FedEx", "delivery", ["fedex.com"], tokens=["fedex"], fused=["fedex"], look=["fedex"], region=G)
brand("ups", "UPS", "delivery", ["ups.com"], tokens=[], fused=[], look=[], region=G)
brand("usps", "USPS", "delivery", ["usps.com"], tokens=["usps"], fused=["usps"], look=[], region=G)
brand("chase", "Chase", "bank", ["chase.com", "jpmorganchase.com", "jpmorgan.com"], tokens=["chase"], fused=["chasebank", "chaseonline"], look=[], region=G)
brand("wellsfargo", "Wells Fargo", "bank", ["wellsfargo.com", "wf.com"], tokens=["wellsfargo"], fused=["wellsfargo"], look=["wellsfargo"], region=G)
brand("bofa", "Bank of America", "bank", ["bankofamerica.com", "ml.com"], tokens=[], fused=["bankofamerica"], look=["bankofamerica"], region=G)
brand("citi", "Citi", "bank", ["citi.com", "citibank.com", "citigroup.com", "citibank.co.in"], tokens=["citibank"], fused=["citibank"], look=["citibank"], region=G)
brand("hsbc", "HSBC", "bank", ["hsbc.com", "hsbc.co.in", "hsbc.co.uk", "hsbc.com.hk"], tokens=["hsbc"], fused=["hsbc"], look=[], region=G)
brand("coinbase", "Coinbase", "crypto", ["coinbase.com"], tokens=["coinbase"], fused=["coinbase"], look=["coinbase"], region=G)
brand("binance", "Binance", "crypto", ["binance.com", "binance.us", "bnbchain.org", "binance.org"], tokens=["binance"], fused=["binance"], look=["binance"], region=G)
brand("metamask", "MetaMask", "crypto", ["metamask.io", "consensys.io", "consensys.net"], tokens=["metamask"], fused=["metamask"], look=["metamask"], region=G)
brand("trustwallet", "Trust Wallet", "crypto", ["trustwallet.com"], tokens=["trustwallet"], fused=["trustwallet"], look=["trustwallet"], region=G)
brand("ledger", "Ledger", "crypto", ["ledger.com"], tokens=[], fused=["ledgerlive", "ledgerwallet"], look=["ledger", "ledgerlive"], region=G)
brand("steam", "Steam", "gaming", ["steampowered.com", "steamcommunity.com", "steamstatic.com", "steamgames.com", "steam-chat.com"], tokens=[], fused=["steamcommunity", "steampowered"], look=["steamcommunity", "steampowered"], region=G)
brand("roblox", "Roblox", "gaming", ["roblox.com", "rbxcdn.com"], tokens=["roblox"], fused=["roblox"], look=["roblox"], region=G)
brand("discord", "Discord", "social", ["discord.com", "discord.gg", "discordapp.com", "discord.media", "discordapp.net", "discord.new"], tokens=["discord"], fused=["discord"], look=["discord"], region=G)
brand("docusign", "DocuSign", "tech", ["docusign.com", "docusign.net"], tokens=["docusign"], fused=["docusign"], look=["docusign"], region=G)
brand("dropbox", "Dropbox", "tech", ["dropbox.com", "dropboxusercontent.com", "db.tt"], tokens=["dropbox"], fused=["dropbox"], look=["dropbox"], region=G)
brand("adobe", "Adobe", "tech", ["adobe.com", "adobe.io", "acrobat.com", "adobelogin.com", "typekit.net"], tokens=["adobe"], fused=[], look=[], region=G)
brand("yahoo", "Yahoo", "tech", ["yahoo.com", "yahoo.co.jp", "yimg.com", "aol.com"], tokens=["yahoo"], fused=["yahoo"], look=[], region=G)
brand("att", "AT&T", "telecom", ["att.com", "att.net", "sbcglobal.net", "currently.com"], tokens=["att"], fused=["attmail"], look=[], region=G)
brand("aliexpress", "AliExpress / Alibaba", "ecommerce", ["aliexpress.com", "alibaba.com", "alipay.com", "aliexpress.us", "aliexpress.ru"], tokens=["aliexpress", "alibaba"], fused=["aliexpress", "alibaba"], look=["aliexpress"], region=G)
brand("booking", "Booking.com", "travel", ["booking.com", "bstatic.com"], tokens=[], fused=["bookingcom"], look=[], region=G)
brand("airbnb", "Airbnb", "travel", ["airbnb.com", "airbnb.co.in", "airbnb.co.uk", "muscache.com"], tokens=["airbnb"], fused=["airbnb"], look=["airbnb"], region=G)
brand("spotify", "Spotify", "media", ["spotify.com", "scdn.co", "spotify.link"], tokens=["spotify"], fused=["spotify"], look=["spotify"], region=G)
brand("openai", "OpenAI / ChatGPT", "tech", ["openai.com", "chatgpt.com", "oaistatic.com", "oaiusercontent.com"], tokens=["openai", "chatgpt"], fused=["openai", "chatgpt"], look=[], region=G)
brand("sbisec", "SBI Securities (Japan)", "broker", ["sbisec.co.jp", "sbigroup.co.jp"], tokens=["sbisec"], fused=["sbisec"], look=["sbisec"], region="jp")
brand("rakuten", "Rakuten", "ecommerce", ["rakuten.co.jp", "rakuten.com", "rakuten-card.co.jp", "rakuten-bank.co.jp", "rakuten-sec.co.jp"], tokens=["rakuten"], fused=["rakuten"], look=["rakuten"], region="jp")
brand("aeon", "AEON", "bank", ["aeon.co.jp", "aeon.com", "aeonbank.co.jp"], tokens=["aeon"], fused=["aeoncard"], look=[], region="jp")
brand("smbc", "SMBC", "bank", ["smbc.co.jp", "smbc-card.com", "smbcnikko.co.jp"], tokens=["smbc"], fused=["smbc"], look=[], region="jp")
brand("mufg", "MUFG", "bank", ["mufg.jp"], tokens=["mufg"], fused=["mufg"], look=[], region="jp")

# Top-level domains that a single company owns. Any address ending in them is theirs.
BRAND_TLDS = {"sbi": "sbi", "google": "google", "youtube": "google", "gmail": "google", "android": "google",
              "microsoft": "microsoft", "office": "microsoft", "xbox": "microsoft", "bing": "microsoft", "azure": "microsoft",
              "apple": "apple", "amazon": "amazon", "aws": "amazon", "hdfcbank": "hdfc", "airtel": "airtel", "jio": "jio"}

# ---------------------------------------------------------------------------
# Other well-known official sites (no impersonation rules, but a match proves
# the site is the real one). Indian first.
# ---------------------------------------------------------------------------
KNOWN = {
    # Government and public bodies outside .gov.in / .nic.in
    "rbi.org.in": ["Reserve Bank of India", "regulator"], "npci.org.in": ["NPCI", "payment"], "bhimupi.org.in": ["BHIM UPI", "payment"],
    "irctc.co.in": ["IRCTC", "travel"], "licindia.in": ["LIC of India", "insurance"], "nseindia.com": ["NSE", "exchange"], "bseindia.com": ["BSE", "exchange"],
    "mcxindia.com": ["MCX", "exchange"], "cdslindia.com": ["CDSL", "exchange"], "nsdl.co.in": ["NSDL", "exchange"], "amfiindia.com": ["AMFI", "regulator"],
    "pfrda.org.in": ["PFRDA", "regulator"], "nabard.org": ["NABARD", "bank"], "sidbi.in": ["SIDBI", "bank"], "eximbankindia.in": ["EXIM Bank", "bank"],
    "bescom.co.in": ["BESCOM", "utility"], "mahadiscom.in": ["MSEDCL", "utility"], "iitb.ac.in": ["IIT Bombay", "education"],
    # Banks not covered above
    "dcbbank.com": ["DCB Bank", "bank"], "equitasbank.com": ["Equitas SFB", "bank"], "ujjivansfb.in": ["Ujjivan SFB", "bank"], "janabank.com": ["Jana SFB", "bank"],
    "tmb.in": ["Tamilnad Mercantile Bank", "bank"], "jkbank.com": ["J&K Bank", "bank"], "csb.co.in": ["CSB Bank", "bank"], "dhanbank.com": ["Dhanlaxmi Bank", "bank"],
    "cityunionbank.com": ["City Union Bank", "bank"], "sc.com": ["Standard Chartered", "bank"], "dbs.com": ["DBS Bank", "bank"], "airtelpaymentsbank.com": ["Airtel Payments Bank", "bank"],
    "saraswatbank.com": ["Saraswat Bank", "bank"], "svcbank.com": ["SVC Bank", "bank"], "esafbank.com": ["ESAF SFB", "bank"], "suryodaybank.com": ["Suryoday SFB", "bank"],
    # Fintech, insurance, NBFC
    "cashfree.com": ["Cashfree", "payment"], "payu.in": ["PayU", "payment"], "billdesk.com": ["BillDesk", "payment"], "ccavenue.com": ["CCAvenue", "payment"],
    "instamojo.com": ["Instamojo", "payment"], "sliceit.com": ["slice", "payment"], "jupiter.money": ["Jupiter", "payment"], "fi.money": ["Fi", "payment"],
    "goniyo.com": ["Niyo", "payment"], "5paisa.com": ["5paisa", "broker"], "dhan.co": ["Dhan", "broker"], "kuvera.in": ["Kuvera", "broker"], "indmoney.com": ["INDmoney", "broker"],
    "sharekhan.com": ["Sharekhan", "broker"], "motilaloswal.com": ["Motilal Oswal", "broker"], "etmoney.com": ["ET Money", "broker"], "paisabazaar.com": ["Paisabazaar", "nbfc"],
    "bankbazaar.com": ["BankBazaar", "nbfc"], "policybazaar.com": ["Policybazaar", "insurance"], "acko.com": ["ACKO", "insurance"], "godigit.com": ["Digit Insurance", "insurance"],
    "starhealth.in": ["Star Health", "insurance"], "nivabupa.com": ["Niva Bupa", "insurance"], "careinsurance.com": ["Care Health", "insurance"], "tataaig.com": ["Tata AIG", "insurance"],
    "maxlifeinsurance.com": ["Max Life", "insurance"], "fibe.in": ["Fibe", "nbfc"], "moneytap.com": ["MoneyTap", "nbfc"], "cashe.co.in": ["CASHe", "nbfc"], "mpokket.in": ["mPokket", "nbfc"],
    "lazypay.in": ["LazyPay", "nbfc"], "getsimpl.com": ["Simpl", "payment"], "manappuram.com": ["Manappuram Finance", "nbfc"], "mahindrafinance.com": ["Mahindra Finance", "nbfc"],
    "hdbfs.com": ["HDB Financial", "nbfc"], "adityabirlacapital.com": ["Aditya Birla Capital", "nbfc"], "lendingkart.com": ["Lendingkart", "nbfc"], "indifi.com": ["Indifi", "nbfc"],
    "rupeek.com": ["Rupeek", "nbfc"], "cleartax.in": ["ClearTax", "other"], "khatabook.com": ["Khatabook", "other"], "okcredit.in": ["OkCredit", "other"],
    "zebpay.com": ["ZebPay", "crypto"], "coinswitch.co": ["CoinSwitch", "crypto"], "mudrex.com": ["Mudrex", "crypto"], "bitpay.com": ["BitPay", "crypto"],
    "kraken.com": ["Kraken", "crypto"], "kucoin.com": ["KuCoin", "crypto"], "okx.com": ["OKX", "crypto"], "bybit.com": ["Bybit", "crypto"], "crypto.com": ["Crypto.com", "crypto"],
    "blockchain.com": ["Blockchain.com", "crypto"],
    # Shopping, food, health
    "ajio.com": ["AJIO", "ecommerce"], "nykaa.com": ["Nykaa", "ecommerce"], "tatacliq.com": ["Tata CLiQ", "ecommerce"], "snapdeal.com": ["Snapdeal", "ecommerce"],
    "jiomart.com": ["JioMart", "ecommerce"], "bigbasket.com": ["BigBasket", "ecommerce"], "blinkit.com": ["Blinkit", "ecommerce"], "zeptonow.com": ["Zepto", "ecommerce"],
    "croma.com": ["Croma", "ecommerce"], "reliancedigital.in": ["Reliance Digital", "ecommerce"], "firstcry.com": ["FirstCry", "ecommerce"], "lenskart.com": ["Lenskart", "ecommerce"],
    "pepperfry.com": ["Pepperfry", "ecommerce"], "urbanladder.com": ["Urban Ladder", "ecommerce"], "purplle.com": ["Purplle", "ecommerce"], "mamaearth.in": ["Mamaearth", "ecommerce"],
    "boat-lifestyle.com": ["boAt", "ecommerce"], "decathlon.in": ["Decathlon", "ecommerce"], "ikea.com": ["IKEA", "ecommerce"], "licious.in": ["Licious", "ecommerce"],
    "1mg.com": ["Tata 1mg", "health"], "pharmeasy.in": ["PharmEasy", "health"], "netmeds.com": ["Netmeds", "health"], "apollo247.com": ["Apollo 24|7", "health"],
    "practo.com": ["Practo", "health"], "bookmyshow.com": ["BookMyShow", "ecommerce"], "dmart.in": ["DMart", "ecommerce"], "titan.co.in": ["Titan", "ecommerce"],
    "tanishq.co.in": ["Tanishq", "ecommerce"], "caratlane.com": ["CaratLane", "ecommerce"], "urbancompany.com": ["Urban Company", "ecommerce"], "olx.in": ["OLX", "ecommerce"],
    "quikr.com": ["Quikr", "ecommerce"], "justdial.com": ["Justdial", "other"], "indiamart.com": ["IndiaMART", "ecommerce"], "99acres.com": ["99acres", "other"],
    "magicbricks.com": ["MagicBricks", "other"], "housing.com": ["Housing.com", "other"], "nobroker.in": ["NoBroker", "other"], "cars24.com": ["CARS24", "other"],
    "cardekho.com": ["CarDekho", "other"], "spinny.com": ["Spinny", "other"],
    # Travel
    "goibibo.com": ["Goibibo", "travel"], "cleartrip.com": ["Cleartrip", "travel"], "yatra.com": ["Yatra", "travel"], "ixigo.com": ["ixigo", "travel"], "redbus.in": ["redBus", "travel"],
    "easemytrip.com": ["EaseMyTrip", "travel"], "olacabs.com": ["Ola", "travel"], "uber.com": ["Uber", "travel"], "rapido.bike": ["Rapido", "travel"], "spicejet.com": ["SpiceJet", "travel"],
    "akasaair.com": ["Akasa Air", "travel"], "oyorooms.com": ["OYO", "travel"], "agoda.com": ["Agoda", "travel"], "expedia.com": ["Expedia", "travel"], "trivago.com": ["trivago", "travel"],
    # Jobs and education
    "foundit.in": ["foundit", "jobs"], "shine.com": ["Shine", "jobs"], "apna.co": ["apna", "jobs"], "timesjobs.com": ["TimesJobs", "jobs"], "unstop.com": ["Unstop", "jobs"],
    "glassdoor.com": ["Glassdoor", "jobs"], "glassdoor.co.in": ["Glassdoor", "jobs"], "byjus.com": ["BYJU'S", "education"], "unacademy.com": ["Unacademy", "education"],
    "vedantu.com": ["Vedantu", "education"], "pw.live": ["Physics Wallah", "education"], "upgrad.com": ["upGrad", "education"], "simplilearn.com": ["Simplilearn", "education"],
    "coursera.org": ["Coursera", "education"], "udemy.com": ["Udemy", "education"], "edx.org": ["edX", "education"], "khanacademy.org": ["Khan Academy", "education"],
    "chitkara.edu.in": ["Chitkara University", "education"], "chitkarauniversity.edu.in": ["Chitkara University", "education"], "amity.edu": ["Amity University", "education"],
    "manipal.edu": ["Manipal", "education"], "bits-pilani.ac.in": ["BITS Pilani", "education"], "vit.ac.in": ["VIT", "education"], "srmist.edu.in": ["SRM", "education"],
    "lpu.in": ["LPU", "education"], "nptel.ac.in": ["NPTEL", "education"], "ugc.ac.in": ["UGC", "education"], "aicte-india.org": ["AICTE", "education"], "nta.ac.in": ["NTA", "education"],
    # Media and news
    "hotstar.com": ["JioHotstar", "media"], "jiocinema.com": ["JioCinema", "media"], "sonyliv.com": ["SonyLIV", "media"], "zee5.com": ["ZEE5", "media"], "primevideo.com": ["Prime Video", "media"],
    "mxplayer.in": ["MX Player", "media"], "gaana.com": ["Gaana", "media"], "jiosaavn.com": ["JioSaavn", "media"], "wynk.in": ["Wynk", "media"], "indiatimes.com": ["Times of India", "media"],
    "ndtv.com": ["NDTV", "media"], "hindustantimes.com": ["Hindustan Times", "media"], "thehindu.com": ["The Hindu", "media"], "indianexpress.com": ["Indian Express", "media"],
    "livemint.com": ["Mint", "media"], "moneycontrol.com": ["Moneycontrol", "media"], "news18.com": ["News18", "media"], "aajtak.in": ["Aaj Tak", "media"], "indiatoday.in": ["India Today", "media"],
    "bbc.com": ["BBC", "media"], "bbc.co.uk": ["BBC", "media"], "dailyhunt.in": ["Dailyhunt", "media"], "inshorts.com": ["Inshorts", "media"], "sharechat.com": ["ShareChat", "social"],
    "business-standard.com": ["Business Standard", "media"], "financialexpress.com": ["Financial Express", "media"], "zeebiz.com": ["Zee Business", "media"], "thequint.com": ["The Quint", "media"],
    "scroll.in": ["Scroll", "media"], "theprint.in": ["ThePrint", "media"], "reuters.com": ["Reuters", "media"], "nytimes.com": ["New York Times", "media"], "theguardian.com": ["The Guardian", "media"],
    "cnn.com": ["CNN", "media"],
    # Global platforms
    "wikipedia.org": ["Wikipedia", "other"], "reddit.com": ["Reddit", "social"], "quora.com": ["Quora", "social"], "pinterest.com": ["Pinterest", "social"], "snapchat.com": ["Snapchat", "social"],
    "tiktok.com": ["TikTok", "social"], "zoom.us": ["Zoom", "tech"], "salesforce.com": ["Salesforce", "tech"], "cloudflare.com": ["Cloudflare", "tech"], "stripe.com": ["Stripe", "payment"],
    "shopify.com": ["Shopify", "tech"], "wordpress.org": ["WordPress", "tech"], "mozilla.org": ["Mozilla", "tech"], "anthropic.com": ["Anthropic", "tech"], "claude.ai": ["Claude", "tech"],
    "visa.com": ["Visa", "payment"], "visa.co.in": ["Visa", "payment"], "mastercard.com": ["Mastercard", "payment"], "mastercard.co.in": ["Mastercard", "payment"], "americanexpress.com": ["American Express", "payment"],
    "rupay.co.in": ["RuPay", "payment"], "wise.com": ["Wise", "payment"], "revolut.com": ["Revolut", "payment"], "temu.com": ["Temu", "ecommerce"], "shein.com": ["SHEIN", "ecommerce"],
    "walmart.com": ["Walmart", "ecommerce"], "target.com": ["Target", "ecommerce"], "bestbuy.com": ["Best Buy", "ecommerce"], "etsy.com": ["Etsy", "ecommerce"],
    "nvidia.com": ["NVIDIA", "tech"], "intel.com": ["Intel", "tech"], "samsung.com": ["Samsung", "tech"], "oneplus.in": ["OnePlus", "tech"], "mi.com": ["Xiaomi", "tech"], "realme.com": ["realme", "tech"],
    "oracle.com": ["Oracle", "tech"], "ibm.com": ["IBM", "tech"], "infosys.com": ["Infosys", "jobs"], "wipro.com": ["Wipro", "jobs"], "hcltech.com": ["HCLTech", "jobs"], "techmahindra.com": ["Tech Mahindra", "jobs"],
    "accenture.com": ["Accenture", "jobs"], "deloitte.com": ["Deloitte", "jobs"], "pwc.com": ["PwC", "jobs"], "ey.com": ["EY", "jobs"], "kpmg.com": ["KPMG", "jobs"], "cognizant.com": ["Cognizant", "jobs"],
    "capgemini.com": ["Capgemini", "jobs"], "ltimindtree.com": ["LTIMindtree", "jobs"], "naukri.com": ["Naukri", "jobs"], "slack.com": ["Slack", "tech"], "notion.so": ["Notion", "tech"],
    "canva.com": ["Canva", "tech"], "figma.com": ["Figma", "tech"], "atlassian.com": ["Atlassian", "tech"], "gitlab.com": ["GitLab", "tech"], "stackoverflow.com": ["Stack Overflow", "tech"],
    "duckduckgo.com": ["DuckDuckGo", "tech"], "proton.me": ["Proton", "tech"], "zoho.com": ["Zoho", "tech"], "zoho.in": ["Zoho", "tech"], "freshworks.com": ["Freshworks", "tech"],
}

# Platforms where anyone can publish under the platform's name. A page there was
# made by a user, so the platform's good name says nothing about it.
UGC_HOSTS = {
    "t.me": ["group or channel", "ग्रुप या चैनल"], "telegram.me": ["group or channel", "ग्रुप या चैनल"], "telegra.ph": ["post", "पोस्ट"],
    "wa.me": ["WhatsApp number", "WhatsApp नंबर"], "chat.whatsapp.com": ["group", "ग्रुप"], "api.whatsapp.com": ["WhatsApp number", "WhatsApp नंबर"],
    "play.google.com": ["app", "ऐप"], "apps.apple.com": ["app", "ऐप"], "sites.google.com": ["site", "साइट"], "docs.google.com": ["form or file", "फ़ॉर्म या फ़ाइल"],
    "drive.google.com": ["file", "फ़ाइल"], "forms.gle": ["form", "फ़ॉर्म"], "storage.googleapis.com": ["file", "फ़ाइल"], "firebasestorage.googleapis.com": ["file", "फ़ाइल"],
    "script.google.com": ["script page", "स्क्रिप्ट पेज"], "translate.goog": ["translated copy", "अनुवादित कॉपी"], "groups.google.com": ["group", "ग्रुप"],
    "linkedin.com": ["page or post", "पेज या पोस्ट"], "facebook.com": ["page or group", "पेज या ग्रुप"], "fb.com": ["page or group", "पेज या ग्रुप"], "m.facebook.com": ["page or group", "पेज या ग्रुप"],
    "instagram.com": ["account", "अकाउंट"], "youtube.com": ["channel or video", "चैनल या वीडियो"], "youtu.be": ["video", "वीडियो"], "x.com": ["account or post", "अकाउंट या पोस्ट"],
    "twitter.com": ["account or post", "अकाउंट या पोस्ट"], "github.com": ["page", "पेज"], "gist.github.com": ["page", "पेज"], "raw.githubusercontent.com": ["file", "फ़ाइल"],
    "medium.com": ["post", "पोस्ट"], "linktr.ee": ["link page", "लिंक पेज"], "reddit.com": ["post", "पोस्ट"], "quora.com": ["post", "पोस्ट"], "discord.gg": ["server invite", "सर्वर इनवाइट"],
    "discord.com": ["server invite", "सर्वर इनवाइट"], "dropbox.com": ["file", "फ़ाइल"], "1drv.ms": ["file", "फ़ाइल"], "onedrive.live.com": ["file", "फ़ाइल"],
    "notion.site": ["page", "पेज"], "notion.so": ["page", "पेज"], "sites.google.com/view": ["site", "साइट"], "canva.site": ["page", "पेज"], "my.canva.site": ["page", "पेज"], "pastebin.com": ["page", "पेज"], "docsend.com": ["file", "फ़ाइल"],
    "s3.amazonaws.com": ["file", "फ़ाइल"], "blob.core.windows.net": ["file", "फ़ाइल"], "web.core.windows.net": ["site", "साइट"], "ipfs.io": ["file", "फ़ाइल"],
    "jotform.com": ["form", "फ़ॉर्म"], "form.jotform.com": ["form", "फ़ॉर्म"], "typeform.com": ["form", "फ़ॉर्म"], "surveymonkey.com": ["form", "फ़ॉर्म"],
    "pages.razorpay.com": ["payment page", "पेमेंट पेज"], "rzp.io": ["payment page", "पेमेंट पेज"], "razorpay.me": ["payment page", "पेमेंट पेज"], "paypal.me": ["payment page", "पेमेंट पेज"],
    "instamojo.com": ["payment page", "पेमेंट पेज"], "imjo.in": ["payment page", "पेमेंट पेज"],
    "forms.office.com": ["form", "फ़ॉर्म"], "forms.cloud.microsoft": ["form", "फ़ॉर्म"], "forms.microsoft.com": ["form", "फ़ॉर्म"], "sway.office.com": ["page", "पेज"],
    "sway.cloud.microsoft": ["page", "पेज"], "cdn.discordapp.com": ["file", "फ़ाइल"], "media.discordapp.net": ["file", "फ़ाइल"], "payments.cashfree.com": ["payment page", "पेमेंट पेज"],
    "web.archive.org": ["saved copy", "सेव की गई कॉपी"], "telegram.dog": ["group or channel", "ग्रुप या चैनल"], "onedrive.com": ["file", "फ़ाइल"], "cosmofeed.com": ["payment page", "पेमेंट पेज"], "topmate.io": ["page", "पेज"],
}
# Paths on UGC hosts that are the platform's own pages, not user content.
GENERIC_PATHS = ["", "/", "/login", "/signup", "/home", "/feed", "/about", "/help", "/legal", "/privacy", "/terms", "/jobs", "/explore", "/search", "/store", "/store/apps", "/settings"]

# Free site builders and hosting platforms, for those the public suffix list misses.
FREE_HOSTS = [
    "weebly.com", "weeblysite.com", "000webhostapp.com", "godaddysites.com", "my.id", "biz.id", "web.id", "gitbook.io", "teachable.com", "usrfiles.com",
    "filesusr.com", "webcindario.com", "mybluehost.me", "yolasite.com", "jimdosite.com", "jimdofree.com", "tilda.ws", "square.site", "business.site",
    "wixsite.com", "wix.com", "editorx.io", "strikingly.com", "mystrikingly.com", "carrd.co", "webflow.io", "framer.website", "framer.app", "framer.ai",
    "notion.site", "super.site", "glide.page", "glideapp.io", "bubbleapps.io", "softr.app", "typedream.app", "duda.co", "site123.me", "ucraft.site",
    "swtest.ru", "xsph.ru", "tw1.ru", "tmweb.ru", "netlify.com", "surge.sh", "ngrok.io", "ngrok-free.app", "ngrok.app", "loca.lt", "serveo.net",
    "trycloudflare.com", "workers.dev", "pages.dev", "r2.dev", "vercel.app", "netlify.app", "github.io", "gitlab.io", "glitch.me", "repl.co", "replit.app",
    "replit.dev", "herokuapp.com", "onrender.com", "fly.dev", "railway.app", "web.app", "firebaseapp.com", "appspot.com", "azurewebsites.net", "azurestaticapps.net",
    "blogspot.com", "wordpress.com", "tumblr.com", "000webhost.com", "byethost.com", "epizy.com", "rf.gd", "infinityfreeapp.com", "freecluster.eu", "ezyro.com",
    "duckdns.org", "ddns.net", "no-ip.org", "hopto.org", "zapto.org", "sytes.net", "servehttp.com", "myftp.biz", "dynu.net", "freeddns.org", "linkpc.net",
    "dweb.link", "ipfs.dweb.link", "cf-ipfs.com", "cloudflare-ipfs.com", "nftstorage.link", "w3s.link", "infura-ipfs.io", "pinata.cloud", "fleek.co", "on-fleek.app",
    "4everland.app", "pantheonsite.io", "plesk.page", "cprapid.com", "ewp.live", "appdomain.cloud", "myshopify.com", "mypinata.cloud", "codesandbox.io", "csb.app",
    "stackblitz.io", "lovable.app", "bolt.host", "web.core.windows.net", "blob.core.windows.net", "amplifyapp.com", "cloudfront.net", "translate.goog",
    "cloudapp.azure.com", "cloudapp.net", "trafficmanager.net", "azureedge.net", "azurefd.net", "googleusercontent.com", "cloudfunctions.net", "run.app",
    "amazonaws.com", "elasticbeanstalk.com", "awsapprunner.com", "on.aws", "digitaloceanspaces.com", "ondigitalocean.app", "oraclecloud.com", "appdomain.cloud",
    "linodeobjects.com", "backblazeb2.com", "wasabisys.com", "b-cdn.net", "akamaized.net", "edgekey.net", "pythonanywhere.com", "000webhostapp.com", "hostinger.site",
    "sharepoint.com", "my.salesforce-sites.com", "force.com", "zohosites.com", "zohosites.in", "odoo.com", "hubspotpagebuilder.com", "wixstudio.io",
    "emlnk.com", "ukit.me", "mobirisesite.com", "site.pro", "webnode.page", "webnode.com", "ucoz.net", "ucoz.ru", "narod.ru", "beget.tech", "hostingersite.com",
]

SHORTENERS = [
    "bit.ly", "bitly.com", "tinyurl.com", "cutt.ly", "rb.gy", "is.gd", "t.ly", "shorturl.at", "tiny.cc", "ow.ly", "buff.ly", "rebrand.ly", "s.id", "v.gd", "goo.gl",
    "t.co", "short.gy", "tiny.one", "surl.li", "clck.ru", "shorte.st", "bc.vc", "adf.ly", "qr.ae", "u.to", "shorturl.asia", "rebrandly.com", "bl.ink", "lnkd.in",
    "amzn.to", "fkrt.it", "wa.link", "tg.me", "1url.in", "linkly.link", "shrtco.de", "urlz.fr", "dub.sh", "spoo.me", "shorturl.gg", "is.gd", "da.gd",
]

# Endings used much more by scams than by real businesses (Spamhaus / Interisle reports).
RISKY_TLDS = [
    "xyz", "top", "click", "buzz", "icu", "cyou", "sbs", "cfd", "rest", "monster", "quest", "bond", "vip", "win", "loan", "work", "men", "gq", "tk", "ml", "cf", "ga",
    "fun", "site", "online", "website", "space", "pw", "lol", "mom", "cam", "beauty", "hair", "makeup", "skin", "autos", "boats", "homes", "yachts", "motorcycles",
    "click", "link", "country", "stream", "download", "racing", "date", "party", "bid", "trade", "webcam", "kim", "fit", "life", "live", "shop", "store", "today",
    "support", "help", "digital", "best", "world", "info", "cc", "su", "ws", "zip", "mov", "run", "tokyo", "xin", "asia", "cyou", "uno", "bar", "biz", "club", "pro", "ink", "one", "icu", "cfd",
]
# Of those, the ones where a real business is rare enough to count on their own.
# The worst of these count on their own; the rest (xyz, click, win, loan, men, date, download, stream) only add weight.
MID_RISKY_TLDS = ["xyz", "click", "win", "loan", "men", "date", "download", "stream", "link", "shop", "online", "site", "live", "store", "info"]
VERY_RISKY_TLDS = ["xyz", "top", "click", "buzz", "icu", "cyou", "sbs", "cfd", "rest", "monster", "quest", "bond", "gq", "tk", "ml", "cf", "ga", "lol", "mom", "cam",
                   "beauty", "hair", "makeup", "skin", "autos", "boats", "homes", "yachts", "motorcycles", "zip", "mov", "su", "pw", "win", "loan", "men", "kim", "bid", "racing", "date", "stream", "download", "party", "xin", "uno"]

WORDS = {
    # Ask you to log in, verify or unlock something. Two of these in one address is a warning on its own.
    "credential": ["login", "logon", "signin", "verify", "verification", "verified", "validate", "validation", "secure", "security", "account", "accounts",
                   "update", "auth", "authenticate", "authentication", "confirm", "confirmation", "password", "passcode", "otp", "kyc", "ekyc", "rekyc", "netbanking",
                   "ebanking", "ibanking", "mbanking", "unlock", "unblock", "blocked", "suspend", "suspended", "suspension", "recover", "recovery", "restore",
                   "reactivate", "activation", "webmail", "mailbox", "wallet", "walletconnect", "seed", "seedphrase", "dapp", "airdrop", "panupdate", "pancard",
                   "aadhaarupdate", "linkaadhaar", "kycupdate", "deactivate", "deactivated", "expire", "expired", "expiry", "locked", "unusual", "signon", "sso", "mfa", "2fa",
                   "connexion", "identification", "authentification", "anmelden", "anmeldung", "acceso", "acessar", "acesso", "conta", "cuenta", "compte",
                   "sicurezza", "sicherheit", "verifica", "verificar", "aggiornamento", "actualizacion", "actualizar", "aktualisierung", "securite", "seguridad", "konto"],
    # Service words that scam sites put next to a brand ("sbi-customer-care"). Only count together with a brand or a credential word.
    "service": ["apk", "download", "install", "fee", "fees", "deposit", "fir", "support", "service", "services", "care", "helpdesk", "helpline", "customercare", "customer", "billing", "invoice", "refund", "refunds", "tracking", "track",
                "parcel", "delivery", "redeliver", "redelivery", "reschedule", "customs", "pending", "challan", "echallan", "fine", "penalty", "toll", "fastag", "bill",
                "electricitybill", "disconnection", "alert", "alerts", "notice", "warning", "limited", "limit", "restricted", "claim", "claims", "complaint", "helpcenter",
                "verification", "status", "contact", "number", "tollfree", "callcenter", "appeal", "appeals", "breach",
                "violation", "violations", "copyright", "disabled", "unpaid", "overdue", "outstanding", "dispute", "chargeback", "reward", "subscribe", "subscription", "renew", "renewal", "membership", "premium", "unsubscribe"],
    # Promise prizes or free money. One of these next to a brand, or two together, is a warning.
    "lure": ["reward", "rewards", "rewardpoints", "prize", "prizes", "lottery", "winner", "winners", "lucky", "luckydraw", "cashback", "giftcard", "giftcards", "jackpot",
             "giveaway", "scratchcard", "scratch", "kbc", "crorepati", "freerecharge", "bonus", "bonuses", "doublemoney", "claimreward", "redeem", "redemption", "points",
             "incentive", "subsidy", "yojana", "freegift", "spinwheel", "luckywheel", "premio", "regalo", "gewinn", "cadeau", "gratuit", "nitro", "robux", "vbucks", "freenitro"],
    # Money words. Normal for real businesses too, so they only add weight to other signs.
    "money": ["free", "offer", "offers", "gift", "gifts", "earn", "earning", "earnings", "income", "profit", "profits", "cash", "money", "loan", "loans", "instantloan",
              "quickloan", "credit", "approved", "preapproved", "salary", "parttime", "workfromhome", "wfh", "task", "tasks", "vip", "sureshot", "signals", "tips", "trading",
              "invest", "investment", "returns", "guaranteed", "crypto", "usdt", "btc", "mining", "recharge", "scheme", "spin", "win", "won", "draw", "double", "bet", "casino", "oferta", "gratis", "topup", "robux", "diamonds", "uc"],
    # Neutral words that often surround a brand name.
    "context": ["bank", "banking", "online", "net", "india", "ind", "in", "app", "apps", "pay", "payment", "payments", "card", "cards", "help", "official", "portal", "center",
                "centre", "team", "info", "web", "site", "home", "my", "mobile", "phone", "call", "sms", "digital", "user", "users", "member", "members", "client", "clients",
                "store", "shop", "shopping", "mall", "sale", "sales", "deals", "deal", "global", "group", "hq", "corp", "inc", "ltd", "pvt", "upi", "id", "page", "pages",
                "link", "links", "go", "get", "now", "new", "best", "plus", "pro", "prime", "premium", "safe", "check", "access", "panel", "dashboard", "cloud", "mail",
                "email", "box", "drive", "doc", "docs", "file", "files", "share", "data", "office", "us", "uk", "usa", "asia", "eu", "careers", "career", "jobs", "job", "work",
                "recruit", "recruitment", "hr", "hire", "hiring", "intern", "internship", "the", "and", "of", "for", "to", "co", "com", "org", "www", "m", "en", "hi", "tv",
                "live", "connect", "service", "direct", "express", "point", "hub", "zone", "world", "club", "plan", "plans", "policy", "insurance", "life", "fund", "funds",
                "finance", "finserv", "money", "wealth", "market", "markets", "trade", "pos", "merchant", "business", "biz", "corporate", "retail", "personal", "user"],
}

# Places where an IDN homograph swaps a Latin letter for a lookalike.
HOMOGLYPHS = {"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "@": "a", "$": "s", "!": "i", "|": "l",
              "а": "a", "с": "c", "е": "e", "о": "o", "р": "p", "ѕ": "s", "х": "x", "у": "y", "і": "i", "ј": "j", "ԁ": "d", "һ": "h", "ԍ": "g", "ո": "n", "ν": "v", "ο": "o", "ι": "i", "κ": "k", "τ": "t"}
MULTI_HOMOGLYPHS = {"rn": "m", "vv": "w", "cl": "d", "nn": "m"}

# Betting and gambling (illegal or unregulated for most Indians).
BETTING = ["1win", "1xbet", "1xlite", "1xbit", "melbet", "mostbet", "parimatch", "dafabet", "betway", "bet365", "stake", "fairplay", "lotus365", "reddy", "reddyanna", "satta", "matka",
           "sattaking", "aviator", "teenpatti", "rummy", "casino", "betting", "sportsbook", "khelo", "4rabet", "batery", "jeetwin", "babu88", "baji", "crickex", "mahadev",
           "lotusbook", "laser247", "tiger exchange", "skyexchange", "diamondexch", "goldexch", "radheexch", "world777", "allpanel"]

GOV_WORDS = ["gov", "govt", "goi", "sarkari", "sarkar", "bharatsarkar", "govin", "gov-in", "nic-in", "nicin", "mygov", "pmyojana", "pradhanmantri", "modiyojana", "pmmodi"]


def build_suffixes() -> list[str]:
    """Public suffix rules from tldextract's offline snapshot (minus Japanese city rules),
    plus the restricted Indian zones the snapshot does not know yet."""
    import tldextract

    snap = pathlib.Path(tldextract.__file__).parent / ".tld_set_snapshot"
    rules, section = [], None
    for line in snap.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if "===BEGIN PRIVATE DOMAINS===" in s:
            section = "p"
        if not s or s.startswith("//"):
            continue
        if "." not in s and not s.startswith("*"):
            continue  # single-label TLDs need no rule: the last label is always a suffix
        if s.endswith(".jp") and s.count(".") >= 1 and not s.startswith(("co.", "ne.", "or.", "ac.", "go.", "ad.", "ed.", "gr.", "lg.")):
            continue
        rules.append(s.encode("idna").decode() if not s.isascii() and not s.startswith(("*", "!")) else s)
    extra = list(ZONES) + [h for h in FREE_HOSTS if "." in h]
    return sorted(set(rules) | set(extra))


# Ordinary words and place names that sit one typo away from a brand
# ("canada" vs Canara Bank, "telegraf" vs Telegram). Hunspell's en_US word list
# is used only to find them; the app ships just the short exception list.
DICTIONARIES = ["/usr/share/hunspell/en_US.dic", "/usr/share/dict/words"]
EXTRA_WORDS = ["canada", "jcloud", "telegraf", "kotaku", "cooking", "blogher", "booking", "grow", "tomato", "finance", "outlook", "steamy", "netflux"]


def dictionary_exceptions() -> list[str]:
    import importlib
    import sys

    sys.path.insert(0, str(HERE.parent))
    li = importlib.import_module("app.linkintel")
    li.data.cache_clear()
    words = set(EXTRA_WORDS)
    for path in DICTIONARIES:
        f = pathlib.Path(path)
        if f.exists():
            for line in f.read_text(encoding="utf-8", errors="ignore").splitlines()[1:]:
                w = line.split("/", 1)[0].strip().lower()
                if w.isalpha() and w.isascii() and len(w) >= 5:
                    words.add(w)
    out = []
    for w in sorted(words):
        p = li.parse(w + ".com")
        if li._lookalike_hits(p):
            out.append(w)
    li.data.cache_clear()
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = {
        "version": "2026-10-23",
        "note": "Generated by tools/build_linkdata.py. Edit that file, not this one.",
        "zones": ZONES,
        "brands": B,
        "known": KNOWN,
        "ugc_hosts": UGC_HOSTS,
        "generic_paths": GENERIC_PATHS,
        "free_hosts": sorted(set(FREE_HOSTS)),
        "shorteners": sorted(set(SHORTENERS)),
        "risky_tlds": sorted(set(RISKY_TLDS)),
        "very_risky_tlds": sorted(set(VERY_RISKY_TLDS)),
        "mid_risky_tlds": sorted(set(MID_RISKY_TLDS)),
        "words": {k: sorted(set(v)) for k, v in WORDS.items()},
        "homoglyphs": HOMOGLYPHS,
        "brand_tlds": BRAND_TLDS,
        "multi_homoglyphs": MULTI_HOMOGLYPHS,
        "betting": BETTING,
        "gov_words": GOV_WORDS,
    }
    data["lookalike_exceptions"] = []
    (OUT / "linkintel.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    sfx = build_suffixes()
    (OUT / "public_suffixes.txt").write_text(
        "// Public Suffix List rules (https://publicsuffix.org, MPL-2.0) plus NexVerify additions.\n"
        "// Generated by tools/build_linkdata.py.\n" + "\n".join(sfx) + "\n", encoding="utf-8")
    data["lookalike_exceptions"] = dictionary_exceptions()
    (OUT / "linkintel.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"brands {len(B)}, known {len(KNOWN)}, suffix rules {len(sfx)}, lookalike exceptions {len(data['lookalike_exceptions'])}")


if __name__ == "__main__":
    main()
