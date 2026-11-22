#!/usr/bin/env python3
"""Veille Chine / Philippines : collecte quotidienne.

1. Lit des flux RSS (presse philippine et internationale + recherches Google Actualités).
2. Filtre par mots-clés, retire ce qui est déjà connu.
3. Demande à Gemini (offre gratuite) de trier et structurer les articles retenus.
4. Écrit les PROPOSITIONS dans a_valider.json. Rien n'est ajouté à donnees.json.
"""
import json, os, re, sys, time, datetime as dt
import urllib.parse, urllib.request
import feedparser

JOURS = 3             # on regarde les articles des 3 derniers jours
MAX_ARTICLES = 40     # plafond d'articles envoyés au modèle par exécution
PAR_REQUETE = 10      # articles par requête au modèle
MAX_REQUETES = 6      # plafond de requêtes au modèle par exécution (quota gratuit)
MODELES = [os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest"), "gemini-flash-latest"]
CLE = os.environ.get("GEMINI_API_KEY", "")

FLUX = [
    "https://www.philstar.com/rss/nation",
    "https://newsinfo.inquirer.net/feed",
    "https://mb.com.ph/rss/articles",
    "https://data.gmanetwork.com/gno/rss/news/nation/feed.xml",
    "https://www.rappler.com/feed/",
    "https://tribune.net.ph/feed",
    "https://news.usni.org/feed",
    "https://thediplomat.com/feed/",
]
def gnews(q): return "https://news.google.com/rss/search?q=%s&hl=en-PH&gl=PH&ceid=PH:en" % urllib.parse.quote(q + " when:3d")
FLUX += [gnews(q) for q in [
    '"West Philippine Sea"', '"Scarborough Shoal"', '"Second Thomas Shoal"', "Ayungin Shoal", "Pag-asa Island",
    "China Coast Guard Philippines", "Chinese vessel Philippines", "Philippines China Taiwan Batanes", "Luzon Strait Philippines",
    "Basilan", "Sulu Jolo", "Maguindanao", "Zamboanga", "Cotabato", "BARMM ambush", "Mindanao shooting",
    "site:tribune.net.ph China Philippines", "site:tribune.net.ph Mindanao", "site:mb.com.ph China Philippines", "site:mb.com.ph Mindanao",
]]

MER = re.compile(r"(west philippine sea|south china sea|scarborough|bajo de masinloc|second thomas|ayungin|sierra madre|pag-?asa|"
    r"spratly|kalayaan|sabina|escoda|sandy cay|reed bank|batanes|luzon strait|china coast guard|chinese coast guard|"
    r"chinese (vessel|ship|navy|warship|research)|pla navy|liaoning|shandong|manila.{0,20}beijing|beijing.{0,20}manila|tarriela|trinidad)", re.I)
ZONE = re.compile(r"(basilan|sulu|jolo|maguindanao|cotabato|barmm|lamitan|zamboanga|abu sayyaf|dawlah|mindanao|bangsamoro)", re.I)
INCIDENT = re.compile(r"(ambush|gunmen|gunman|shot dead|shooting|killed|slain|attack|clash|encounter|bomb|explosion|grenade|kidnap|"
    r"soldier|troops|army|military|police|operation|manhunt|wounded|arrest)", re.I)
class MOTS:
    @staticmethod
    def search(t): return bool(MER.search(t) or (ZONE.search(t) and INCIDENT.search(t)))

def charger(chemin, defaut):
    try:
        with open(chemin, encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError: return defaut

def nettoyer(t): return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t or "")).strip()

def source_lettre(url, nom):
    t = (url + " " + nom).lower()
    if re.search(r"reuters|apnews|\bap\b|afp|usni|pna\.gov|pia\.gov|gov\.ph", t): return "A"
    if re.search(r"philstar|inquirer|gmanetwork|mb\.com|manilatimes|thediplomat|rappler|tribune|sunstar|bulletin|cnn|bbc|aljazeera", t): return "B"
    return "C"

def collecter():
    limite = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(days=JOURS)
    vus, out = set(), []
    for u in FLUX:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                                                     "Accept": "application/rss+xml, application/xml, text/xml, */*"})
            with urllib.request.urlopen(req, timeout=30) as r: f = feedparser.parse(r.read())
        except Exception as e: print("ECHEC flux (%s) : %s" % (str(e)[:80], u[:110])); continue
        if not f.entries: print("VIDE (0 article dans le flux) :", u[:110]); continue
        n = 0
        for rang, e in enumerate(f.entries):
            lien = e.get("link", "")
            if not lien or lien in vus: continue
            d = e.get("published_parsed") or e.get("updated_parsed")
            if d and dt.datetime(*d[:6]) < limite: continue
            titre, resume = nettoyer(e.get("title")), nettoyer(e.get("summary"))[:600]
            if not MOTS.search(titre + " " + resume): continue
            vus.add(lien); n += 1
            out.append(dict(rang=rang, titre=titre, resume=resume, lien=lien,
                            media=nettoyer(getattr(e, "source", {}).get("title", "")) or f.feed.get("title", ""),
                            publie=dt.datetime(*d[:6]).strftime("%Y-%m-%d") if d else ""))
        print("OK %3d retenus sur %3d lus : %s" % (n, len(f.entries), u[:110]))
    out.sort(key=lambda a: a["rang"])
    return out

