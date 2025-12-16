# Singular Daily

**Transform your content queue into a personalized daily podcast.**

## 🏗️ Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Next.js App   │────▶│     Supabase     │◀────│  Python Worker  │
│   (Vercel)      │     │  (Database/Auth) │     │    (Railway)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │   Telegram   │
                        │     Bot      │
                        └──────────────┘
```

## 📦 Structure du Projet

```
singular-daily/
├── singular-daily-app/     # Frontend Next.js
│   ├── src/
│   │   ├── app/           # Pages (App Router)
│   │   ├── components/    # Composants React
│   │   └── lib/          # Utilitaires & Supabase
│   └── package.json
│
├── python-worker/          # Backend Python
│   ├── bot.py             # Bot Telegram
│   ├── worker.py          # Traitement des contenus
│   ├── extractor.py       # Extraction de contenu
│   ├── generator.py       # Génération AI
│   ├── db.py              # Client Supabase
│   └── requirements.txt
│
└── supabase/
    └── schema.sql         # Schéma de base de données
```

---

## 🚀 Guide de Mise en Production

### Étape 1 : Configuration Supabase

1. **Créer un projet Supabase** sur [supabase.com](https://supabase.com)

2. **Exécuter le schéma SQL** :
   - Aller dans SQL Editor
   - Copier le contenu de `supabase/schema.sql`
   - Exécuter

3. **Créer les buckets Storage** :
   - Aller dans Storage
   - Créer un bucket `episodes` (public)
   - Créer un bucket `feeds` (public)

4. **Configurer les politiques Storage** :
   ```sql
   -- Pour le bucket episodes
   CREATE POLICY "Public read access"
   ON storage.objects FOR SELECT
   USING (bucket_id = 'episodes');

   CREATE POLICY "Authenticated upload"
   ON storage.objects FOR INSERT
   WITH CHECK (bucket_id = 'episodes');
   ```

5. **Récupérer les clés** :
   - Project URL: `Settings > API > Project URL`
   - Anon Key: `Settings > API > anon public`
   - Service Role Key: `Settings > API > service_role` (⚠️ secret!)

6. **Activer Google Auth** (optionnel) :
   - `Authentication > Providers > Google`
   - Configurer avec vos credentials Google Cloud

---

### Étape 2 : Déployer le Frontend (Vercel)

1. **Push le code sur GitHub**

2. **Importer sur Vercel** :
   - Aller sur [vercel.com](https://vercel.com)
   - New Project > Import depuis GitHub
   - Sélectionner le dossier `singular-daily-app`

3. **Configurer les variables d'environnement** :
   ```
   NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGc...
   SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...
   NEXT_PUBLIC_APP_URL=https://votre-app.vercel.app
   ```

4. **Déployer**

5. **Configurer le domaine** (optionnel) :
   - Settings > Domains > Add domain

---

### Étape 3 : Créer le Bot Telegram

1. **Créer le bot** :
   - Ouvrir [@BotFather](https://t.me/BotFather) sur Telegram
   - Envoyer `/newbot`
   - Choisir un nom : `Singular Daily`
   - Choisir un username : `SingularDailyBot`
   - Copier le token API

2. **Configurer le bot** :
   ```
   /setdescription - Transform your content into a daily podcast
   /setabouttext - Send YouTube links, articles, and podcasts. Get a personalized audio digest.
   /setcommands
   start - Connect your account
   queue - View your content queue
   generate - Create your podcast now
   help - Get help
   ```

---

### Étape 4 : Déployer le Worker Python (Railway)

1. **Créer un compte [Railway](https://railway.app)**

2. **Créer un nouveau projet** :
   - New Project > Deploy from GitHub Repo
   - Sélectionner votre repo
   - Root Directory: `python-worker`

3. **Configurer les variables d'environnement** :
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
   SUPABASE_URL=https://xxx.supabase.co
   SUPABASE_SERVICE_KEY=eyJhbGc...
   OPENAI_API_KEY=sk-...
   JINA_API_KEY=jina_... (optionnel)
   APP_URL=https://votre-app.vercel.app
   ```

