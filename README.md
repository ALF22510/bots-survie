# 🧬 Bots de survie

Paper trading (argent fictif) : des bots tradent l'or et la crypto avec de vraies données. Ceux qui violent la règle de survie meurent et sont remplacés par des copies mutées des meilleurs.

## Mise à jour depuis la version quotidienne

Remplace le contenu de ces 4 fichiers sur GitHub (crayon → colle → Commit) :
`bot.py`, `config.json`, `index.html`, `.github/workflows/daily.yml`.
Puis onglet **Actions → bots → Run workflow**. Les résultats sont désormais stockés sur une branche `data` (créée automatiquement). Le vieux `state.json` de la branche principale est ignoré : tu peux le supprimer.

## Fonctionnement

- GitHub lance le script **toutes les 5 minutes** (minimum autorisé ; en pratique il peut y avoir du retard). À chaque lancement, il traite **toutes les bougies d'une minute terminées depuis le dernier lancement** : les bots décident donc à chaque minute, même si l'affichage se met à jour toutes les 5 à 15 minutes.
- La page de suivi se rafraîchit seule toutes les 60 secondes.
- L'or ne cote pas le week-end ; ses données Yahoo peuvent avoir environ 10 à 15 minutes de retard.

## Réglages (config.json)

La page de suivi a un formulaire qui génère le texte à coller dans config.json. Cases utiles : `interval` (1m, 5m, 15m, 1h, 1d), `period_days` (durée d'une « semaine » de survie), `death_rule`, `population`, `fee`, `backfill_days`. Pour repartir de zéro, coche « Réinitialiser » dans le formulaire (ça augmente `reset_id`).

## À savoir

- **Frais** : avec des bougies d'une minute et 0,1 % de frais par transaction, la plupart des bots perdent de l'argent en frais. Les bougies de 5 à 15 minutes donnent des résultats plus parlants.
- **Dépôt public** : nécessaire pour que Pages et les lancements automatiques restent gratuits.
- **Désactivation** : GitHub peut désactiver les lancements planifiés après 60 jours sans activité. Si tu reçois un e-mail à ce sujet, réactive le workflow dans l'onglet Actions.
- **Pas d'ordres réels** : tout est simulé.

## Points ouverts

- Critère de réussite : battre « acheter et garder » (courbes de marché), pas seulement atteindre +5 %.
- Hasard : attendre plusieurs semaines avant de conclure.
- Positions longues uniquement (pas de vente à découvert).
- Extinction : un bot mort est toujours remplacé, la population ne disparaît jamais.
