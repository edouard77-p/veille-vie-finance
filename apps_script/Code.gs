/**
 * ===========================================================================
 *  VOIE RAPIDE V.I.E FINANCE — Google Apps Script (gratuit, compte Google)
 * ===========================================================================
 *  - Scanne Business France toutes les 2 min en heures ouvrées (10 min sinon)
 *    et t'envoie sur Telegram chaque NOUVELLE offre V.I.E en finance.
 *  - Relaie sur Telegram tes alertes e-mail (LinkedIn, Indeed, Google Alerts…)
 *    rangées par un filtre Gmail sous le libellé « vie-alertes ».
 *  - Surveille le script GitHub et te prévient s'il s'arrête.
 *
 *  Installation (détaillée dans le README) :
 *   1. Paramètres du projet > Propriétés du script : TELEGRAM_TOKEN,
 *      (facultatif) KEYWORDS_URL et GITHUB_STATUS_URL.
 *   2. Exécuter trouverChatId()  -> enregistre TELEGRAM_CHAT_ID.
 *   3. Exécuter installer()      -> crée le déclencheur et envoie un message.
 *   4. Exécuter testerAlertes()  -> fausse offre + e-mail de secours.
 *  Fonctions utiles ensuite : diagnostic(), desinstaller(), reinitialiser().
 * ===========================================================================
 */

// ----------------------------- RÉGLAGES ------------------------------------
var REGLAGES = {
  minutesHeuresOuvrees: 2,      // 1 possible, mais double la charge sur Business France
  minutesHorsHeures: 10,
  heuresOuvrees: [7, 21],       // heure de Paris : de 7h à 21h
  joursOuvres: [1, 2, 3, 4, 5], // 1 = lundi … 7 = dimanche
  inclureVIA: false,            // true pour recevoir aussi les V.I.A
  maxMessagesParScan: 25,       // au-delà : un message récapitulatif
  gmailToutesLesMinutes: 5,
  gmailRequete: 'label:vie-alertes -label:vie-relaye newer_than:3d',
  surveillanceGithubMinutes: 30,
  githubEnPanneApresMinutes: 90, // GitHub Actions peut prendre 30 min de retard
  alerteApresEchecs: 3,
  budgetQuotidienMinutes: 75     // Google : 90 min/jour max pour les déclencheurs (compte gratuit)
};

var SITE = 'https://mon-vie-via.businessfrance.fr';
var API_URL = 'https://civiweb-api-prd.azurewebsites.net/api/Offers/search';
// Clé publique envoyée à tous les navigateurs par le site ; relue sur la page d'accueil toutes les 6 h.
var FALLBACK_API_KEY = 'l+KwpoLPiXlsjxNT/NQ2iOFz8+iuygxAODs9FeAEWYM=';
var PAGE_SIZE = 100;
var TZ = 'Europe/Paris';

