// @ts-nocheck
// All page text in English and Hindi: each entry is [english, hindi].
import type { Lang } from "./api";

export const S: any = {
  eyebrow: ["Scam checker for India", "भारत के लिए स्कैम चेकर"],
  h1a: ["Check it", "पैसे भेजने से"], h1b: ["before you pay.", "पहले जाँचें।"],
  lead: ["Paste the name or link of a loan app, stock-tips group, job offer or website. NexVerify checks official records and tells you, in plain words, whether to pay.",
         "किसी लोन ऐप, स्टॉक-टिप्स ग्रुप, नौकरी के ऑफ़र या वेबसाइट का नाम या लिंक डालें। NexVerify सरकारी रिकॉर्ड जाँचकर आसान शब्दों में बताता है कि पैसे भेजें या नहीं।"],
  placeholder: ["App name, website or Telegram link", "ऐप का नाम, वेबसाइट या टेलीग्राम लिंक"],
  check: ["Check now", "अभी जाँचें"], checkShort: ["Check", "जाँचें"],
  try: ["Try:", "आज़माएँ:"],
  note: ["Preview: only the four sample cases run here, with made-up data. Live checks on anything run in the app on your computer.",
         "प्रीव्यू: यहाँ सिर्फ़ चार सैंपल केस नकली डेटा के साथ चलते हैं। किसी भी चीज़ की लाइव जाँच आपके कंप्यूटर पर ऐप में होती है।"],
  miss: ["This preview has no server, so it can only run the four sample cases. Run the app on your computer to check that live.",
         "इस प्रीव्यू में सर्वर नहीं है, इसलिए सिर्फ़ चार सैंपल केस चलते हैं। इसे लाइव जाँचने के लिए अपने कंप्यूटर पर ऐप चलाएँ।"],
  help: ["Fraud? Call <b>1930</b>", "फ्रॉड? कॉल करें <b>1930</b>"],
  mode: ["Preview · sample data", "प्रीव्यू · सैंपल डेटा"],
  howTitle: ["How it works", "यह कैसे काम करता है"], howSub: ["Three steps, about half a minute.", "तीन कदम, लगभग आधा मिनट।"],
  answersTitle: ["You get one of three answers", "आपको तीन में से एक जवाब मिलता है"],
  answersSub: ["No confusing numbers. The score is there if you want it.", "कोई उलझन नहीं। स्कोर भी दिखता है, अगर आप देखना चाहें।"],
  checksTitle: ["What we check", "हम क्या जाँचते हैं"], checksSub: ["Five sources at the same time. Every problem we find comes with proof.", "पाँच स्रोत एक साथ। हर समस्या के साथ सबूत मिलता है।"],
  samplesTitle: ["Try a sample case", "सैंपल केस आज़माएँ"], samplesSub: ["Made-up cases that run through the real checking engine.", "नकली केस, जो असली जाँच इंजन से चलते हैं।"],
  run: ["Run this check →", "यह जाँच चलाएँ →"],
  footBig: ["Lost money? Call <b>1930</b> now.", "पैसे गए? अभी <b>1930</b> पर कॉल करें।"],
  footSmall: ["The first hours matter most: the bank may still be able to stop the money. Then report it at cybercrime.gov.in. NexVerify checks public records; it is not legal advice.",
              "पहले कुछ घंटे सबसे ज़रूरी हैं: बैंक शायद पैसा रोक सके। फिर cybercrime.gov.in पर रिपोर्ट करें। NexVerify सार्वजनिक रिकॉर्ड जाँचता है; यह कानूनी सलाह नहीं है।"],
  sample: ["Sample case, made-up data", "सैंपल केस, नकली डेटा"],
  checking: ["Checking", "जाँच हो रही है"], doneOf: ["of 5 checks done", "/5 जाँच पूरी"],
  scoreWord: ["score", "स्कोर"],
  callBox: ["Already paid? Call", "पैसे भेज दिए? कॉल करें"],
  proof: ["View proof (PDF)", "सबूत देखें (PDF)"], again: ["Check again", "फिर से जाँचें"],
  whyTitle: ["Why", "क्यों"], allGood: ["None of the five checks found a problem. Still, never pay upfront to someone you don't know.", "पाँचों जाँचों में कोई समस्या नहीं मिली। फिर भी अनजान लोगों को पहले पैसे न दें।"],
  checksDone: ["The 5 checks", "पाँच जाँचें"], tapTile: ["Tap a check to see each step it took.", "हर कदम देखने के लिए किसी जाँच पर टैप करें।"],
  todoTitle: ["What to do now", "अब क्या करें"],
  notPaid: ["Haven't paid yet?", "अभी पैसे नहीं भेजे?"], paid: ["Already paid?", "पैसे भेज चुके हैं?"],
  copy: ["Copy complaint", "शिकायत कॉपी करें"], copied: ["Copied", "कॉपी हो गया"], selected: ["Selected: press Ctrl+C", "चुना गया: Ctrl+C दबाएँ"],
  portal: ["Open cybercrime.gov.in", "cybercrime.gov.in खोलें"],
  tech: ["Technical details", "तकनीकी जानकारी"], techSub: ["claims vs records, evidence, rules", "दावे बनाम रिकॉर्ड, सबूत, नियम"],
  tClaims: ["What they claim vs what records show", "उनका दावा बनाम रिकॉर्ड"],
  claim: ["They claim", "दावा"], how: ["How we checked", "कैसे जाँचा"], found: ["Records show", "रिकॉर्ड में"], proofCol: ["Proof", "सबूत"], cut: ["Points", "अंक"],
  tEvidence: ["Evidence files (each sealed with a SHA-256 hash)", "सबूत फ़ाइलें (हर एक SHA-256 हैश से सील)"],
  tComplaint: ["Complaint text for cybercrime.gov.in", "cybercrime.gov.in के लिए शिकायत टेक्स्ट"],
  tRules: ["All scoring rules (fixed, no AI guessing)", "स्कोर के सभी नियम (तय, AI अंदाज़ा नहीं)"],
  open: ["Open", "खोलें"], close: ["Close", "बंद करें"],
  pdfTitle: ["Proof PDF", "सबूत PDF"], pdfNote: ["In the app this downloads as a real PDF. These are its pages.", "ऐप में यह असली PDF डाउनलोड होता है। ये उसके पेज हैं।"]
};
export const VERDICT: any = {
  VERIFIED_OFFICIAL: ["green", "Verified Official", "प्रमाणित आधिकारिक", "Official regulated portal", "आधिकारिक विनियमित पोर्टल"],
  LOOKS_OK: ["green", "Looks safe", "सुरक्षित लगता है", "Records look consistent", "रिकॉर्ड ठीक लगते हैं"],
  LOW_RISK: ["green", "Looks safe", "सुरक्षित लगता है", "Records look consistent", "रिकॉर्ड ठीक लगते हैं"],
  COULDNT_VERIFY: ["gray", "Couldn't verify", "जाँच नहीं हो पाई", "Not enough data, don't pay yet", "जानकारी कम, अभी पैसे न भेजें"],
  UNKNOWN: ["gray", "Couldn't verify", "जाँच नहीं हो पाई", "Not enough data, don't pay yet", "जानकारी कम, अभी पैसे न भेजें"],
  SUSPICIOUS: ["amber", "Suspicious", "संदिग्ध", "Warning signs detected", "ख़तरे के संकेत मिले"],
  CAUTION: ["amber", "Be careful", "सावधान रहें", "Some warning signs", "कुछ ख़तरे के संकेत"],
  HIGH_RISK: ["red", "Don't pay", "पैसे न भेजें", "High risk", "बहुत ज़्यादा जोखिम"]
};
export const STEPS: any = [
  [["Paste a name or link", "An app name, a website, a Play Store link or a Telegram group."], ["नाम या लिंक डालें", "ऐप का नाम, वेबसाइट, Play Store लिंक या टेलीग्राम ग्रुप।"]],
  [["We check 5 sources", "Government lists, the company register, the app itself and complaints online."], ["हम 5 स्रोत जाँचते हैं", "सरकारी सूचियाँ, कंपनी रजिस्टर, ऐप खुद और ऑनलाइन शिकायतें।"]],
  [["Get a clear answer", "Don't pay, be careful, or no red flags, with the reasons and proof."], ["साफ़ जवाब पाएँ", "पैसे न भेजें, सावधान रहें, या कोई ख़तरा नहीं, कारण और सबूत के साथ।"]]
];
export const ANSWERS: any = [
  ["red", "x", ["Don't pay", "0-39", "Strong signs of a scam. Do not send money or share an OTP."], ["पैसे न भेजें", "0-39", "स्कैम के पक्के संकेत। पैसे न भेजें, OTP न बताएँ।"]],
  ["amber", "!", ["Be careful", "40-69", "Some warning signs. Check more before you pay anything."], ["सावधान रहें", "40-69", "कुछ ख़तरे के संकेत। पैसे देने से पहले और जाँचें।"]],
  ["green", "ok", ["No red flags", "70-100", "Records look consistent. Still, never pay strangers upfront."], ["कोई ख़तरा नहीं", "70-100", "रिकॉर्ड ठीक लगते हैं। फिर भी अनजान को पहले पैसे न दें।"]]
];
export const CHECKS: any = {
  rbi: [["Is it a real lender?", "Loan apps must be run by a lender registered with RBI.", "RBI lending-app list"], ["क्या यह असली लेंडर है?", "लोन ऐप किसी RBI-रजिस्टर्ड लेंडर का होना चाहिए।", "RBI लेंडिंग-ऐप सूची"]],
  sebi: [["Is the stock advice licensed?", "Anyone selling stock tips must be registered with SEBI.", "SEBI adviser lists"], ["क्या स्टॉक सलाह लाइसेंस वाली है?", "स्टॉक टिप्स बेचने वाले का SEBI में रजिस्टर्ड होना ज़रूरी है।", "SEBI सलाहकार सूची"]],
  company: [["Is the company real?", "Does its company number belong to it, and how old is its website?", "Company register + website age"], ["क्या कंपनी असली है?", "क्या कंपनी नंबर उसी का है, और वेबसाइट कितनी पुरानी है?", "कंपनी रजिस्टर + वेबसाइट उम्र"]],
  listing: [["What does it promise?", "Guaranteed profits, upfront fees, a different publisher, access to your contacts.", "Its app page or website"], ["यह क्या वादा करता है?", "पक्का मुनाफ़ा, पहले फ़ीस, अलग पब्लिशर, आपके कॉन्टैक्ट्स की माँग।", "उसका ऐप पेज या वेबसाइट"]],
  news: [["Have people complained?", "News reports and complaint forums, counted only if Google really found them.", "News + complaint forums"], ["क्या लोगों ने शिकायत की है?", "खबरें और शिकायत फ़ोरम, तभी गिने जाते हैं जब Google ने सच में ढूँढे हों।", "खबरें + शिकायत फ़ोरम"]]
};
export const TRUST: any = [
  [["Same answer every time", "Fixed rules decide the score. AI only looks things up and writes the summary."], ["हर बार एक ही जवाब", "स्कोर तय नियम तय करते हैं। AI सिर्फ़ जानकारी ढूँढता और सार लिखता है।"]],
  [["Proof for every reason", "Every page and record we used is saved and sealed, so you can show it to your bank."], ["हर कारण का सबूत", "हर पेज और रिकॉर्ड सेव और सील होता है, ताकि आप बैंक को दिखा सकें।"]],
  [["Ready for 1930", "If you already paid, we hand you complaint text you can paste on cybercrime.gov.in."], ["1930 के लिए तैयार", "अगर पैसे भेज दिए, तो cybercrime.gov.in पर पेस्ट करने लायक शिकायत तैयार मिलती है।"]]
];
export const SAMPLES: any = {
  quickrupee: [["Loan app", "Promises Rs. 50,000 in 2 minutes and asks for your contacts."], ["लोन ऐप", "2 मिनट में Rs. 50,000 का वादा, कॉन्टैक्ट्स माँगता है।"]],
  bullvanta: [["Telegram tips", "Says it is SEBI registered and guarantees 300% returns."], ["टेलीग्राम टिप्स", "SEBI रजिस्टर्ड होने का दावा, 300% पक्का मुनाफ़ा।"]],
  hirevexa: [["Internship", "Asks for a Rs. 1,999 “refundable” fee to confirm your seat."], ["इंटर्नशिप", "सीट पक्की करने के लिए Rs. 1,999 की “रिफ़ंडेबल” फ़ीस।"]],
  safekosh: [["Loan app", "Shows its registered lender and every charge upfront."], ["लोन ऐप", "अपना रजिस्टर्ड लेंडर और हर चार्ज पहले दिखाता है।"]]
};
export const TRY: any = ["quickrupee-loans.in", "t.me/bullvantasignals", "hirevexa-careers.in", "safekosh.in"];
export const TODO: any = {
  HIGH_RISK: [["<b>Don't pay</b> and don't share any OTP, UPI PIN or screen.", "<b>Don't install</b> any app or file they send you.", "<b>Block</b> the number or group and tell friends and family."],
              ["<b>पैसे न भेजें</b> और कोई OTP, UPI PIN या स्क्रीन शेयर न करें।", "उनके भेजे किसी ऐप या फ़ाइल को <b>इंस्टॉल न करें</b>।", "नंबर या ग्रुप <b>ब्लॉक करें</b> और परिवार को बताएँ।"]],
  CAUTION: [["<b>Pause.</b> Don't pay until the warning signs are explained.", "<b>Ask for proof</b>: registration numbers you can check yourself.", "<b>Never pay a fee</b> just to get a job, loan or prize."],
            ["<b>रुकिए।</b> ख़तरे के संकेत साफ़ होने तक पैसे न भेजें।", "<b>सबूत माँगें</b>: ऐसे रजिस्ट्रेशन नंबर जो आप खुद जाँच सकें।", "नौकरी, लोन या इनाम के लिए <b>कभी फ़ीस न दें</b>।"]],
  LOW_RISK: [["<b>Pay only inside the official app</b> or website, never to a personal UPI ID.", "<b>Read the charges</b> before you accept a loan or plan.", "<b>Never share</b> your OTP or UPI PIN with anyone."],
             ["<b>सिर्फ़ ऑफ़िशियल ऐप</b> या वेबसाइट में पेमेंट करें, किसी निजी UPI ID पर नहीं।", "लोन या प्लान लेने से पहले <b>चार्ज पढ़ें</b>।", "अपना OTP या UPI PIN <b>किसी से न बताएँ</b>।"]],
  UNKNOWN: [["<b>Don't pay yet.</b> We couldn't reach enough sources.", "<b>Try again</b> in a minute.", "<b>Ask for proof</b> you can check yourself."],
            ["<b>अभी पैसे न भेजें।</b> हम पर्याप्त स्रोतों तक नहीं पहुँच पाए।", "थोड़ी देर बाद <b>फिर कोशिश करें</b>।", "ऐसा <b>सबूत माँगें</b> जो आप खुद जाँच सकें।"]]
};
export const PAID: any = [["<b>Call 1930</b> as fast as you can. The first hours matter most.", "<b>Report it</b> on cybercrime.gov.in. Our complaint text is ready to paste.", "<b>Keep the proof</b> PDF and your payment receipt or UTR number."],
            ["जितनी जल्दी हो सके <b>1930 पर कॉल करें</b>। पहले कुछ घंटे सबसे ज़रूरी हैं।", "cybercrime.gov.in पर <b>रिपोर्ट करें</b>। हमारी शिकायत तैयार है।", "<b>सबूत PDF</b> और पेमेंट की रसीद या UTR नंबर संभाल कर रखें।"]];

