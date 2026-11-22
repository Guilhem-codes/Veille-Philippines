#!/usr/bin/env python3
"""Étape 4 : applique tes décisions.
Dans a_valider.json, mets "statut": "valide" ou "rejete" sur chaque proposition.
Ce script verse les validées dans donnees.json (événement + fil d'actualité),
retire les validées et les rejetées de a_valider.json, et laisse le reste en attente."""
import json, re, datetime as dt

def charger(n):
    with open(n, encoding="utf-8") as f: return json.load(f)
def ecrire(n, o):
    with open(n, "w", encoding="utf-8") as f: json.dump(o, f, ensure_ascii=False, indent=1)

def main():
    donnees, attente = charger("donnees.json"), charger("a_valider.json")
    evs, news = donnees["evenements"], donnees["actualites"]
    liens = {u for e in evs for u in re.findall(r"https?://\S+", e.get("source", ""))} | {n.get("url") for n in news}
    nums = [int(m.group(1)) for e in evs for m in [re.search(r"(\d+)$", e.get("id", ""))] if m]
    suivant = max(nums or [0]) + 1
    reste, ok, rej, dbl = [], 0, 0, 0
    for p in attente["propositions"]:
        s = (p.get("statut") or "").strip().lower()
        if s == "rejete": rej += 1; continue
        if s != "valide": reste.append(p); continue
        if p.get("lien") in liens: dbl += 1; continue
        ident = "phcn-2026-%03d" % suivant; suivant += 1
        evs.append({"id": ident, "ref": ident.upper(), "title": p["titre"], "date": p["date"],
                    "cat": p["cat"], "impact": p["impact"], "src": p["src"], "info": p.get("info", "2"),
                    "place": p["lieu"], "desc": p["resume"], "source": "%s : %s" % (p["media"], p["lien"]),
                    "lat": p.get("lat"), "lng": p.get("lng"), "ex": ""})
        for l in [{"media": p["media"], "lien": p["lien"]}] + (p.get("autres_liens") or []):
            if l["lien"] in liens: continue
            liens.add(l["lien"])
            news.append({"id": "n-%s-%s" % (re.sub(r"\W", "", l["media"].lower())[:12], p["date"].replace("-", "")),
                         "date": p["date"], "note": "", "source": l["media"], "title": p["titre"], "url": l["lien"]})
        ok += 1
    attente["propositions"] = reste
    donnees["mise_a_jour"] = dt.date.today().isoformat()
    ecrire("donnees.json", donnees); ecrire("a_valider.json", attente)
    print("%d validées, %d rejetées, %d doublons ignorés, %d encore en attente" % (ok, rej, dbl, len(reste)))

if __name__ == "__main__": main()
