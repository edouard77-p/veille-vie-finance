/**
 * Exécute apps_script/Code.gs dans Node avec des services Google simulés.
 *   node tests/apps_script_harness.js parity  < entrées JSON  -> verdicts du classifieur JS
 *   node tests/apps_script_harness.js scenario                -> déroulé installer/tick/doGet/Gmail
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const CODE = fs.readFileSync(path.join(__dirname, '..', 'apps_script', 'Code.gs'), 'utf8');

function makeContext(route) {
  const props = {};
  const sent = { telegram: [], mail: [] };
  const clock = { now: Date.UTC(2026, 9, 26, 9, 0, 0) };
  const resp = (code, body) => ({
    getResponseCode: () => code,
    getContentText: () => (typeof body === 'string' ? body : JSON.stringify(body)),
  });
  const fetch = (url, opts) => {
    opts = opts || {};
    if (url.indexOf('api.telegram.org') >= 0) {
      const payload = JSON.parse(opts.payload || '{}');
      if (url.endsWith('/getUpdates')) return resp(200, { ok: true, result: [{ message: { chat: { id: 4242, first_name: 'Eder' } } }] });
      sent.telegram.push(payload);
      return resp(200, { ok: true });
    }
    return route(url, opts, resp);
  };
  const labels = {};
  const ctx = {
    console,
    PropertiesService: {
      getScriptProperties: () => ({
        getProperty: (k) => (k in props ? props[k] : null),
        setProperty: (k, v) => { props[k] = String(v); },
        setProperties: (o) => { Object.keys(o).forEach((k) => { props[k] = String(o[k]); }); },
        deleteProperty: (k) => { delete props[k]; },
        getProperties: () => Object.assign({}, props),
      }),
    },
    CacheService: { getScriptCache: () => ({ get: () => null, put: () => {} }) },
    UrlFetchApp: { fetch, fetchAll: (reqs) => reqs.map((r) => fetch(r.url, r)) },
    Utilities: {
      sleep: () => {},
      getUuid: () => '1234-5678',
      formatDate: (d, tz) => {
        const f = new Intl.DateTimeFormat('en-GB', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
          hour: 'numeric', minute: 'numeric', weekday: 'short', hour12: false }).formatToParts(d);
        const g = (t) => f.find((p) => p.type === t).value;
        const dow = { Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6, Sun: 7 }[g('weekday')];
        return `${g('year')}-${g('month')}-${g('day')}|${Number(g('hour')) % 24}|${Number(g('minute'))}|${dow}`;
      },
    },
    LockService: { getScriptLock: () => ({ tryLock: () => true, releaseLock: () => {} }) },
    MailApp: { sendEmail: (to, subject, body) => sent.mail.push({ to, subject, body }) },
    Session: { getEffectiveUser: () => ({ getEmail: () => 'moi@example.com' }) },
    GmailApp: {
      threads: [],
      search: function () { return this.threads.filter((t) => !t.labels.includes('vie-relaye')); },
      getUserLabelByName: (n) => labels[n] || null,
      createLabel: (n) => (labels[n] = { name: n }),
    },
    ContentService: { MimeType: { JSON: 'json' }, createTextOutput: (s) => ({ content: s, setMimeType() { return this; } }) },
    ScriptApp: {
      triggers: [],
      getProjectTriggers() { return this.triggers; },
      deleteTrigger(t) { this.triggers = this.triggers.filter((x) => x !== t); },
      newTrigger(fn) {
        const self = this;
        return { timeBased: () => ({ everyMinutes: (n) => ({ create: () => self.triggers.push({ fn, n, getHandlerFunction: () => fn }) }) }) };
      },
    },
    Logger: { log: () => {} },
  };
  vm.createContext(ctx);
  vm.runInContext(CODE, ctx);
  ctx.__clock = clock;
  vm.runInContext('Date.now = function () { return __clock.now; };', ctx);
  return { ctx, props, sent, clock };
}

function bfOffer(id, title, extra) {
  return Object.assign({ id, missionTitle: title, organizationName: 'Société ' + id, cityName: 'SINGAPOUR', countryName: 'SINGAPOUR',
    missionDuration: 12, indemnite: 3214.5, startBroadcastDate: '2026-10-26T08:00:00Z', missionType: 'VIE',
    missionDescription: 'Description de la mission.' }, extra || {});
}

function scenario() {
  let offers = [];
  for (let i = 0; i < 150; i++) offers.push(bfOffer(1000 + i, i % 10 === 0 ? 'VIE Financial Analyst ' + i : 'VIE Ingénieur Méthodes ' + i));
  let failing = false;
  const route = (url, opts, resp) => {
    if (url === 'https://mon-vie-via.businessfrance.fr/') return resp(200, '<script>{config:{API_KEY:"k\\u002Fey",a:1}}</script>');
    if (url.indexOf('/api/Offers/search') >= 0) {
      if (failing) return resp(503, 'down');
      if (opts.headers['X-API-KEY'] !== 'k/ey') return resp(401, 'no');
      const b = JSON.parse(opts.payload);
      return resp(200, { count: offers.length, result: offers.slice(b.skip, b.skip + b.limit) });
    }
    if (url.indexOf('raw.githubusercontent.com') >= 0) return resp(200, { last_run: new Date(Date.UTC(2026, 9, 26, 6, 0)).toISOString() });
    return resp(404, 'not found');
  };
  const { ctx, props, sent, clock } = makeContext(route);
  const out = {};
  props.TELEGRAM_TOKEN = '123:abc';
  vm.runInContext('trouverChatId()', ctx);
  out.chatId = props.TELEGRAM_CHAT_ID;

  vm.runInContext('installer()', ctx);
  out.afterInstall = { telegram: sent.telegram.length, firstText: sent.telegram[0].text, triggers: ctx.ScriptApp.triggers.length,
    sentIds: vm.runInContext("getSet_('sent').length", ctx), seenIds: vm.runInContext("getSet_('seen').length", ctx) };

  // Deux nouvelles offres : une finance, une non.
  offers.push(bfOffer(2001, 'V.I.E - Treasury Analyst (H/F)'), bfOffer(2002, 'VIE Business Developer'));
  sent.telegram.length = 0;
  clock.now += 11 * 60000;
  vm.runInContext('tick()', ctx);
  out.afterNew = sent.telegram.map((p) => ({ text: p.text, button: !!p.reply_markup }));

  sent.telegram.length = 0;
  clock.now += 11 * 60000;
  vm.runInContext('tick()', ctx);
  out.repeat = sent.telegram.length;

  const good = JSON.parse(vm.runInContext(`doGet({parameter:{token:'${props.STATUS_TOKEN}'}}).content`, ctx));
  const bad = JSON.parse(vm.runInContext("doGet({parameter:{token:'faux'}}).content", ctx));
  out.doGet = { ok: good.ok, hasNew: good.sentIds.indexOf('2001') >= 0, bfOk: good.bfOk, badOk: bad.ok };

  // Pannes : 3 échecs -> une seule alerte, puis message de rétablissement.
  failing = true;
  sent.telegram.length = 0;
  for (let i = 0; i < 4; i++) { clock.now += 11 * 60000; vm.runInContext('tick()', ctx); }
  out.failureAlerts = sent.telegram.filter((p) => p.text.indexOf('en échec') >= 0).length;
  failing = false;
  clock.now += 11 * 60000;
  vm.runInContext('tick()', ctx);
  out.recovered = sent.telegram.some((p) => p.text.indexOf('rétabli') >= 0);

  // Relais Gmail
  ctx.GmailApp.threads = [{
    labels: [], getId: () => 't1', addLabel(l) { this.labels.push(l.name); },
    getMessages: () => [{
      getSubject: () => 'Nouvelles offres : VIE finance', getFrom: () => 'LinkedIn <jobalerts-noreply@linkedin.com>',
      getPlainBody: () => '', getBody: () => '<a href="https://www.linkedin.com/comm/jobs/view/111">V.I.E Credit Analyst – BNP Paribas</a>' +
        '<a href="https://www.linkedin.com/comm/jobs/view/111">V.I.E Credit Analyst – BNP Paribas</a>' +
        '<a href="https://www.google.com/url?rct=j&amp;url=https%3A%2F%2Fex.com%2Fjob&amp;ct=ga">VIE Treasury Analyst Singapore</a>' +
        '<a href="https://ex.com/aide">Aide comptable – VIE Montréal</a>' +
        '<a href="https://www.linkedin.com/settings">Se désabonner de cette alerte</a><a href="x">court</a>',
    }],
  }];
  props.GITHUB_STATUS_URL = 'https://raw.githubusercontent.com/moi/veille/main/state/status.json';
  sent.telegram.length = 0;
  clock.now += 31 * 60000;
  vm.runInContext('tick()', ctx);
  out.gmail = { messages: sent.telegram.filter((p) => p.text.indexOf('📧') === 0).map((p) => p.text), labelled: ctx.GmailApp.threads[0].labels };
  out.ghWatchAlert = sent.telegram.some((p) => p.text.indexOf('Script GitHub arrêté') >= 0);
  process.stdout.write(JSON.stringify(out));
}

function parity() {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const { ctx } = makeContext(() => null);
  ctx.__input = input;
  const res = vm.runInContext(`(function () {
    var c = new Classifier_(DEFAULT_KEYWORDS);
    return __input.map(function (x) {
      var v = c.classify(x[0], x[1] || '', x[2] || '');
      return { isFinance: v.isFinance, domain: v.domain || '', basis: v.basis || '', vie: c.looksVie(x[0], x[1] || '') };
    });
  })()`, ctx);
  process.stdout.write(JSON.stringify(res));
}

({ parity, scenario })[process.argv[2] || 'scenario']();