PROMPT = """Tu aides à tenir une veille de sécurité Chine / Philippines (mer de Chine méridionale, détroit de Luçon, sécurité intérieure à Mindanao/Sulu/BARMM).
Pour chaque article ci-dessous, dis s'il décrit un ÉVÉNEMENT CONCRET et récent (incident en mer ou dans les airs, mouvement militaire notable, déclaration diplomatique marquante, attaque ou opération de sécurité à Mindanao, etc.).
Exclus : opinions, analyses sans fait nouveau, rappels d'événements anciens, sujets sans lien avec la zone.
Réponds UNIQUEMENT par un tableau JSON, un objet par article retenu, avec ces champs :
- "n" : numéro de l'article
- "titre" : titre court en français
- "date" : date de l'événement AAAA-MM-JJ, ou null si tu ne peux pas la déduire de l'article
- "cat" : "incident" (mer, air, pêche, navires), "militaire", "diplo", ou "terrestre" (sécurité intérieure)
- "impact" : 1 (faible), 2 (moyen), 3 (élevé : morts, collision, attaque directe)
- "lieu" : lieu en français, aussi précis que l'article le permet
- "lat", "lng" : coordonnées approximatives si tu connais le lieu avec certitude, sinon null
- "resume" : 2 à 4 phrases factuelles en français, uniquement ce que dit l'article
N'invente rien : si une information manque, mets null. Si aucun article ne convient, réponds [].

ARTICLES :
"""

def appeler(articles, debut):
    texte = PROMPT + "\n".join("[%d] %s | %s | publié %s\n%s" % (debut + i, a["titre"], a["media"], a["publie"], a["resume"]) for i, a in enumerate(articles))
    corps = json.dumps({"contents": [{"parts": [{"text": texte}]}],
                        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}}).encode()
    for modele in MODELES:
        url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % modele
        for essai in range(4):
            req = urllib.request.Request(url, corps, {"Content-Type": "application/json", "x-goog-api-key": CLE})
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    rep = json.load(r)
                t = rep["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(re.sub(r"^```(?:json)?|```$", "", t.strip()).strip())
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="ignore")[:200].replace("\n", " ")
                print("Erreur Gemini %s (%s), essai %d : %s" % (e.code, modele, essai + 1, msg))
                if e.code in (429, 500, 502, 503, 504) and essai < 3: time.sleep(30 * (essai + 1)); continue
                break
            except Exception as e:
                print("Erreur (%s) :" % modele, e)
                if essai < 3: time.sleep(10); continue
                break
    return None

def main():
    if not CLE: sys.exit("GEMINI_API_KEY absente : vérifie le secret GitHub.")
    donnees = charger("donnees.json", {"evenements": [], "actualites": []})
    attente = charger("a_valider.json", {"mise_a_jour": None, "propositions": []})
    connus = {n.get("url") for n in donnees.get("actualites", [])} | {p.get("lien") for p in attente["propositions"]}
    connus |= {u for e in donnees.get("evenements", []) for u in re.findall(r"https?://\S+", e.get("source", ""))}
    arts = [a for a in collecter() if a["lien"] not in connus][:MAX_ARTICLES]
    print(len(arts), "articles nouveaux envoyés au modèle")
    ajoutes = 0
    echecs = 0
    for k in range(0, min(len(arts), PAR_REQUETE * MAX_REQUETES), PAR_REQUETE):
        lot = arts[k:k + PAR_REQUETE]
        res = appeler(lot, k)
        if res is None:
            echecs += 1; print("Lot %d ignoré (le modèle n'a pas répondu)." % (k // PAR_REQUETE + 1))
            if echecs >= 2: print("Arrêt après 2 échecs consécutifs."); break
            continue
        echecs = 0
        for r in res:
            try: a = arts[int(r["n"])]
            except Exception: continue
            attente["propositions"].append({
                "date": r.get("date") or a["publie"], "date_incertaine": not r.get("date"),
                "titre": r.get("titre") or a["titre"], "cat": r.get("cat"), "impact": r.get("impact"),
                "lieu": r.get("lieu"), "lat": r.get("lat"), "lng": r.get("lng"),
                "resume": r.get("resume"), "src": source_lettre(a["lien"], a["media"]), "info": "2",
                "media": a["media"], "lien": a["lien"], "ajoute_le": dt.date.today().isoformat(),
                "statut": "à vérifier"})
            ajoutes += 1
        time.sleep(5)
    attente["mise_a_jour"] = dt.date.today().isoformat()
    with open("a_valider.json", "w", encoding="utf-8") as f:
        json.dump(attente, f, ensure_ascii=False, indent=1)
    print(ajoutes, "propositions ajoutées ; total en attente :", len(attente["propositions"]))

if __name__ == "__main__": main()
