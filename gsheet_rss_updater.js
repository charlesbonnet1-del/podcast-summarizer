/**
 * Script Google Apps Script pour mettre à jour les flux RSS dans la colonne D
 * basé sur le source_name de la colonne B
 *
 * Instructions:
 * 1. Ouvrir Google Sheets
 * 2. Extensions > Apps Script
 * 3. Coller ce code
 * 4. Exécuter la fonction updateRSSFeeds()
 */

function updateRSSFeeds() {
  // Mapping source_name -> RSS URL (flux testés et fonctionnels)
  const RSS_MAPPING = {
    // ASIA
    "Nikkei": "https://asia.nikkei.com/rss/feed/nar",
    "Nikkei Asia": "https://asia.nikkei.com/rss/feed/nar",
    "The Ken": "https://the-ken.com/feed/",
    "Global Taiwan Institute": "https://globaltaiwan.org/feed/",
    "Panda Daily": "https://pandaily.com/feed/",
    "Pandaily": "https://pandaily.com/feed/",
    "New Bloom Magazine": "https://newbloommag.net/feed/",
    "ChinaTalk": "https://www.chinatalk.media/feed",
    "China Project": "https://thechinaproject.com/feed/",
    "Al-Monitor": "https://www.al-monitor.com/feed",

    // ATTENTION / MEDIA
    "Journalism.co.uk": "https://www.journalism.co.uk/feed/",
    "Shane Parrish": "https://fs.blog/feed/",
    "Farnam Street": "https://fs.blog/feed/",
    "Nieman Lab": "https://www.niemanlab.org/feed/",
    "The Hollywood Reporter": "https://www.hollywoodreporter.com/feed/",
    "Hollywood Reporter": "https://www.hollywoodreporter.com/feed/",
    "Casey Newton": "https://www.platformer.news/rss/",
    "Platformer": "https://www.platformer.news/rss/",

    // CRYPTO
    "Sygnum Bank": "https://www.sygnum.com/feed/",
    "Balaji Srinivasan": "https://balajis.com/feed/",
    "Naval Ravikant": "https://nav.al/feed",
    "David Hoffman": "https://davidhoffman.substack.com/feed",
    "Anthony Pompliano": "https://pomp.substack.com/feed",
    "Jesse Walden": "https://variant.fund/feed/",

    // CYBER
    "Brian Krebs": "https://krebsonsecurity.com/feed/",
    "Krebs on Security": "https://krebsonsecurity.com/feed/",
    "Have I Been Pwned": "https://www.troyhunt.com/rss/",
    "Troy Hunt": "https://www.troyhunt.com/rss/",
    "SANS Internet Storm Center": "https://isc.sans.edu/rssfeed.xml",
    "SANS ISC": "https://isc.sans.edu/rssfeed.xml",
    "Exploit-DB": "https://www.exploit-db.com/rss.xml",
    "The Hacker News": "https://feeds.feedburner.com/TheHackersNews",
    "InfoSecurity Magazine": "https://www.infosecurity-magazine.com/rss/news/",
    "Infosecurity Magazine": "https://www.infosecurity-magazine.com/rss/news/",
    "Pierluigi Paganini": "https://securityaffairs.com/feed",
    "Security Affairs": "https://securityaffairs.com/feed",
    "Katie Moussouris": "https://www.lutasecurity.com/blog-feed.xml",
    "Robert M. Lee": "https://www.robertmlee.org/feed/",
    "Graham Cluley": "https://grahamcluley.com/feed/",
    "CERT-FR": "https://www.cert.ssi.gouv.fr/feed/",
    "L'Agence nationale de la sécurité des systèmes d'information": "https://www.cert.ssi.gouv.fr/feed/",
    "ANSSI": "https://www.cert.ssi.gouv.fr/feed/",

    // DEALS / VC
    "Fred Wilson": "https://avc.com/feed/",
    "AVC": "https://avc.com/feed/",
    "Bill Gurley": "https://abovethecrowd.com/feed/",
    "Above the Crowd": "https://abovethecrowd.com/feed/",
    "Lenny Rachitsky": "https://www.lennysnewsletter.com/feed",
    "Lenny's Newsletter": "https://www.lennysnewsletter.com/feed",
    "Mario Gabriele": "https://www.generalist.com/feed",
    "The Generalist": "https://www.generalist.com/feed",
    "Marc Andreessen": "https://pmarca.substack.com/feed",
    "Packy McCormick": "https://www.notboring.co/feed",
    "Not Boring": "https://www.notboring.co/feed",
    "CB Insights": "https://www.cbinsights.com/research/feed/",
    "TechCrunch Startups": "https://techcrunch.com/category/startups/feed/",

    // DEEP TECH / SCIENCE
    "CNRS Journal": "https://lejournal.cnrs.fr/rss",
    "CNRS": "https://lejournal.cnrs.fr/rss",
    "EuroFusion": "https://euro-fusion.org/feed/",
    "MIT Tech Review": "https://www.technologyreview.com/feed/",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
    "Opinions Libres": "https://www.oezratty.net/wordpress/feed/",
    "Olivier Ezratty": "https://www.oezratty.net/wordpress/feed/",
    "Techniques de l'Ingénieur": "https://www.techniques-ingenieur.fr/actualite/feed/",
    "Tech. Ingénieur": "https://www.techniques-ingenieur.fr/actualite/feed/",
    "World Nuclear News": "https://www.world-nuclear-news.org/rss",
    "Hello Tomorrow": "https://hello-tomorrow.org/feed/",
    "Sifted": "https://sifted.eu/feed",
    "Sifted - Deep Tech": "https://sifted.eu/feed",
    "Infleqtion": "https://www.infleqtion.com/feed/",
    "L'Usine Nouvelle": "https://www.usinenouvelle.com/rss/",
    "Quantum Dice": "https://www.quantum-dice.com/feed/",
    "Futura Sciences": "https://www.futura-sciences.com/rss/actualites.xml",
    "Quanta Magazine": "https://www.quantamagazine.org/feed",
    "Semiconductor Digest": "https://www.semiconductor-digest.com/feed/",
    "WikiChip": "https://fuse.wikichip.org/feed/",

    // SCIENCE BLOGGERS
    "Derek Lowe": "https://www.science.org/blogs/pipeline/feed",
    "In the Pipeline": "https://www.science.org/blogs/pipeline/feed",
    "Sabine Hossenfelder": "https://backreaction.blogspot.com/feeds/posts/default",
    "Brian Wang": "https://www.nextbigfuture.com/feed",
    "Next Big Future": "https://www.nextbigfuture.com/feed",
    "Kevin Kelly": "https://kk.org/cooltools/feed/",

    // ENERGY
    "Energy Storage News": "https://www.energy-storage.news/rss/",
    "H2 View": "https://h2-view.com/feed/",
    "Offshore Energy": "https://www.offshore-energy.biz/feed/",
    "David Roberts": "https://www.volts.wtf/feed",
    "Volts": "https://www.volts.wtf/feed",

    // HEALTH
    "Endpoints News": "https://endpts.com/feed/",
    "FierceHealthCare": "https://www.fiercehealthcare.com/rss/xml",
    "FierceHelathCare": "https://www.fiercehealthcare.com/rss/xml",
    "Medical Device and Diagnostic Industry": "https://www.mddionline.com/rss.xml",
    "MD+DI": "https://www.mddionline.com/rss.xml",
    "The Medical Futurist": "https://medicalfuturist.com/feed/",
    "DNA Script": "https://www.dnascript.com/feed/",
    "Healthcare Dive": "https://www.healthcaredive.com/feeds/news/",

    // AI COMPANIES
    "Nvidia": "https://developer.nvidia.com/blog/feed/",
    "NVIDIA": "https://developer.nvidia.com/blog/feed/",
    "Demis Hassabis": "https://deepmind.google/blog/feed/",
    "DeepMind": "https://deepmind.google/blog/feed/",
    "AMD": "https://ir.amd.com/rss/news-releases.xml",
    "Intel": "https://newsroom.intel.com/feed/",
    "Planète Robots": "https://www.planeterobots.com/feed/",
    "Oxford Internet Institute": "https://www.oii.ox.ac.uk/blog/feed/",

    // AI RESEARCHERS
    "Sam Altman": "https://blog.samaltman.com/posts.atom",
    "Andrej Karpathy": "https://karpathy.github.io/feed.xml",
    "Sebastian Raschka": "https://magazine.sebastianraschka.com/feed",
    "Ahead of AI": "https://magazine.sebastianraschka.com/feed",
    "Francois Chollet": "https://fchollet.substack.com/feed",
    "François Chollet": "https://fchollet.substack.com/feed",
    "Nathan Benaich": "https://nathanbenaich.substack.com/feed",
    "Alberto Romero": "https://thealgorithmicbridge.substack.com/feed",
    "The Algorithmic Bridge": "https://thealgorithmicbridge.substack.com/feed",
    "Dylan Patel": "https://www.semianalysis.com/feed",
    "SemiAnalysis": "https://www.semianalysis.com/feed",
    "Doug O'Laughlin": "https://www.fabricatedknowledge.com/feed",
    "Fabricated Knowledge": "https://www.fabricatedknowledge.com/feed",
    "Import AI": "https://importai.substack.com/feed",
    "Import AI (Jack Clark)": "https://importai.substack.com/feed",
    "Jack Clark": "https://importai.substack.com/feed",
    "The Gradient": "https://thegradient.pub/rss/",
    "Last Week in AI": "https://lastweekin.ai/feed",
    "Davis Summarizes Papers": "https://dblalock.substack.com/feed",
    "AI Snake Oil": "https://www.aisnakeoil.com/feed",
    "LessWrong": "https://www.lesswrong.com/feed.xml",
    "LessWrong AI": "https://www.lesswrong.com/feed.xml",
    "MIRI Blog": "https://intelligence.org/feed/",
    "MIRI": "https://intelligence.org/feed/",
    "AI Alignment Newsletter": "https://rohinshah.com/alignment-newsletter/feed/",
    "Machine Learning Mastery": "https://machinelearningmastery.com/feed/",
    "Chip Huyen": "https://huyenchip.com/feed.xml",

    // POLICY / REGULATION
    "La Quadrature du Net": "https://www.laquadrature.net/feed/",
    "EU DisinfoLab": "https://www.disinfo.eu/feed/",
    "EFF Deeplinks": "https://www.eff.org/rss/updates.xml",
    "EFF": "https://www.eff.org/rss/updates.xml",
    "Berkman Klein Center": "https://medium.com/feed/berkman-klein-center",
    "Center for Democracy & Tech": "https://cdt.org/feed/",

    // MACRO / ECONOMICS
    "Tyler Cowen": "https://marginalrevolution.com/feed",
    "Marginal Revolution": "https://marginalrevolution.com/feed",
    "Scott Sumner": "https://www.themoneyillusion.com/feed/",
    "The Money Illusion": "https://www.themoneyillusion.com/feed/",
    "Ben Thompson": "https://stratechery.com/feed/",
    "Stratechery": "https://stratechery.com/feed/",
    "Joseph Politano": "https://apricitas.substack.com/feed",
    "Apricitas Economics": "https://apricitas.substack.com/feed",
    "Adam Tooze": "https://adamtooze.substack.com/feed",
    "Adam Tooze Chartbook": "https://adamtooze.substack.com/feed",
    "Chartbook": "https://adamtooze.substack.com/feed",

    // MARKETING
    "Seth Godin": "https://seths.blog/feed/",

    // GENERAL NEWS
    "L'Usine Digitale": "https://www.usine-digitale.fr/rss",
    "Usine Digitale": "https://www.usine-digitale.fr/rss",
    "Tim O'Reilly": "https://www.oreilly.com/radar/feed/",
    "O'Reilly Radar": "https://www.oreilly.com/radar/feed/",
    "Teslarati": "https://www.teslarati.com/feed/",
    "Robert Zubrin": "https://www.marssociety.org/feed/",
    "Mars Society": "https://www.marssociety.org/feed/",
    "Wall Street Journal": "https://feeds.a.dj.com/rss/RSSWSJD.xml",
    "The Wall Street Journal": "https://feeds.a.dj.com/rss/RSSWSJD.xml",
    "WSJ": "https://feeds.a.dj.com/rss/RSSWSJD.xml",
    "Sky News": "https://feeds.skynews.com/feeds/rss/technology.xml",
    "Sky News (Tech)": "https://feeds.skynews.com/feeds/rss/technology.xml",
    "La Nación": "https://www.lanacion.com.ar/arc/outboundfeeds/rss/category/tecnologia/",
    "La Nación (Tecno - ARG)": "https://www.lanacion.com.ar/arc/outboundfeeds/rss/category/tecnologia/",
    "Japan Times": "https://www.japantimes.co.jp/feed/",
    "Japan Times (Tech)": "https://www.japantimes.co.jp/feed/",
    "The Japan Times": "https://www.japantimes.co.jp/feed/",
    "Hacker News": "https://news.ycombinator.com/rss",
    "Axios": "https://api.axios.com/feed/",
    "Rest of World": "https://restofworld.org/feed/",
    "Maddyness": "https://www.maddyness.com/feed/",
    "ActuIA": "https://www.actuia.com/feed/",

    // SPACE
    "Payload Space": "https://payloadspace.com/feed/",

    // PODCASTS (YouTube RSS)
    "Huberman Labs": "https://feeds.megaphone.fm/hubermanlab",
    "Andrew Huberman": "https://feeds.megaphone.fm/hubermanlab",
  };

  // Récupérer la feuille active
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();

  // Récupérer toutes les données
  const lastRow = sheet.getLastRow();
  const sourceNames = sheet.getRange("B2:B" + lastRow).getValues();
  const existingRSS = sheet.getRange("D2:D" + lastRow).getValues();

  let updatedCount = 0;
  let skippedCount = 0;
  let notFoundCount = 0;
  const notFoundSources = [];

  // Parcourir chaque ligne
  for (let i = 0; i < sourceNames.length; i++) {
    const sourceName = sourceNames[i][0];
    const currentRSS = existingRSS[i][0];

    // Ignorer si vide
    if (!sourceName) continue;

    // Ignorer si RSS déjà présent et valide
    if (currentRSS && currentRSS.toString().trim().startsWith("http")) {
      skippedCount++;
      continue;
    }

    // Chercher le RSS dans le mapping
    const rssUrl = RSS_MAPPING[sourceName] || RSS_MAPPING[sourceName.trim()];

    if (rssUrl) {
      // Mettre à jour la cellule D
      sheet.getRange("D" + (i + 2)).setValue(rssUrl);
      updatedCount++;
    } else {
      notFoundCount++;
      notFoundSources.push(sourceName);
    }
  }

  // Afficher le résumé
  let message = `✅ Mise à jour terminée!\n\n`;
  message += `📝 ${updatedCount} RSS ajoutés\n`;
  message += `⏭️ ${skippedCount} déjà présents (ignorés)\n`;
  message += `❌ ${notFoundCount} non trouvés`;

  if (notFoundSources.length > 0 && notFoundSources.length <= 20) {
    message += `:\n${notFoundSources.join(", ")}`;
  }

  SpreadsheetApp.getUi().alert(message);
}

/**
 * Ajoute un menu personnalisé au chargement
 */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('🔄 RSS Tools')
    .addItem('Mettre à jour les flux RSS', 'updateRSSFeeds')
    .addToUi();
}
