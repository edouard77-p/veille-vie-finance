# Veille V.I.E finance → Telegram (0 €/mois)

Système gratuit qui détecte les nouvelles offres de **V.I.E en finance** dans le monde et t'envoie une notification Telegram (e-mail en secours) avec : titre, entreprise, ville/pays, domaine financier, date de publication, durée, indemnité, date limite, extrait de description, lien direct et source.

```
              ┌──────────────── Voie rapide : Google Apps Script (déclencheur chaque minute) ─────────────┐
              │  Business France : scan toutes les 2 min (7h–21h lun–ven), 10 min sinon                     │
              │  Relais Gmail : alertes LinkedIn / Indeed / WTTJ / Google Alerts… → Telegram (toutes 5 min) │
              │  Surveille le script GitHub                                                               │
              └───────────────┬──────────────────────────────────────────────────────────▲───────────────┘
                              │ Telegram                                    état (offres  │ statut
   ton téléphone ◄────────────┤                                             déjà envoyées)│
                              │ Telegram / e-mail                                         │
              ┌───────────────┴──────────────── Script Python : GitHub Actions (toutes les 10 min) ──────┐
              │  Business France (secours, ou principal si pas de voie rapide)                             │
              │  Flux RSS Google Alerts + Talkwalker · page V.I.E BNP Paribas · Workday/Greenhouse/Lever…   │
              │  Filtre finance FR/EN (7 domaines) · bilan quotidien à 20h · alertes de panne              │
              └────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Pourquoi cette architecture

**La source qui compte : Mon Volontariat International (Business France).** Tous les V.I.E passent par Business France ; son site s'appuie sur une API JSON qui renvoie toutes les offres en ligne (≈ 900–1 000) avec titre, entreprise, ville, pays, dates, indemnité et description. Elle n'est pas triée par date : il faut lire les ~10 pages à chaque passage. Les entreprises (ex. BNP Paribas) republient parfois leurs V.I.E sur leur site, et les agrégateurs (LinkedIn, Indeed…) les relaient avec du retard.

**Le facteur limitant de la vitesse : l'hébergement gratuit.**

| | Fréquence possible | Remarque |
|---|---|---|
| GitHub Actions (cron) | 5 min minimum, souvent retardé de 5 à 30 min en charge | gratuit et illimité pour un dépôt public |
| **Google Apps Script** | **toutes les minutes** | gratuit, sans carte bancaire ; 90 min d'exécution/jour |
| Oracle / Google Cloud « free tier » | continu | demande une carte bancaire : écarté |

D'où deux moteurs complémentaires qui se surveillent mutuellement.

### Comparaison des trois options

| | A — Simple | B — Script Python + Telegram | **C — Couverture maximale (retenue)** |
|---|---|---|---|
| Coût réel | 0 € | 0 € | 0 € |
| Sources | Google Alerts, Talkwalker, alertes e-mail des sites | API Business France + quelques sources | API Business France (2 moteurs) + RSS + pages carrières + ATS + relais des alertes e-mail |
| Délai sur Business France | heures à 1 jour (indexation Google, e-mails quotidiens) | 10–40 min (cron GitHub) | **~1–2 min** en heures ouvrées, ~10 min sinon |
| Pertinence finance | moyenne (beaucoup de bruit) | bonne (titre + description) | bonne, offres ambiguës signalées « à vérifier » |
| Quotas | aucun souci | aucun (dépôt public) | Apps Script : budget de 90 min/jour, auto-régulé |
| Mise en place | 15 min | 30 min | ~45 min |
| Maintenance | nulle | faible | faible : diagnostic, bilan quotidien, alertes de panne |
| Fonctionnement durable | oui | oui (les commits d'état évitent la désactivation après 60 jours) | oui + surveillance croisée |

**Pas d'IA dans la boucle critique.** Un filtre par règles (FR/EN, titre puis catégorie puis description) est instantané, gratuit et prévisible ; un modèle de langage ajouterait de la latence et des quotas gratuits qui changent souvent, pour un gain marginal. Piste d'amélioration en §8.

---

## 2. Installation pas à pas (≈ 45 min)

### Étape 1 — Bot Telegram (5 min)

1. Dans Telegram, cherche **@BotFather** (badge bleu) → `/newbot`.
2. Nom affiché : `Veille VIE finance` ; identifiant : se termine par `bot` (ex. `eder_vie_finance_bot`).
3. BotFather te donne un **token** `123456789:AA...` → garde-le secret.
4. Ouvre ton bot (lien `t.me/<identifiant>`) et appuie sur **Démarrer** (ou envoie `/start`).
5. Récupère ton **chat ID** : ouvre dans ton navigateur `https://api.telegram.org/bot<TOKEN>/getUpdates` et note le nombre après `"chat":{"id":`.
6. Dans Telegram : épingle la conversation et active les notifications (son dédié conseillé).