4. **Configurer le démarrage** :
   - Settings > Start Command: `python bot.py`

5. **Déployer**

#### Alternative : Déployer sur un VPS

```bash
# Sur votre serveur
cd /opt
git clone votre-repo singular-daily
cd singular-daily/python-worker

# Créer un environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Configurer les variables
cp .env.example .env
nano .env  # Remplir les valeurs

# Créer un service systemd
sudo nano /etc/systemd/system/singular-daily-bot.service
```

Contenu du service :
```ini
[Unit]
Description=Singular Daily Telegram Bot
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/singular-daily/python-worker
Environment=PATH=/opt/singular-daily/python-worker/venv/bin
ExecStart=/opt/singular-daily/python-worker/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Activer et démarrer
sudo systemctl enable singular-daily-bot
sudo systemctl start singular-daily-bot

# Voir les logs
sudo journalctl -u singular-daily-bot -f
```

---

### Étape 5 : Configurer le CRON (Génération quotidienne)

Pour générer automatiquement les podcasts chaque matin :

#### Option A : Railway Cron Jobs
```bash
# Dans Railway, ajouter un Cron Job
Schedule: 0 6 * * *  # 6h00 UTC chaque jour
Command: python worker.py
```

#### Option B : GitHub Actions
Créer `.github/workflows/daily-generation.yml` :
```yaml
name: Daily Podcast Generation

on:
  schedule:
    - cron: '0 6 * * *'  # 6h00 UTC
  workflow_dispatch:  # Manuel

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          cd python-worker
          pip install -r requirements.txt
      
      - name: Run worker
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          cd python-worker
          python worker.py
```

---

## 🔧 Variables d'Environnement

### Frontend (Vercel)
| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_SUPABASE_URL` | URL du projet Supabase |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Clé publique Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | Clé service (pour API routes) |
| `NEXT_PUBLIC_APP_URL` | URL de l'app (pour RSS) |

### Backend (Railway/VPS)
| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Token du bot Telegram |
| `SUPABASE_URL` | URL du projet Supabase |
| `SUPABASE_SERVICE_KEY` | Clé service Supabase |
| `OPENAI_API_KEY` | Clé API OpenAI |
| `JINA_API_KEY` | (Optionnel) Clé Jina Reader |
| `APP_URL` | URL de l'app |

---

## 💰 Estimation des Coûts

| Service | Gratuit | Pro |
|---------|---------|-----|
| Vercel | ✅ Hobby plan | ~$20/mois |
| Supabase | ✅ Free tier (500MB) | ~$25/mois |
| Railway | ✅ $5 credit | ~$5-10/mois |
| OpenAI | ~$0.02/épisode | ~$0.02/épisode |

**Coût total estimé** : $0-5/mois pour un MVP avec usage modéré.

---

## 🧪 Tester en Local

### Frontend
```bash
cd singular-daily-app
cp .env.example .env.local
# Remplir les variables
npm install
npm run dev
```

### Backend
```bash
cd python-worker
python -m venv venv
source venv/bin/activate  # ou `venv\Scripts\activate` sur Windows
pip install -r requirements.txt
cp .env.example .env
# Remplir les variables
python bot.py
```

---

## 📝 Prochaines Étapes (V2)

- [ ] Transcription de podcasts audio (Whisper)
- [ ] Planification personnalisée de génération
- [ ] Multi-language support
- [ ] Résumés par email
- [ ] Historique des épisodes avec recherche
- [ ] Intégration Pocket/Instapaper
- [ ] App mobile

---

## 🆘 Dépannage

### Le bot ne répond pas
1. Vérifier le token Telegram
2. Vérifier les logs Railway/VPS
3. S'assurer que le bot tourne (`python bot.py`)

### Erreur de connexion Supabase
1. Vérifier les clés API
2. Vérifier les RLS policies
3. Tester avec le service role key

### L'audio ne se génère pas
1. Vérifier la clé OpenAI
2. Vérifier les quotas OpenAI
3. Voir les logs du worker

---

## 📄 License

MIT License - Feel free to use and modify!