// Copie de config/keywords.json (utilisée si KEYWORDS_URL est vide ou injoignable).
// Synchronisée automatiquement par tools/sync_keywords.py — ne pas éditer à la main.
// <KEYWORDS>
var DEFAULT_KEYWORDS = {
  "domaines": {
    "Marchés financiers": ["sales (&|and|et) trading", "s ?& ?t", "global markets?", "capital markets?", "debt capital markets?", "equity capital markets?", "dcm", "ecm", "marches? (de capitaux|financiers?)", "trad(er|ers|ing)", "structur(ing|eur|euse|eurs|ation)", "structured products?", "produits? structures?", "produits? derives", "derivatives?", "equity derivatives?", "fixed income", "rates", "forex", "fx", "commodit(y|ies)", "matieres premieres", "front office", "middle office", "back office", "securities", "prime brokerage", "brokerage", "broker", "recherche (economique|financiere|actions|credit)", "economist(e|es)?", "strategist(e|es)?"],
    "Banque & financement": ["corporate banking", "investment banking", "transaction banking", "private banking", "retail banking", "banque (d investissement|de financement|privee|de detail|commerciale)", "bank(ing|er|ers)?", "banqu(e|es|ier|iere|iers|ieres)", "financements?( structures?| de projets?)?", "financing", "structured finance", "project finance", "trade finance", "export finance", "leveraged finance", "acquisition finance", "real estate finance", "asset finance", "syndicat(ion|ions)", "loans?", "lending", "relationship manager", "wealth management", "gestion de patrimoine", "conseill(er|ere) patrimonial", "affacturage", "factoring", "credit bail", "leasing"],
    "Analyse & investissement": ["equity research", "analyste? credit", "credit analy[a-z]*", "asset management", "asset managers?", "gestion d actifs", "gerant(e)?", "portfolio", "portefeuilles?", "funds?", "fonds", "private equity", "capital investissement", "venture capital", "growth equity", "investissements?", "invest(ment|ments)", "m ?& ?a", "mergers?", "fusions?( (et )?acquisitions?)?", "corporate development", "valuations?", "evaluation financiere", "transaction services", "deal advisory", "due diligence", "financial advisory", "ratings? analysts?", "notation financiere"],
    "Audit, risques & conformité": ["audit(eur|euse|eurs|euses|or|ors|ing)?", "internal control", "controle (interne|permanent|periodique)", "risks?", "risques?", "compliance", "conformite", "kyc", "aml", "lcb ?ft", "anti money laundering", "financial crime", "fraud", "fraude", "regulatory reporting", "reporting reglementaire", "prudenti(al|el)", "solvency", "solvabilite", "model validation", "backtesting", "stress tests?", "sox", "ifrs", "us gaap", "gaap", "commissaire aux comptes"],
    "Fintech & quant": ["fintech", "insurtech", "regtech", "quant", "quants", "quantitati(ve|f|ve analyst)", "actuar[a-z]*", "payments?", "paiements?", "crypto (actifs|assets)", "digital assets", "actifs numeriques", "financial engineer[a-z]*", "ingenieri(e|eur) financier(e)?"],
    "Finance internationale": ["(finance|financial|financier|financiere) (international|internationale|regional|regionale|zone|region|apac|emea|latam|amerique|asie|afrique|filiale|filiales)", "(international|internationale|regional|regionale|zone|filiale|subsidiary|country) (finance|financial|controll?er|controlling|treasurer|tresorier|cfo)", "finance de filiales?"],
    "Finance d'entreprise": ["corporate finance", "fp ?& ?a", "fpa", "financial planning", "control(e|eur|euse|eurs|euses) de gestion", "controll?ers?", "controlling", "cost controll?er", "business controll?er", "controleu(r|se|rs|ses) (financi(er|ere)|budgetaire|credit)", "financial analy[a-z]*", "analystes? financi(er|ere)s?", "tresor(erie|ier|iere|iers)", "treasur(y|er|ers)", "cash management", "cash manager", "reporting financier", "financial reporting", "consolidation", "comptab[a-z]*", "accounting", "accountants?", "accounts (payable|receivable)", "credit manag(er|ement)", "credit controll?er", "recouvrement", "budget(aire|s)?", "fiscal(ite)?", "tax(es)?", "transfer pricing", "prix de transfert", "investor relations", "relations? investisseurs?", "pricing analysts?", "billing", "facturation", "cfo", "chief financial officer", "daf", "raf"]
  },
  "generique": ["financ(e|es|ial|ials|ier|iere|iers|ieres|iero|iera|eiro|eira)", "finanz[a-z]*"],
  "veto_titre": ["talent acquisition", "acquisition de talents", "customer acquisition", "user acquisition", "quantity surveyors?", "metreu(r|se)", "audit(eur|euse|or|ing)? (qualite|quality|hse|ehs|securite|security|energetique|energy|environnement|environmental|fournisseurs?|suppliers?|process|produits?|products?)", "(quality|qualite|hse|ehs|supplier|fournisseurs?|energy|energetique|environmental|safety) audit(eur|euse|or|ors|ing|s)?", "assurance qualite", "quality assurance", "risks? (hse|ehs|safety)", "(hse|ehs|safety) risks?", "risques? (hse|professionnels|industriels|chimiques|psychosociaux)", "fund ?raising (event|evenementiel)", "sales engineers?", "ingenieu(r|re)s? (commercia(l|le|ux)|d affaires)", "business develop(er|ers|ment manager|ment representative)"],
  "exclusions_si_description_seule": ["business develop[a-z]*", "developpement (commercial|des ventes|business|international|territorial|produit)", "commercia(l|le|les|ux)", "sales", "ventes?", "marketing", "communication", "achats?", "acheteu(r|se)", "purchas[a-z]*", "procurement", "sourcing", "supply chain", "logisti[a-z]*", "ingenieu(r|re|rs)", "engineer(s|ing)?", "developpeu(r|se)", "developer", "software", "logiciels?", "data engineer", "devops", "cloud", "it", "informatique", "reseaux", "rh", "ressources humaines", "human resources", "hr", "recrut[a-z]*", "talent", "qualite", "quality", "production", "maintenance", "technici(en|enne|an)", "designer", "design", "product (manager|owner)", "customer (success|service)", "service client"],
  "seuil_description": 3,
  "vie_texte_libre": ["volontariat international", "international volunteer", "volontaire international", "vie contract", "contrat vie", "v i e"]
};
// </KEYWORDS>

// =========================== FONCTIONS À LANCER ============================

function installer() {
  var p = props_();
  if (!p.getProperty('TELEGRAM_TOKEN')) throw new Error('Ajoute d\'abord TELEGRAM_TOKEN dans Paramètres du projet > Propriétés du script.');
  if (!p.getProperty('TELEGRAM_CHAT_ID')) throw new Error('Lance d\'abord trouverChatId() (après avoir envoyé /start à ton bot).');
  if (!p.getProperty('STATUS_TOKEN')) p.setProperty('STATUS_TOKEN', Utilities.getUuid().replace(/-/g, ''));
  desinstaller();
  ScriptApp.newTrigger('tick').timeBased().everyMinutes(1).create();
  var res = scanBusinessFrance_({ force: true });
  tg_('✅ <b>Voie rapide installée</b>\n' + esc_(res.message) +
      '\nScan Business France toutes les ' + REGLAGES.minutesHeuresOuvrees + ' min en heures ouvrées, ' +
      REGLAGES.minutesHorsHeures + ' min sinon.');
  Logger.log('Installé. ' + res.message);
  Logger.log('STATUS_TOKEN (à copier dans le secret GitHub FASTLANE_TOKEN) : ' + p.getProperty('STATUS_TOKEN'));
}