### Étape 2 — Dépôt GitHub + script Python (15 min)

1. Crée un compte GitHub si besoin, puis **New repository** : nom `veille-vie-finance`, **Public** (minutes illimitées ; en privé, 2 000 min/mois ne suffiraient pas pour un passage toutes les 10 min), sans README.
2. **Add file › Upload files** et glisse **le contenu** du dossier décompressé.
   ⚠️ Le dossier caché `.github` doit être inclus (macOS : `Cmd + Maj + .` dans le Finder pour l'afficher). Vérifie ensuite que `.github/workflows/veille.yml` existe dans le dépôt ; sinon *Add file › Create new file*, nomme-le `.github/workflows/veille.yml` et colle son contenu.
3. **Settings › Secrets and variables › Actions › New repository secret** :
   - `TELEGRAM_BOT_TOKEN` = le token de BotFather
   - `TELEGRAM_CHAT_ID` = ton chat ID
4. Onglet **Actions** : si GitHub le demande, active les workflows.
5. **Actions › veille-vie-finance › Run workflow** :
   - commande `test-notify` → tu reçois une fausse offre + un message système ;
   - commande `run` → tu reçois **la liste de toutes les offres V.I.E finance actuellement en ligne** (initialisation), puis seulement les nouvelles ;
   - commande `check` → diagnostic de chaque source.
6. Ensuite tout est automatique (toutes les 10 min). Les commits « chore: état de la veille » sont normaux : c'est la mémoire du système.

### Étape 3 — Voie rapide Apps Script (15 min)

1. Va sur [script.google.com](https://script.google.com) › **Nouveau projet** › nomme-le `Voie rapide VIE`.
2. Remplace le contenu de `Code.gs` par celui de `apps_script/Code.gs` › Enregistrer.
3. ⚙️ **Paramètres du projet › Propriétés du script › Ajouter** :
   - `TELEGRAM_TOKEN` = le token du bot
   - `KEYWORDS_URL` = `https://raw.githubusercontent.com/<ton-pseudo>/veille-vie-finance/main/config/keywords.json` (mots-clés partagés avec GitHub)
   - `GITHUB_STATUS_URL` = `https://raw.githubusercontent.com/<ton-pseudo>/veille-vie-finance/main/state/status.json` (surveillance du script GitHub)
4. Dans l'éditeur, choisis la fonction **`trouverChatId`** › Exécuter. Google demande des autorisations : *Examiner les autorisations › ton compte › Paramètres avancés › Accéder à Voie rapide VIE (non sécurisé)*. C'est normal pour un script personnel : il lit l'API Business France, envoie des messages Telegram, lit le libellé Gmail `vie-alertes` et peut t'envoyer un e-mail de secours.
5. Exécute **`installer`** → message « Voie rapide installée » sur Telegram.
6. Exécute **`testerAlertes`** → fausse offre sur Telegram + e-mail de test dans ta boîte.
7. **Relier les deux moteurs** (évite les doublons et active la surveillance croisée) :
   - **Déployer › Nouveau déploiement** › type *Application Web* › Exécuter en tant que *Moi* › Accès *Tout le monde* › Déployer › copie l'URL qui finit par `/exec` ;
   - dans GitHub, ajoute les secrets `FASTLANE_URL` = cette URL et `FASTLANE_TOKEN` = la valeur `STATUS_TOKEN` (visible dans les propriétés du script).

   Le point d'accès ne renvoie que l'état (heure du dernier scan, identifiants d'offres déjà envoyées) et exige le jeton.

### Étape 4 — Alertes e-mail des plateformes → Telegram (10 min, facultatif mais conseillé)

LinkedIn, Indeed et les autres interdisent la collecte automatisée : on utilise leurs **alertes e-mail officielles**, que la voie rapide relaie sur Telegram.

1. Crée des alertes avec ces recherches (localisation : monde entier si possible) :
   - **LinkedIn Jobs** : `"VIE" finance`, `"V.I.E" analyst`, `VIE (treasury OR controller OR "financial analyst" OR "credit analyst")` — active aussi les notifications de l'appli LinkedIn ;
   - **Indeed** : `VIE finance`, `volontariat international finance` ;
   - **Welcome to the Jungle** : contrat *VIE* + métier *Finance* › *Créer une alerte* ;
   - **JobTeaser** (via l'espace carrière de ton école) : type de contrat VIE ;
   - **BNP Paribas** : page des offres V.I.E › *Créer mon alerte mail* ;
   - **Business France** : si ton espace candidat propose une alerte ou une recherche sauvegardée, active-la.
2. Quand le premier e-mail de chaque plateforme arrive : ouvre-le › ⋮ › **Filtrer les messages similaires** › *Créer un filtre* › **Appliquer le libellé** › nouveau libellé `vie-alertes`.
3. Toutes les 5 minutes, la voie rapide transmet sur Telegram chaque e-mail portant ce libellé (objet + liens vers les offres), puis le marque `vie-relaye`.

### Étape 5 — Google Alerts et Talkwalker en RSS (10 min)

1. Sur [google.com/alerts](https://www.google.com/alerts), crée ces alertes avec *Afficher les options* : Fréquence **Au fil de l'eau**, Langue **Toutes**, Région **Toutes**, Nombre **Tous les résultats**, Envoyer à **Flux RSS** :
   - `"V.I.E" (finance OR financial OR audit OR trésorerie OR treasury OR "contrôle de gestion")`
   - `"VIE" ("financial analyst" OR "FP&A" OR controller OR "credit analyst" OR "M&A" OR "risk analyst")`
   - `site:linkedin.com/jobs ("V.I.E" OR "VIE") (finance OR analyst OR controller)`
2. Sur [talkwalker.com/alerts](https://www.talkwalker.com/alerts), crée `"volontariat international" (finance OR banque OR audit OR trésorerie)` avec livraison **RSS**.
3. Clique sur l'icône RSS de chaque alerte, copie l'URL et colle-la dans `config/sources.toml` (champ `url` des blocs `[[rss]]`) directement sur GitHub (icône crayon › *Commit changes*).

Ces sources sont plus lentes (indexation Google : quelques heures) mais rattrapent des offres publiées hors Business France.

### Étape 6 — E-mail de secours côté GitHub (facultatif)

La voie rapide envoie déjà ses e-mails de secours via Gmail. Pour que le script GitHub le fasse aussi si Telegram tombe : active la validation en deux étapes sur ton compte Google, crée un **mot de passe d'application** (Compte Google › Sécurité › Mots de passe des applications), puis ajoute les secrets `SMTP_USER` (ton adresse Gmail) et `SMTP_PASSWORD` (le mot de passe d'application).

---

## 3. Tests de bon fonctionnement

| Test | Comment | Résultat attendu |
|---|---|---|
| Canal Telegram (GitHub) | Actions › Run workflow › `test-notify` | 1 fausse offre + 1 message système |
| Canal Telegram + e-mail (Apps Script) | exécuter `testerAlertes` | fausse offre sur Telegram + e-mail reçu |
| Sources | Run workflow › `check` | ✅/❌ par source, nombre d'offres V.I.E finance trouvées |
| Voie rapide | exécuter `diagnostic` | offres lues, budget du jour, date du dernier scan |
| Bilan | Run workflow › `heartbeat` | bilan du jour immédiat |
| Filtre finance | en local : `python -m vie_alert explain "VIE Junior Controller"` | décision, domaine et termes repérés |
| Tests automatiques (71 intitulés FR/EN, pipeline complet, pannes, voie rapide simulée) | `pip install -r requirements-dev.txt && python -m pytest` (relancés par GitHub à chaque modification du code) | tous verts |

---

## 4. Surveillance et reprise après erreur

| Incident | Réaction automatique |
|---|---|
| Erreur réseau ponctuelle | jusqu'à 3 nouvelles tentatives avec délai croissant |
| Une source tombe | les autres continuent ; alerte Telegram après 3 échecs consécutifs, puis message « rétablie » |
| Clé de l'API Business France changée | relecture automatique sur la page d'accueil du site |
| Réponse vide ou format changé | le scan échoue proprement **sans toucher à l'état** (pas de rafale de fausses nouveautés) |
| Notification non envoyée | l'offre n'est pas marquée comme vue : renvoyée au passage suivant ; e-mail en secours |
| Rafale d'offres | 30 messages max par passage (25 côté voie rapide), le reste dans un récapitulatif |
| Voie rapide arrêtée | le script GitHub te prévient et reprend le scan Business France à chaque passage |
| Script GitHub arrêté | la voie rapide te prévient (aucun passage depuis 90 min) |
| Workflow GitHub en erreur | message Telegram avec le lien vers le journal |
| Budget Apps Script presque épuisé | scans espacés à 10 min jusqu'au lendemain + message |
| Tout est muet | le **bilan quotidien de 20h** n'arrive pas → va voir l'onglet Actions |

---

## 5. Quotas et limites (vérifiés en octobre 2026)

| Service | Limite gratuite | Usage prévu |
|---|---|---|
| GitHub Actions | runners standard gratuits pour les dépôts publics ; cron ≥ 5 min, retards possibles ; workflows planifiés désactivés après 60 jours sans activité | 144 passages/jour ; l'état commité maintient l'activité |
| Apps Script (compte Gmail) | 20 000 appels UrlFetch/jour, 90 min/jour de déclencheurs, 6 min par exécution, 50 000 lectures/écritures de propriétés/jour, 100 destinataires d'e-mail/jour | ≈ 5 000 appels et ≈ 20 000 lectures/écritures par jour ; temps d'exécution surveillé et auto-régulé (75 min) |
| Telegram Bot API | gratuit ; ~1 message/s par conversation | respecté (pause de 1 s entre messages, gestion du code 429) |
| Google Alerts / Talkwalker | gratuits, livraison RSS | 4 flux prévus |

Charge sur Business France : ~10 requêtes par scan, soit ≈ 5 000 requêtes par jour ouvré au réglage par défaut. Passer `minutesHeuresOuvrees` à 1 doublerait cette charge pour gagner une minute en moyenne : déconseillé.

---

## 6. Règles d'usage respectées

- **Business France** : API non documentée mais publique (celle du site, avec la clé que le site envoie à tous les visiteurs) ; accès en lecture seule, fréquence modérée, usage personnel. Si Business France la ferme ou la restreint, le système te prévient : bascule alors sur une alerte e-mail officielle.
- **Pages carrières** : `robots.txt` vérifié avant chaque lecture, agent identifié, 1 page de liste + 5 fiches max par passage.
- **LinkedIn, Indeed, Welcome to the Jungle…** : aucune collecte automatisée, uniquement leurs alertes e-mail officielles.
- **Greenhouse, Lever, SmartRecruiters** : API publiques documentées par les éditeurs. **Workday** : le JSON appelé par la page carrières elle-même.
- **GitHub Actions** : les conditions de GitHub réservent en principe Actions aux activités liées au projet du dépôt ; ce type de veille légère est largement toléré mais reste une zone grise. Le workflow reste sobre (≈ 1 min toutes les 10 min, aucune boucle infinie) et la voie rapide fonctionne indépendamment si GitHub coupait l'accès.
- **Secrets** : jamais dans le code ; masqués dans les journaux publics.

---

## 7. Réglages utiles

- `config/keywords.json` — mots-clés finance (7 domaines), vetos (« auditeur qualité », « talent acquisition »…), seuil de détection par description. Partagé avec la voie rapide via `KEYWORDS_URL`. Teste une modification avec `python -m vie_alert explain "Titre"`.
- `config/sources.toml` — bilan quotidien, plafond de messages, inclusion des V.I.A, flux RSS, pages surveillées, entreprises Workday/Greenhouse/Lever/SmartRecruiters.
- `REGLAGES` en haut de `Code.gs` — fréquences, heures ouvrées, requête Gmail.

---

## 8. Améliorer la couverture sans dépenser

1. **Ajouter des entreprises** qui recrutent beaucoup de V.I.E en finance : repère l'URL de leur page carrières ; si elle contient `myworkdayjobs.com`, `greenhouse.io`, `lever.co` ou `smartrecruiters.com`, recopie un bloc dans `sources.toml`, puis lance `check`.
2. **Surveiller une page carrières simple** (liste d'offres en HTML) : bloc `[[page_watch]]` avec un `link_pattern` repris des liens d'offres.
3. **Multiplier les alertes ciblées** : Google Alerts `site:` sur les pages carrières de banques et groupes (ex. `site:careers.societegenerale.com "V.I.E"`), alertes LinkedIn par domaine (`VIE "M&A"`, `VIE "FP&A"`…).
4. **Affiner le filtre** à partir des messages « à vérifier » reçus : ajoute les intitulés manqués dans `keywords.json`, les faux positifs dans `veto_titre`.
5. **IA (optionnel, plus tard)** : un score de correspondance avec ton CV via une API de modèle de langage à palier gratuit, appliqué uniquement aux offres déjà retenues, pour les classer par priorité — sans ralentir l'alerte.

---

## 9. Dépannage

- **Aucun message après `test-notify`** : vérifie les secrets (pas d'espace), que tu as bien appuyé sur *Démarrer* dans le bot, et le journal de l'action.
- **`Push` refusé dans l'étape « Enregistrer l'état »** : Settings › Actions › General › Workflow permissions › *Read and write permissions*.
- **`Exception: Service invoked too many times`** (Apps Script) : quota du jour atteint ; il se réinitialise sous 24 h, et le script GitHub assure le relais.
- **`API Business France : HTTP 401`** persistant : la clé a changé et la page d'accueil a aussi changé de structure ; ouvre le site, F12 › Réseau, repère l'en-tête `X-API-KEY` d'une requête `Offers/search` et mets-la dans le secret GitHub `VIE_API_KEY` (et la constante `FALLBACK_API_KEY` de `Code.gs`).
- **Après une modification de `Code.gs`** : *Déployer › Gérer les déploiements › Modifier › Nouvelle version* pour mettre à jour l'application Web.

---

## Structure

```
.github/workflows/veille.yml   passage toutes les 10 min + commandes manuelles
.github/workflows/tests.yml    tests automatiques à chaque modification
apps_script/Code.gs            voie rapide (à coller dans script.google.com)
config/keywords.json           filtre finance (partagé Python / Apps Script)
config/sources.toml            sources et réglages du script Python
vie_alert/                     script Python (sources, filtre, notifications, état)
state/                         mémoire (offres vues, santé des sources) — géré automatiquement
tests/                         tests Python + exécution simulée de Code.gs
tools/sync_keywords.py         recopie keywords.json dans Code.gs (copie de secours)
```