export const ICONS: any = {
  rbi: '<path d="M4 10 16 4l12 6M6 12v10M11 12v10M16 12v10M21 12v10M26 12v10M3 25h26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  sebi: '<path d="M4 25h24M6 20l6-6 5 4 9-10M21 8h5v5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  company: '<rect x="5" y="7" width="22" height="18" rx="3" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="15" r="3" fill="none" stroke="currentColor" stroke-width="2"/><path d="M18 13h5M18 18h5M8 22c1-2 7-2 8 0" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  listing: '<rect x="9" y="3" width="14" height="26" rx="3" fill="none" stroke="currentColor" stroke-width="2"/><path d="M14 25h4M13 9h6M13 13h6M13 17h3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  news: '<path d="M5 8h22v13H14l-6 5v-5H5z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M10 13h12M10 17h8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
};
export const MARK: any = {
  x: '<path d="M10 10l12 12M22 10 10 22" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>',
  "!": '<path d="M16 8v10M16 23v1" stroke="currentColor" stroke-width="3.2" stroke-linecap="round"/>',
  ok: '<path d="M8 17l5 5 11-12" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>',
  q: '<path d="M12 12a4 4 0 1 1 6 3.4c-1.2.7-2 1.6-2 2.8M16 23v1" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round"/>',
  dash: '<path d="M10 16h12" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>'
};