function trouverChatId() {
  var token = props_().getProperty('TELEGRAM_TOKEN');
  if (!token) throw new Error('Ajoute d\'abord TELEGRAM_TOKEN dans les propriétés du script.');
  var r = JSON.parse(UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/getUpdates', { muteHttpExceptions: true }).getContentText());
  var chats = {};
  (r.result || []).forEach(function (u) {
    var m = u.message || u.channel_post;
    if (m && m.chat) chats[m.chat.id] = m.chat.first_name || m.chat.title || '';
  });
  var ids = Object.keys(chats);
  if (!ids.length) throw new Error('Aucun message trouvé : ouvre ton bot dans Telegram, envoie /start, puis relance.');
  props_().setProperty('TELEGRAM_CHAT_ID', ids[0]);
  Logger.log('TELEGRAM_CHAT_ID enregistré : ' + ids[0] + ' (' + chats[ids[0]] + ')' + (ids.length > 1 ? ' — autres : ' + ids.slice(1).join(', ') : ''));
}

function testerAlertes() {
  var ok = notifyOffer_({
    id: 'test', title: '[TEST] V.I.E – Treasury Analyst (H/F)', company: 'Entreprise Exemple', city: 'Singapour',
    country: 'Singapour', published: '2026-10-26', start: '2027-01-01', duration: '12 mois', salary: '3 200 €/mois',
    description: 'Message de test : si tu le lis sur ton téléphone, la voie rapide fonctionne.',
    url: SITE + '/offres/recherche', domain: "Finance d'entreprise", basis: 'titre'
  });
  mail_('[V.I.E finance] Test du secours e-mail', 'Si tu lis cet e-mail, le secours par e-mail de la voie rapide fonctionne.');
  Logger.log('Telegram : ' + (ok ? 'OK' : 'ÉCHEC') + ' — e-mail de test envoyé à ' + Session.getEffectiveUser().getEmail());
}

function diagnostic() {
  var kw = keywords_();
  var data = fetchAllBF_();
  var clf = new Classifier_(kw);
  var finance = data.offers.map(toOffer_).filter(function (o) { return evaluate_(o, clf); });
  var lines = ['🩺 <b>Diagnostic voie rapide</b>',
    'Business France : ' + data.offers.length + ' offres (annoncées : ' + data.count + '), dont ' + finance.length + ' V.I.E finance',
    'Mots-clés : ' + (props_().getProperty('KEYWORDS_URL') ? 'lus depuis GitHub' : 'copie intégrée'),
    'Budget Apps Script utilisé aujourd\'hui : ' + Math.round(runtimeToday_() / 60000) + ' / ' + REGLAGES.budgetQuotidienMinutes + ' min',
    'Dernier scan réussi : ' + (props_().getProperty('bf_last_ok_iso') || 'jamais')];
  finance.slice(0, 5).forEach(function (o) { lines.push('↳ ' + esc_(o.title) + ' · ' + esc_(o.domain)); });
  tg_(lines.join('\n'));
  Logger.log(lines.join('\n').replace(/<[^>]+>/g, ''));
}

function desinstaller() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'tick') ScriptApp.deleteTrigger(t);
  });
}

function reinitialiser() {
  var p = props_(), keep = { TELEGRAM_TOKEN: 1, TELEGRAM_CHAT_ID: 1, STATUS_TOKEN: 1, KEYWORDS_URL: 1, GITHUB_STATUS_URL: 1 };
  Object.keys(p.getProperties()).forEach(function (k) { if (!keep[k]) p.deleteProperty(k); });
  Logger.log('État effacé : le prochain scan repartira de zéro (sans renvoyer les offres déjà en ligne).');
}

// ============================ DÉCLENCHEUR ==================================

function tick() {
  var t0 = Date.now();
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) return;           // un passage est déjà en cours
  try {
    var now = paris_(new Date());
    var p = props_();
    var budgetHit = runtimeToday_() > REGLAGES.budgetQuotidienMinutes * 60000;
    var business = REGLAGES.joursOuvres.indexOf(now.dow) >= 0 && now.hour >= REGLAGES.heuresOuvrees[0] && now.hour < REGLAGES.heuresOuvrees[1];
    var every = business ? REGLAGES.minutesHeuresOuvrees : REGLAGES.minutesHorsHeures;
    if (budgetHit) {
      every = Math.max(every, 10);
      if (p.getProperty('budget_warned') !== now.date) {
        p.setProperty('budget_warned', now.date);
        tg_('⏳ Budget quotidien Apps Script presque atteint : scans espacés à ' + every + ' min jusqu\'à demain.');
      }
    }
    if (due_('bf_last_try_ms', every)) scanBusinessFrance_({});
    if (due_('gmail_last_ms', REGLAGES.gmailToutesLesMinutes)) safe_(relayGmail_);
    if (due_('gh_last_ms', REGLAGES.surveillanceGithubMinutes)) safe_(watchGithub_);
  } finally {
    addRuntime_(Date.now() - t0);
    lock.releaseLock();
  }
}

