# 🧬 Bots de survie

Expérience de paper trading (argent fictif) : des bots tradent l'or et la crypto avec de vraies données. Ceux qui violent la règle de survie meurent et sont remplacés par des copies mutées des meilleurs.

## Mise en place (depuis un téléphone)

1. Sur github.com, crée un dépôt **public** nommé `bots-survie`.
2. Ajoute les fichiers (bouton « Add file » → « Create new file », colle le contenu) : `bot.py`, `config.json`, `index.html`, `README.md`, et `.github/workflows/daily.yml` (tape le chemin complet dans le nom du fichier, les `/` créent les dossiers).
3. Onglet **Settings → Actions → General → Workflow permissions** : choisis « Read and write permissions ».
4. Onglet **Actions** → « bots-quotidien » → **Run workflow** pour le premier lancement. Ensuite il se lance seul chaque jour à 00h10 UTC.
5. Onglet **Settings → Pages** : source « Deploy from a branch », branche `main`, dossier `/ (root)`. Ta page de suivi sera à `https://TON-PSEUDO.github.io/bots-survie/`.

## Réglages

Ils sont dans `config.json` (la page de suivi a un formulaire qui génère le texte à coller). Pour repartir de zéro (nouvelle règle, nouvel historique), supprime `state.json` puis relance le workflow.

## Points ouverts (à décider pendant l'expérience)

- **Critère de réussite** : battre le simple « acheter et garder » (courbes de marché), pas seulement atteindre +5 %/semaine.
- **Hasard** : peu de semaines = résultats trompeurs. Attendre 2 à 3 mois avant de conclure.
- **Frais et glissement** : 0,1 % par transaction est modeste. Les vrais coûts sont plus élevés sur de petits montants.
- **Positions longues uniquement** : pas de vente à découvert pour l'instant.
- **Heures de données** : l'or ne cote pas le week-end, donc ses bots ne bougent pas ces jours-là.
- **Extinction** : un bot mort est toujours remplacé, la population ne disparaît donc jamais. À toi de décider si une extinction totale doit arrêter l'expérience.
- **Argent réel** : aucun ordre réel n'est passé. Y venir plus tard demanderait des tests longs, une plateforme légale et la déclaration fiscale.