export const L = (lang: Lang) => (lang === "hi" ? 1 : 0);
export const t = (k: string, lang: Lang): string => S[k][L(lang)];

// Wording that differs in the real app (the preview has no server).
Object.assign(S, {
  noteLive: ["Live: each check runs now on Gemini with Google Search, usually in under a minute.", "लाइव: हर जाँच अभी Gemini और Google Search से चलती है, आमतौर पर एक मिनट से कम में।"],
  noteDemo: ["Only the four sample cases run right now. Add GEMINI_API_KEY to backend/.env and restart the API for live checks.", "अभी सिर्फ़ चार सैंपल केस चलते हैं। लाइव जाँच के लिए backend/.env में GEMINI_API_KEY डालें और API फिर से चालू करें।"],
  modeLive: ["Live · Gemini", "लाइव · Gemini"],
  modeDemo: ["Demo only · add key", "सिर्फ़ डेमो · key जोड़ें"],
  modeOff: ["API offline", "API बंद"],
  offline: ["Can't reach the API. Start the backend on port 8000, then try again.", "API से जुड़ नहीं पाए। पोर्ट 8000 पर बैकएंड चालू करें, फिर कोशिश करें।"],
  proofDl: ["Download proof (PDF)", "सबूत डाउनलोड करें (PDF)"],
  cached: ["Saved result, under 24 h old", "सेव किया नतीजा, 24 घंटे के अंदर"],
  partial: ["Some sources could not be checked and gave no points.", "कुछ स्रोतों की जाँच नहीं हो पाई, उनसे अंक नहीं कटे।"],
  recent: ["Recent checks", "हाल की जाँचें"],
  scoreBreakdown: ["Score Breakdown", "स्कोर विवरण"],
  scoreBreakdownSub: ["All 7 signals checked with evidence & points", "सभी 7 संकेतों की जाँच सबूत और अंकों के साथ"],
  confidence: ["Confidence", "विश्वसनीयता"],
  confHigh: ["HIGH", "उच्च"],
  confMed: ["MEDIUM", "मध्यम"],
  confLow: ["LOW", "कम"],
  statusPass: ["PASS", "पास"],
  statusWarn: ["WARNING", "चेतावनी"],
  statusFail: ["FAIL", "विफल"],
  statusUnknown: ["UNVERIFIED", "अपुष्ट"],
  humanAssistTitle: ["Help Us Verify This Page", "इस पेज को जाँचने में मदद करें"],
  humanAssistSub: ["We couldn't open this link directly due to bot protection or security wall. Provide what you see to run an evidence-based check.", "सुरक्षा या बॉट सुरक्षा के कारण हम यह लिंक सीधे नहीं खोल पाए। सबूत आधारित जाँच के लिए जो दिख रहा है वह दर्ज करें।"],
  humanAssistUrl: ["Full URL from your address bar", "एड्रेस बार से पूरा URL"],
  humanAssistText: ["Paste page text or message received", "पेज का टेक्स्ट या मिला हुआ संदेश यहाँ पेस्ट करें"],
  humanAssistQ1: ["How did you receive this link?", "आपको यह लिंक कैसे मिला?"] ,
  humanAssistQ2: ["Are they asking for payment, fee or OTP?", "क्या वे पैसे, फ़ीस या OTP माँग रहे हैं?"],
  humanAssistQ3: ["What returns or rewards do they promise?", "वे क्या मुनाफ़ा या इनाम का वादा कर रहे हैं?"],
  humanAssistSubmit: ["Submit for Verification", "जाँच के लिए सबमिट करें"],
  humanAssistBadge: ["Based on user-provided evidence", "उपयोगकर्ता द्वारा दिए गए सबूत पर आधारित"],
  disputeBtn: ["Think this verdict is wrong?", "क्या यह नतीजा ग़लत लगता है?"],
  disputeTitle: ["Dispute this verdict", "इस नतीजे पर आपत्ति दर्ज करें"],
  disputeSub: ["Tell us why you think this check is inaccurate. Evidence is re-evaluated.", "बताएँ कि यह नतीजा क्यों ग़लत लगता है। सबूतों की दोबारा समीक्षा की जाएगी।"],
  disputeReason: ["Select reason", "कारण चुनें"],
  disputeReason1: ["Official bank or government website", "ऑफ़िशियल बैंक या सरकारी वेबसाइट है"],
  disputeReason2: ["Legitimate business / service", "वैध व्यवसाय या सेवा है"],
  disputeReason3: ["Active scam that was not caught", "सक्रिय स्कैम है जो पकड़ा नहीं गया"],
  disputeReason4: ["Other issue", "अन्य कारण"],
  disputeComment: ["Additional details (optional)", "अतिरिक्त विवरण (वैकल्पिक)"],
  disputeSubmit: ["Submit Report", "रिपोर्ट सबमिट करें"],
  disputeThanks: ["Report submitted. Thank you for keeping India safe.", "रिपोर्ट दर्ज की गई। भारत को सुरक्षित रखने में मदद के लिए धन्यवाद।"],
  batchTabSingle: ["Single Check", "एकल जाँच"],
  batchTabMulti: ["Batch Check (Multi-URL)", "बैच जाँच (एक साथ कई लिंक)"],
  batchTitle: ["Batch URL Verification", "बैच URL सत्यापन"],
  batchLead: ["Paste multiple URLs, domains or apps (one per line) to verify them all at once.", "एक साथ कई URL, डोमेन या ऐप (प्रति पंक्ति एक) पेस्ट करें।"],
  batchPlaceholder: ["https://sbi.bank.in\nhttps://sbi-rewards-claim.in\nhttps://groww.in\n...", "https://sbi.bank.in\nhttps://sbi-rewards-claim.in\nhttps://groww.in\n..."],
  batchStart: ["Start Batch Check", "बैच जाँच शुरू करें"],
  batchProgress: ["Verifying links...", "लिंक जाँचे जा रहे हैं..."],
  batchDlCsv: ["Export CSV", "CSV डाउनलोड"],
  batchDlPdf: ["Download Batch PDF", "बैच PDF डाउनलोड"],
  batchRetry: ["Retry Failed", "विफल लिंक दोबारा जाँचें"],
  filterAll: ["All", "सभी"],
  filterSafe: ["Safe", "सुरक्षित"],
  filterSuspicious: ["Suspicious", "संदिग्ध"],
  filterHighRisk: ["High Risk", "उच्च जोखिम"],
});