/** Point d'accès lu par le script GitHub (Déployer > Application Web). */
function doGet(e) {
  var p = props_();
  var token = p.getProperty('STATUS_TOKEN');
  var out;
  if (!token || !e || !e.parameter || e.parameter.token !== token) {
    out = { ok: false, error: 'token invalide' };
  } else {
    out = {
      ok: true, lastTry: new Date(Number(p.getProperty('bf_last_try_ms') || 0)).toISOString(), lastBfScan: p.getProperty('bf_last_ok_iso') || '',
      bfOk: (p.getProperty('bf_fail') || '0') === '0', sentIds: getSet_('sent')
    };
  }
  return ContentService.createTextOutput(JSON.stringify(out)).setMimeType(ContentService.MimeType.JSON);
}

// ========================== BUSINESS FRANCE ================================

function scanBusinessFrance_(opts) {
  var p = props_();
  try {
    var data = fetchAllBF_();
    var clf = new Classifier_(keywords_());
    var seen = setOf_(getSet_('seen')), sent = setOf_(getSet_('sent'));
    var firstRun = !p.getProperty('bf_init');
    var fresh = [], currentIds = {};
    data.offers.forEach(function (raw) {
      var id = String(raw.id);
      currentIds[id] = true;
      if (seen[id]) return;
      var o = toOffer_(raw);
      if (evaluate_(o, clf)) fresh.push(o);
    });
    fresh.sort(function (a, b) { return Number(b.id) - Number(a.id) || 0; });

    var failed = {}, message;
    if (firstRun) {
      fresh.forEach(function (o) { sent[o.id] = true; });
      p.setProperty('bf_init', '1');
      message = 'Initialisation : ' + fresh.length + ' offres V.I.E finance déjà en ligne (le script GitHub t\'envoie la liste). Les nouvelles arriveront ici.';
    } else {
      var head = fresh.slice(0, REGLAGES.maxMessagesParScan), rest = fresh.slice(REGLAGES.maxMessagesParScan);
      head.forEach(function (o) { if (notifyOffer_(o)) sent[o.id] = true; else failed[o.id] = true; });
      if (rest.length) {
        var lines = ['➕ <b>' + rest.length + ' autres nouvelles offres V.I.E finance</b>'];
        rest.forEach(function (o) { lines.push(line_(o)); });
        if (sendLong_(lines)) rest.forEach(function (o) { sent[o.id] = true; });
        else rest.forEach(function (o) { failed[o.id] = true; });
      }
      message = fresh.length + ' nouvelle(s) offre(s) finance.';
    }

    // État : on garde ce qui est en ligne (si la liste est complète), sauf les envois ratés.
    var newSeen = data.complete ? currentIds : merge_(seen, currentIds);
    Object.keys(failed).forEach(function (id) { delete newSeen[id]; });
    var newSent = {};
    Object.keys(sent).forEach(function (id) { if (!data.complete || currentIds[id]) newSent[id] = true; });
    putSet_('seen', Object.keys(newSeen));
    putSet_('sent', Object.keys(newSent));

    p.setProperty('bf_last_ok_iso', new Date().toISOString());
    if (p.getProperty('bf_alerted') === '1') tg_('✅ Business France (voie rapide) rétabli.');
    p.setProperties({ bf_fail: '0', bf_alerted: '0', bf_last_error: '' });
    return { ok: true, message: data.offers.length + ' offres lues. ' + message };
  } catch (err) {
    var n = Number(p.getProperty('bf_fail') || 0) + 1;
    var msg = String(err && err.message || err).replace(/bot\d+:[\w-]+/g, 'bot***');
    p.setProperties({ bf_fail: String(n), bf_last_error: msg.slice(0, 300) });
    if (n >= REGLAGES.alerteApresEchecs && p.getProperty('bf_alerted') !== '1') {
      var text = '⚠️ <b>Voie rapide : Business France en échec</b> (' + n + ' fois de suite)\n<code>' + esc_(msg.slice(0, 300)) + '</code>';
      if (!tg_(text)) mail_('[V.I.E finance] Voie rapide en échec', text);
      p.setProperty('bf_alerted', '1');
    }
    if (opts && opts.force) throw err;
    return { ok: false, message: msg };
  }
}

function apiKey_(refresh) {
  var p = props_();
  var age = Date.now() - Number(p.getProperty('api_key_at') || 0);
  if (!refresh && p.getProperty('api_key') && age < 6 * 3600000) return p.getProperty('api_key');
  var key = FALLBACK_API_KEY;
  try {
    var html = UrlFetchApp.fetch(SITE + '/', { muteHttpExceptions: true }).getContentText();
    var m = html.match(/[,{]API_KEY:"([^"]+)"/);
    if (m) key = JSON.parse('"' + m[1] + '"');
  } catch (e) { /* page injoignable : clé de secours */ }
  p.setProperties({ api_key: key, api_key_at: String(Date.now()) });
  return key;
}

