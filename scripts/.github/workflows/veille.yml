name: Veille quotidienne
on:
  schedule:
    - cron: "30 5 * * *"   # tous les jours à 05h30 UTC (06h30 ou 07h30 à Paris)
  workflow_dispatch:        # permet aussi de la lancer à la main
permissions:
  contents: write
jobs:
  collecte:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install feedparser
      - run: python scripts/collect.py
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
      - name: Enregistrer les propositions
        run: |
          git config user.name "veille-bot"
          git config user.email "veille-bot@users.noreply.github.com"
          git add a_valider.json
          git diff --staged --quiet || git commit -m "Propositions du $(date +%F)"
          git push