function bfRequest_(skip, key) {
  return {
    url: API_URL, method: 'post', contentType: 'application/json', muteHttpExceptions: true,
    headers: { 'X-API-KEY': key, 'Accept': 'application/json' },
    payload: JSON.stringify({ skip: skip, limit: PAGE_SIZE, sort: 0 })
  };
}

/** Lit toutes les pages en parallèle (UrlFetchApp.fetchAll). */
function fetchAllBF_() {
  var p = props_();
  var expected = Math.max(1, Math.ceil(Number(p.getProperty('bf_count') || 0) / PAGE_SIZE) + 1);
  for (var attempt = 0; attempt < 2; attempt++) {
    var key = apiKey_(attempt === 1);
    var reqs = [];
    for (var i = 0; i < expected; i++) reqs.push(bfRequest_(i * PAGE_SIZE, key));
    var resps = UrlFetchApp.fetchAll(reqs);
    if (resps.some(function (r) { return r.getResponseCode() === 401; }) && attempt === 0) continue;
    var byId = {}, count = 0, lastLen = PAGE_SIZE, page = expected;
    var absorb = function (r) {
      if (r.getResponseCode() !== 200) throw new Error('API Business France : HTTP ' + r.getResponseCode() + ' ' + r.getContentText().slice(0, 150));
      var d = JSON.parse(r.getContentText());
      var batch = Array.isArray(d) ? d : (d.result || d.results);
      if (!Array.isArray(batch)) throw new Error('API Business France : format inattendu');
      if (d.count) count = d.count;
      batch.forEach(function (o) { if (o.id !== undefined && o.id !== null) byId[String(o.id)] = o; });
      return batch.length;
    };
    resps.forEach(function (r) { lastLen = absorb(r); });
    while (lastLen === PAGE_SIZE && page < 30) {            // il y a plus d'offres que prévu
      lastLen = absorb(UrlFetchApp.fetch(API_URL, bfRequest_(page * PAGE_SIZE, key)));
      page++;
    }
    var offers = Object.keys(byId).map(function (k) { return byId[k]; });
    if (!offers.length) throw new Error('API Business France : 0 offre renvoyée');
    p.setProperty('bf_count', String(count || offers.length));
    return { offers: offers, count: count, complete: !count || offers.length >= count * 0.98 };
  }
  throw new Error('API Business France : clé refusée (401)');
}

function first_(raw, names) {
  for (var i = 0; i < names.length; i++) {
    var v = raw[names[i]];
    if (v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && !v.length)) return v;
  }
  return '';
}

function strings_(v) {
  if (typeof v === 'string') return [v];
  if (Array.isArray(v)) return [].concat.apply([], v.map(strings_));
  if (v && typeof v === 'object') return [].concat.apply([], Object.keys(v).map(function (k) { return strings_(v[k]); }));
  return [];
}

function title_(s) {
  return String(s || '').toLowerCase().replace(/(^|[\s\-'])([a-zà-ÿ])/g, function (m, a, b) { return a + b.toUpperCase(); });
}

function toOffer_(raw) {
  var tags = [];
  Object.keys(raw).forEach(function (k) {
    if (/special|sector|secteur|metier|activit|domain|categor|fonction|function|job/i.test(k)) tags = tags.concat(strings_(raw[k]));
  });
  var salary = first_(raw, ['indemnite', 'indemnity']);
  var duration = first_(raw, ['missionDuration', 'duration']);
  var type = first_(raw, ['missionType', 'missionTypeName', 'typeMission']);
  return {
    id: String(raw.id),
    title: String(first_(raw, ['missionTitle', 'title']) || '(sans titre)').trim(),
    company: String(first_(raw, ['organizationName', 'companyName'])).trim(),
    city: title_(first_(raw, ['cityName', 'city'])), country: title_(first_(raw, ['countryName', 'country'])),
    published: String(first_(raw, ['startBroadcastDate', 'creationDate'])).slice(0, 10),
    start: String(first_(raw, ['missionStartDate'])).slice(0, 10),
    deadline: String(first_(raw, ['endBroadcastDate'])).slice(0, 10),
    duration: /^\d+$/.test(String(duration)) ? duration + ' mois' : String(duration),
    salary: salary && !isNaN(Number(salary)) ? Math.round(Number(salary)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ' €/mois' : String(salary || ''),
    description: stripHtml_(String(first_(raw, ['missionDescription'])) + ' ' + String(first_(raw, ['missionProfile']))),
    tags: tags.join(' '),
    type: strings_(type).join(' ').toUpperCase() || String(type).toUpperCase(),
    url: SITE + '/offres/' + raw.id
  };
}

function evaluate_(o, clf) {
  if (o.type.indexOf('VIA') >= 0 && o.type.indexOf('VIE') < 0 && !REGLAGES.inclureVIA) return false;
  var v = clf.classify(o.title, o.description, o.tags);
  if (!v.isFinance) return false;
  o.domain = v.domain; o.basis = v.basis;
  return true;
}

// ============================ CLASSIFIEUR ==================================
// Même logique que vie_alert/classify.py (vérifié par les tests).

var GENERIC_DOMAIN = "Finance d'entreprise";

function normalize_(s) {
  s = String(s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9&]+/g, ' ').trim();
  return ' ' + s + ' ';
}

function compile_(pats) {
  if (!pats || !pats.length) return null;
  return new RegExp('(?<![a-z0-9])(?:' + pats.map(function (p) { return '(?:' + p + ')'; }).join('|') + ')(?![a-z0-9])');
}

var VIE_UPPER = /(?<![A-Za-z])V\.? ?I\.? ?E\.?(?![A-Za-z])/;

function Classifier_(kw) {
  var self = this;
  this.order = Object.keys(kw.domaines);
  this.domains = this.order.map(function (name) { return kw.domaines[name].map(function (p) { return compile_([p]); }); });
  this.generic = (kw.generique || []).map(function (p) { return compile_([p]); });
  this.veto = compile_(kw.veto_titre || []);
  this.descExcl = compile_(kw.exclusions_si_description_seule || []);
  this.threshold = Number(kw.seuil_description || 3);
  this.vieFree = compile_(kw.vie_texte_libre || []);

  this.hits = function (text) {
    var per = {}, generic = [];
    self.order.forEach(function (name, i) {
      var found = [];
      self.domains[i].forEach(function (r) { var m = text.match(r); if (m) found.push(m[0].trim()); });
      if (found.length) per[name] = found;
    });
    self.generic.forEach(function (r) { var m = text.match(r); if (m) generic.push(m[0].trim()); });
    return { per: per, generic: generic };
  };

  this.best = function (per) {
    var best = null, n = 0;
    self.order.forEach(function (name) { if (per[name] && per[name].length > n) { best = name; n = per[name].length; } });
    return best;
  };

  this.classify = function (title, description, tags) {
    var t = normalize_(title), m;
    if (self.veto && (m = t.match(self.veto))) return { isFinance: false, reason: 'veto titre : ' + m[0].trim() };
    var labels = [['titre', t], ['catégorie', normalize_(tags)]];
    for (var i = 0; i < labels.length; i++) {
      var h = self.hits(labels[i][1]);
      if (Object.keys(h.per).length) return { isFinance: true, domain: self.best(h.per), basis: labels[i][0] };
      if (h.generic.length) return { isFinance: true, domain: GENERIC_DOMAIN, basis: labels[i][0] };
    }
    if (self.descExcl && (m = t.match(self.descExcl))) return { isFinance: false, reason: 'titre hors finance : ' + m[0].trim() };
    var d = self.hits(normalize_(description)), distinct = {};
    Object.keys(d.per).forEach(function (k) { d.per[k].forEach(function (x) { distinct[x] = 1; }); });
    if (d.generic.length) distinct[d.generic[0]] = 1;
    if (Object.keys(distinct).length >= self.threshold) {
      return { isFinance: true, domain: self.best(d.per) || GENERIC_DOMAIN, basis: 'description' };
    }
    return { isFinance: false, reason: Object.keys(distinct).length + ' terme(s) finance dans la description' };
  };

  this.looksVie = function () {
    for (var i = 0; i < arguments.length; i++) {
      var s = arguments[i];
      if (!s) continue;
      if (VIE_UPPER.test(s)) return true;
      if (self.vieFree && self.vieFree.test(normalize_(s))) return true;
    }
    return false;
  };
}

function keywords_() {
  var url = props_().getProperty('KEYWORDS_URL');
  if (!url) return DEFAULT_KEYWORDS;
  var cache = CacheService.getScriptCache();
  var cached = cache.get('kw');
  if (cached) return JSON.parse(cached);
  try {
    var r = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    if (r.getResponseCode() === 200) {
      var kw = JSON.parse(r.getContentText());
      if (kw.domaines) { cache.put('kw', JSON.stringify(kw), 3600); return kw; }
    }
  } catch (e) { /* GitHub injoignable : copie intégrée */ }
  return DEFAULT_KEYWORDS;
}

// ============================ GMAIL → TELEGRAM =============================

function relayGmail_() {
  var threads = GmailApp.search(REGLAGES.gmailRequete, 0, 15);
  if (!threads.length) return;
  var done = GmailApp.getUserLabelByName('vie-relaye') || GmailApp.createLabel('vie-relaye');
  threads.forEach(function (t) {
    var msgs = t.getMessages(), m = msgs[msgs.length - 1];
    var links = extractLinks_(m.getBody()).slice(0, 10);
    var lines = ['📧 <b>' + esc_(m.getSubject()) + '</b>', 'De : ' + esc_(m.getFrom())];
    links.forEach(function (l) { lines.push('• <a href="' + esc_(l.url) + '">' + esc_(l.text) + '</a>'); });
    if (!links.length) lines.push('<i>' + esc_(m.getPlainBody().slice(0, 600)) + '</i>');
    lines.push('<a href="https://mail.google.com/mail/u/0/#all/' + t.getId() + '">Ouvrir dans Gmail</a>');
    if (sendLong_(lines)) t.addLabel(done);
  });
}

function extractLinks_(html) {
  var re = /<a\b[^>]*?href\s*=\s*["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi, out = [], seen = {}, m;
  var skip = /d[ée]sabonn|unsubscribe|param[eè]tres|settings|pr[ée]f[ée]rences|preferences|privacy|confidentialit|politique de|conditions d|mentions l[ée]gales|centre d.aide|help cent|voir tou|see all|view all|g[ée]rer (mes|les|vos|l)|manage (your |job )?alert|app store|google play|t[ée]l[ée]charge/i;
  while ((m = re.exec(html)) !== null) {
    var url = decodeEntities_(m[1]), text = stripHtml_(m[2]);
    if (!/^https?:/i.test(url) || text.length < 12 || skip.test(text)) continue;
    var g = url.match(/^https?:\/\/(?:www\.)?google\.[a-z.]+\/url\?(?:.*&)?(?:url|q)=([^&]+)/i);
    if (g) url = decodeURIComponent(g[1]);
    if (seen[url]) continue;
    seen[url] = 1;
    out.push({ url: url, text: text.slice(0, 140) });
  }
  return out;
}

// ======================= SURVEILLANCE DU SCRIPT GITHUB =====================

function watchGithub_() {
  var p = props_(), url = p.getProperty('GITHUB_STATUS_URL');
  if (!url) return;
  var problem = '';
  try {
    var r = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    if (r.getResponseCode() !== 200) problem = 'statut illisible (HTTP ' + r.getResponseCode() + ')';
    else {
      var last = Date.parse(JSON.parse(r.getContentText()).last_run || '');
      var mins = Math.round((Date.now() - last) / 60000);
      if (isNaN(last) || mins > REGLAGES.githubEnPanneApresMinutes) problem = 'dernier passage il y a ' + (isNaN(mins) ? '?' : mins) + ' min';
    }
  } catch (e) { problem = String(e.message || e); }
  if (problem && p.getProperty('gh_alerted') !== '1') {
    tg_('⚠️ <b>Script GitHub arrêté ?</b> ' + esc_(problem) + '\nVérifie l\'onglet Actions de ton dépôt (workflow désactivé, erreur…). La voie rapide continue.');
    p.setProperty('gh_alerted', '1');
  } else if (!problem && p.getProperty('gh_alerted') === '1') {
    tg_('✅ Script GitHub de nouveau actif.');
    p.setProperty('gh_alerted', '0');
  }
}

// ============================== MESSAGES ===================================

function frDate_(iso) {
  var m = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? m[3] + '/' + m[2] + '/' + m[1] : String(iso || '');
}

function formatOffer_(o) {
  var lines = ['🔔 <b>' + esc_(o.title) + '</b>'];
  if (o.company) lines.push('🏢 ' + esc_(o.company));
  var where = [o.city, o.country].filter(Boolean).join(', ');
  if (where) lines.push('📍 ' + esc_(where));
  lines.push('💼 ' + esc_(o.domain || 'Finance') + (o.basis === 'description' ? ' · <i>à vérifier (repérée via la description)</i>' : ''));
  var facts = [];
  if (o.published) facts.push('publiée le ' + frDate_(o.published));
  if (o.start) facts.push('début ' + frDate_(o.start));
  if (o.duration) facts.push(o.duration);
  if (o.salary) facts.push(o.salary);
  if (o.deadline) facts.push('candidature jusqu\'au ' + frDate_(o.deadline));
  if (facts.length) lines.push('🗓 ' + esc_(facts.join(' · ')));
  if (o.description) {
    var d = o.description.length > 280 ? o.description.slice(0, 279).replace(/\s+\S*$/, '') + '…' : o.description;
    lines.push('📝 <i>' + esc_(d) + '</i>');
  }
  lines.push('🔗 ' + esc_(o.url));
  lines.push('🛰 Source : Business France (voie rapide)');
  return lines.join('\n');
}

function line_(o) {
  var where = [o.city, o.country].filter(Boolean).join(', ');
  return '• <a href="' + esc_(o.url) + '">' + esc_(o.title) + '</a>' + (o.company ? ' — ' + esc_(o.company) : '') +
    (where ? ' (' + esc_(where) + ')' : '') + ' · <i>' + esc_(o.domain) + '</i>';
}

function notifyOffer_(o) {
  var text = formatOffer_(o);
  if (tg_(text, o.url)) return true;
  return mail_('[V.I.E finance] ' + o.title + ' – ' + o.company, text);
}

function sendLong_(lines) {
  var chunks = [], cur = '';
  lines.forEach(function (l) {
    if (cur && cur.length + l.length + 1 > 3800) { chunks.push(cur); cur = ''; }
    cur = cur ? cur + '\n' + l : l;
  });
  if (cur) chunks.push(cur);
  var ok = true;
  chunks.forEach(function (c) { if (!tg_(c) && !mail_('[V.I.E finance] Récapitulatif', c)) ok = false; });
  return ok;
}

var lastSendMs_ = 0;

function tg_(text, buttonUrl) {
  var p = props_(), token = p.getProperty('TELEGRAM_TOKEN'), chat = p.getProperty('TELEGRAM_CHAT_ID');
  if (!token || !chat) return false;
  var payload = { chat_id: chat, text: String(text).slice(0, 4096), parse_mode: 'HTML', disable_web_page_preview: true };
  if (buttonUrl && /^https?:/.test(buttonUrl)) payload.reply_markup = { inline_keyboard: [[{ text: '📨 Ouvrir l\'offre', url: buttonUrl }]] };
  for (var i = 0; i < 4; i++) {
    var wait = 1050 - (Date.now() - lastSendMs_);
    if (wait > 0) Utilities.sleep(wait);                  // ~1 message/s
    var r;
    try {
      r = UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage',
        { method: 'post', contentType: 'application/json', payload: JSON.stringify(payload), muteHttpExceptions: true });
    } catch (e) { Utilities.sleep(1500); continue; }
    lastSendMs_ = Date.now();
    var code = r.getResponseCode();
    if (code === 200) return true;
    var body = {};
    try { body = JSON.parse(r.getContentText()); } catch (e) { /* ignore */ }
    var desc = String(body.description || '').toLowerCase();
    if (code === 429) { Utilities.sleep(Math.min(Number((body.parameters || {}).retry_after || 5), 30) * 1000); continue; }
    if (code === 400 && desc.indexOf('parse') >= 0) { payload.text = toPlain_(payload.text); delete payload.parse_mode; continue; }
    if (code === 400 && payload.reply_markup && (desc.indexOf('button') >= 0 || desc.indexOf('url') >= 0)) { delete payload.reply_markup; continue; }
    if (code >= 500) { Utilities.sleep(1500); continue; }
    Logger.log('Telegram a refusé le message : ' + code + ' ' + desc);
    return false;
  }
  return false;
}

function mail_(subject, html) {
  try {
    MailApp.sendEmail(Session.getEffectiveUser().getEmail(), subject, toPlain_(html));
    return true;
  } catch (e) { Logger.log('E-mail non envoyé : ' + e); return false; }
}

// ============================== OUTILS =====================================

function props_() { return PropertiesService.getScriptProperties(); }

/** True (et mémorise l'heure) si la tâche n'a pas tourné depuis « minutes » (marge de 20 s). */
function due_(key, minutes) {
  var p = props_(), last = Number(p.getProperty(key) || 0);
  if (Date.now() - last < minutes * 60000 - 20000) return false;
  p.setProperty(key, String(Date.now()));
  return true;
}

function safe_(fn) { try { fn(); } catch (e) { Logger.log(fn.name + ' : ' + e); } }

function esc_(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

function decodeEntities_(s) {
  return String(s || '').replace(/&nbsp;/g, ' ').replace(/&#39;|&apos;/g, '\'').replace(/&quot;/g, '"')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#(\d+);/g, function (m, n) { return String.fromCharCode(Number(n)); })
    .replace(/&amp;/g, '&');
}

function stripHtml_(s) {
  return decodeEntities_(String(s || '').replace(/<br\s*\/?>|<\/p>|<\/li>/gi, ' ').replace(/<[^>]+>/g, ' ')).replace(/\s+/g, ' ').trim();
}

function toPlain_(s) {
  return decodeEntities_(String(s).replace(/<a href="([^"]+)">([^<]*)<\/a>/g, '$2 ($1)').replace(/<[^>]+>/g, ''));
}

function paris_(d) {
  var parts = Utilities.formatDate(d, TZ, 'yyyy-MM-dd|H|m|u').split('|');
  return { date: parts[0], hour: Number(parts[1]), minute: Number(parts[2]), dow: Number(parts[3]) };
}

function runtimeToday_() {
  var v = (props_().getProperty('runtime') || '').split('|');
  return v[0] === paris_(new Date()).date ? Number(v[1] || 0) : 0;
}

function addRuntime_(ms) {
  props_().setProperty('runtime', paris_(new Date()).date + '|' + (runtimeToday_() + ms));
}

function setOf_(arr) { var o = {}; arr.forEach(function (x) { o[x] = true; }); return o; }

function merge_(a, b) { var o = {}; Object.keys(a).forEach(function (k) { o[k] = true; }); Object.keys(b).forEach(function (k) { o[k] = true; }); return o; }

/** Ensembles d'identifiants stockés en morceaux de 8 000 caractères (limite des propriétés : 9 Ko). */
function putSet_(name, ids) {
  var p = props_(), s = ids.join(','), parts = Math.ceil(s.length / 8000) || 1, kv = {};
  for (var i = 0; i < parts; i++) kv[name + '_' + i] = s.slice(i * 8000, (i + 1) * 8000);
  kv[name + '_n'] = String(parts);
  var old = Number(p.getProperty(name + '_n') || 0);
  p.setProperties(kv);
  for (var j = parts; j < old; j++) p.deleteProperty(name + '_' + j);
}

function getSet_(name) {
  var p = props_(), n = Number(p.getProperty(name + '_n') || 0), s = '';
  for (var i = 0; i < n; i++) s += p.getProperty(name + '_' + i) || '';
  return s ? s.split(',') : [];
}
