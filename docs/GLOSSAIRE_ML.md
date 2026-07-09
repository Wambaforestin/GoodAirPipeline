# Glossaire ML du pipeline GoodAir

Ce document explique tous les concepts statistiques et techniques utilisés lors de la mise en place du modèle de prédiction de l'indice de qualité de l'air.

---

## Statistiques descriptives

### Moyenne

La moyenne est la somme de toutes les valeurs divisée par leur nombre. Elle donne une idée générale du niveau central d'une variable.

**Quand l'utiliser :** La moyenne est fiable quand les données sont homogènes et qu'il n'y a pas de valeurs extrêmes. Par exemple, la température moyenne sur une journée calme est un bon indicateur car les valeurs ne varient pas énormément. En revanche, la moyenne des revenus dans un pays est trompeuse car une poignée de milliardaires la tire vers le haut alors que la majorité de la population gagne beaucoup moins.

**Dans notre projet :** On utilise la moyenne pour avoir une idée générale du niveau de pollution sur la période. La moyenne de l'indice de qualité de l'air est de 39 sur notre dataset, ce qui signifie qu'en général l'air est de bonne qualité sur les 11 villes surveillées. Cependant, le pic à 434 à Paris tire cette moyenne vers le haut, ce qui montre la limite de cet indicateur seul.

---

### Médiane

La médiane est la valeur du milieu quand on trie toutes les valeurs dans l'ordre. La moitié des valeurs est en dessous, l'autre moitié est au-dessus.

**Quand l'utiliser :** La médiane est préférable à la moyenne quand les données contiennent des valeurs aberrantes ou une distribution asymétrique. L'exemple le plus parlant est le prix de l'immobilier : dans un quartier avec quelques propriétés de luxe à 10 millions d'euros, la moyenne des prix sera très élevée et ne représentera pas le prix typique d'un appartement. La médiane, elle, donnera le prix du bien qui se trouve exactement au milieu de tous les biens, ce qui est bien plus représentatif de ce que la plupart des acheteurs vont trouver.

**Dans notre projet :** La médiane de l'indice de qualité de l'air est de 37, très proche de la moyenne de 39. Cela indique que la distribution est relativement équilibrée malgré quelques pics extrêmes. Si la médiane avait été très différente de la moyenne, cela aurait signalé un problème de valeurs aberrantes importantes.

---

### Écart-type

L'écart-type mesure à quel point les valeurs sont dispersées autour de la moyenne. Un écart-type faible signifie que les valeurs sont concentrées près de la moyenne, un écart-type élevé signifie qu'elles sont très dispersées.

**Quand l'utiliser :** On utilise l'écart-type pour comparer la variabilité de deux variables ou de deux groupes. Par exemple, si deux villes ont la même moyenne de température mais des écarts-types différents, la ville avec l'écart-type le plus élevé a des températures plus extrêmes (des hivers plus froids et des étés plus chauds). En machine learning, un écart-type élevé sur les scores de validation croisée signifie que le modèle est instable.

**Dans notre projet :** L'écart-type de l'indice de qualité de l'air est de 18 points, ce qui signifie que la plupart des mesures se situent entre 21 et 57. Les valeurs très loin de cet intervalle sont des candidats potentiels aux outliers. L'écart-type de 0.022 sur les R² de nos trois splits TimeSeriesSplit confirme que notre modèle Random Forest est stable et cohérent.

---

### Min et Max

Le minimum est la valeur la plus basse du dataset, le maximum est la plus haute. Ils définissent l'étendue complète des données.

**Quand l'utiliser :** Le min et le max sont utiles pour détecter les erreurs évidentes et vérifier la cohérence physique des données. Si la température minimum est de -200°C ou si l'humidité maximum dépasse 100%, il y a clairement une erreur de mesure ou de transmission.

**Dans notre projet :** L'indice de qualité de l'air va de 0 à 434. Le minimum de 0 correspond à des heures de très bonne qualité de l'air, le maximum de 434 est un pic exceptionnel à Paris qui représente un vrai épisode de pollution sévère et non une erreur de capteur.

---

### Q1 et Q3 - Les quartiles

Q1 est la valeur en dessous de laquelle se trouvent 25% des données, Q3 est la valeur en dessous de laquelle se trouvent 75% des données. L'écart entre Q1 et Q3 s'appelle l'IQR (intervalle interquartile).

**Quand l'utiliser :** Les quartiles sont utilisés pour comprendre la répartition des données sans être influencé par les valeurs extrêmes. Ils sont particulièrement utiles pour les distributions asymétriques. Dans la finance, les quartiles des rendements permettent de comprendre ce que gagnent la majorité des investisseurs plutôt que de se focaliser sur les performances exceptionnelles de quelques-uns.

**Dans notre projet :** Q1 de l'indice de qualité de l'air est à 27 et Q3 est à 52. Cela signifie que 50% de nos mesures se situent entre 27 et 52, une zone de bonne qualité de l'air. Les valeurs en dehors de cet intervalle sont statistiquement inhabituelles et méritent une attention particulière.

---

### Distribution symétrique vs asymétrique

Une distribution symétrique ressemble à une cloche, avec autant de valeurs à gauche qu'à droite de la moyenne. Une distribution asymétrique à droite a une longue queue vers les valeurs élevées : la majorité des valeurs est basse mais quelques valeurs très élevées tirent la distribution vers la droite.

**Quand l'utiliser :** L'analyse de la distribution est la première étape avant tout modélisation. Elle détermine quels outils statistiques sont appropriés. La régression linéaire suppose une distribution symétrique de la variable cible, donc si la distribution est très asymétrique, il faut soit transformer la variable (log transformation) soit choisir un autre algorithme.

**Dans notre projet :** L'indice de qualité de l'air a une distribution fortement asymétrique à droite. La grande majorité des mesures est entre 0 et 80 mais quelques pics comme 434 créent une longue queue à droite. Cette asymétrie justifie le choix de Random Forest plutôt que la régression linéaire, et explique pourquoi on applique une winsorisation avant l'entraînement.

---

### Boxplot - Boîte à moustaches

Le boxplot est un graphique qui représente visuellement Q1, la médiane, Q3 et les valeurs extrêmes d'une distribution. La boîte centrale contient les 50% des données les plus centrales, les moustaches s'étendent jusqu'aux valeurs extrêmes non aberrantes, et les points isolés au-delà des moustaches sont les outliers.

**Quand l'utiliser :** Le boxplot est idéal pour comparer plusieurs groupes en un seul coup d'œil. Il permet de voir immédiatement quelle ville a l'indice de qualité de l'air le plus élevé, laquelle est la plus stable, et laquelle a le plus de valeurs aberrantes. C'est beaucoup plus efficace que de comparer des tableaux de chiffres.

**Dans notre projet :** Les boxplots ont montré que Paris a la boîte la plus haute avec le plus d'outliers, et que Lyon a la boîte la plus basse car sa station AQICN ne mesure pas tous les polluants. Ces observations ont directement influencé notre compréhension des données avant la modélisation.

---

### Histogramme

L'histogramme découpe l'axe des valeurs en intervalles égaux et compte combien de mesures tombent dans chaque intervalle. La hauteur de chaque barre représente ce nombre.

**Quand l'utiliser :** L'histogramme est le premier graphique à tracer pour comprendre la forme d'une distribution. Il permet de voir immédiatement si les données sont symétriques, asymétriques, bimodales (deux pics) ou uniformes. Il aide à décider si une transformation est nécessaire avant la modélisation.

**Dans notre projet :** Les histogrammes ont montré que l'indice de qualité de l'air est très concentré entre 0 et 100, avec quelques barres quasi invisibles au-delà. Cela confirme que les dépassements du seuil d'alerte de 100 sont des événements rares représentant seulement 0.2% du dataset.

---

### Matrice de corrélation

La matrice de corrélation mesure la relation linéaire entre chaque paire de variables. Elle va de -1 à 1, où 1 signifie que quand une variable monte l'autre monte proportionnellement, -1 signifie que quand une variable monte l'autre descend, et 0 signifie qu'il n'y a pas de relation linéaire entre les deux variables.

**Quand l'utiliser :** La matrice de corrélation est utilisée en début de projet pour identifier les variables les plus prometteuses pour prédire la variable cible, et pour détecter la multicolinéarité (deux variables qui mesurent quasiment la même chose). Si deux features sont corrélées à 0.95, garder les deux n'apporte pas d'information supplémentaire et peut déstabiliser certains modèles.

**Dans notre projet :** PM25 et l'indice de qualité de l'air ont une corrélation de 0.76, ce qui en fait la feature la plus prometteuse. La température et l'humidité ont une corrélation de -0.67, une relation physique normale. Il est important de noter qu'une corrélation proche de 0 ne signifie pas que deux variables sont indépendantes : elles peuvent avoir une relation non linéaire que la corrélation de Pearson ne détecte pas, ce qui est précisément pourquoi on utilise Random Forest plutôt que la régression linéaire.

---

## Gestion des données

### Valeurs NULL légitimes vs erreurs

Toutes les valeurs NULL ne sont pas des erreurs. Dans notre projet, certaines stations AQICN ne disposent pas de capteurs pour mesurer tous les polluants : Lyon n'a pas de capteur PM25 ni O3, Franconville n'a pas de capteur O3. Ces NULL sont légitimes car ils signifient simplement que la donnée n'existe pas pour cette ville.

**Quand les conserver vs les imputer :** On conserve les NULL quand ils ont une signification physique réelle et qu'on utilise des algorithmes qui les gèrent nativement comme Random Forest et XGBoost. On les impute uniquement quand la donnée est manquante pour des raisons techniques (panne réseau ponctuelle) et qu'on dispose d'une méthode d'imputation fiable. Imputer des NULL légitimes, c'est fabriquer de la donnée qui n'a pas été mesurée, ce qui biaise le modèle.

---

### Trous temporels

Un trou temporel est une période où le pipeline n'a pas collecté de données. Dans notre projet, ces trous correspondent aux heures où l'ordinateur personnel hébergeant le pipeline était en veille ou éteint. Les trous temporels ont deux impacts importants : ils rendent les features de lag inutilisables et ils imposent d'utiliser TimeSeriesSplit plutôt qu'un split aléatoire pour l'évaluation du modèle.

---

### Outliers - Valeurs aberrantes

Un outlier est une valeur très éloignée des autres valeurs du dataset. Il peut être une erreur de mesure ou un événement réel exceptionnel. Dans notre projet, le pic d'indice de qualité de l'air à 434 à Paris est un outlier réel qui correspond à un vrai épisode de pollution sévère. On ne le supprime pas mais on le bride via la winsorisation car sa présence brute rendrait l'apprentissage du modèle instable.

---

### IQR - Intervalle interquartile

L'IQR est la différence entre Q3 et Q1. Il représente l'étendue des 50% centraux des données et sert à détecter les outliers avec la règle suivante : une valeur est considérée comme outlier si elle est inférieure à Q1 - 1.5 × IQR ou supérieure à Q3 + 1.5 × IQR.

**Quand l'utiliser :** L'IQR est préférable au Z-score pour détecter les outliers dans les distributions asymétriques, car il ne fait aucune hypothèse sur la forme de la distribution. Dans notre projet, l'IQR de l'indice de qualité de l'air est de 25 (52 - 27) et la borne supérieure est de 89.5. Toute valeur au-dessus est un outlier statistique.

---

### Winsorisation

La winsorisation consiste à brider les valeurs extrêmes en les remplaçant par les percentiles limites, au lieu de les supprimer. Dans notre projet, on applique une winsorisation à 1% et 99% : le pic à 434 est ramené à 76.

**Quand l'utiliser :** On choisit la winsorisation quand les valeurs extrêmes sont réelles mais perturbent l'apprentissage du modèle. On choisit la suppression quand les valeurs extrêmes sont clairement des erreurs. Dans notre cas, le pic à 434 est un vrai épisode de pollution, donc on le bride plutôt que de le supprimer.

---

### Bootstrapping

Le bootstrapping est une technique statistique qui consiste à tirer aléatoirement des échantillons avec remplacement depuis le dataset pour estimer l'incertitude d'une statistique. Dans notre projet, on l'utilise pour vérifier si les outliers de l'indice de qualité de l'air sont influents sur la moyenne. On calcule la moyenne avec et sans les outliers sur 1000 échantillons aléatoires et on compare les intervalles de confiance à 95%.

---

### Test de permutation

Le test de permutation est une méthode statistique qui vérifie si la différence observée entre deux groupes est réelle ou due au hasard. On mélange aléatoirement les étiquettes des deux groupes des milliers de fois et on regarde si la différence observée est exceptionnelle comparée aux différences obtenues par hasard. Dans notre projet, la p-value obtenue en comparant mars et juin est de 0.002 : la différence entre les mois est statistiquement significative et Mois est une feature pertinente pour le modèle.

---

### Z-score - Pourquoi on ne l'a pas utilisé

Le Z-score mesure à combien d'écarts-types une valeur se trouve de la moyenne, et une valeur avec un Z-score supérieur à 3 est généralement considérée comme outlier. On ne l'a pas utilisé car il suppose que les données suivent une distribution normale, ce qui n'est pas le cas de notre indice de qualité de l'air fortement asymétrique. L'IQR est plus robuste que le Z-score pour ce type de distribution.

---

### Ground Truth

Le Ground Truth désigne les données réelles mesurées, par opposition aux données estimées ou prédites. Dans notre projet, on a délibérément choisi de ne pas imputer les valeurs manquantes et de ne pas interpoler les trous temporels, pour que notre dataset d'entraînement soit composé à 100% de Ground Truth. Un modèle entraîné sur des données fabriquées apprend à prédire ces données fabriquées et non la réalité.

---

## Feature Engineering

### Encodage cyclique sin/cos

Certaines variables sont cycliques : leur valeur maximale et leur valeur minimale sont en réalité proches l'une de l'autre. L'heure est cyclique car 23h et 0h sont séparées d'une seule heure mais numériquement leur différence est de 23. La direction du vent est cyclique car 359° (presque Nord) et 1° (presque Nord aussi) sont physiquement proches mais numériquement éloignés de 358 degrés. La solution est d'encoder ces variables avec sin et cos sur leur période naturelle, ce qui représente ces variables sur un cercle et capture correctement leur nature cyclique.

**Dans notre projet :** On applique cet encodage à l'heure (période 24), au mois (période 12) et à la direction du vent (période 360°). Sans cet encodage, le modèle aurait cru que minuit et 23h sont très éloignés, ce qui est faux.

---

### One-Hot Encoding

Le One-Hot Encoding transforme une variable catégorielle en plusieurs colonnes binaires, une par catégorie. Chaque ligne a un 1 dans la colonne correspondant à sa catégorie et des 0 dans toutes les autres.

**Quand l'utiliser :** Le One-Hot Encoding est adapté aux variables nominales sans ordre naturel entre les catégories. On l'utilise pour NomVille car les villes n'ont pas de relation ordinale : Paris n'est pas numériquement supérieure à Lyon. Si on attribuait un numéro à chaque ville, le modèle croirait qu'il existe une relation mathématique entre elles, ce qui n'a aucun sens.

---

### Label Encoding - Pourquoi on ne l'a pas utilisé

Le Label Encoding attribue un nombre entier à chaque catégorie. Il est adapté aux variables ordinales où l'ordre a un sens, comme les niveaux de qualité (Bon=0, Moyen=1, Mauvais=2). Pour NomVille, il n'est pas approprié car les villes n'ont pas d'ordre naturel, ce qui est pourquoi on utilise le One-Hot Encoding à la place.

---

### Log transformation - Pourquoi on ne l'a pas appliquée

La log transformation compresse les grandes valeurs pour rendre une distribution asymétrique plus symétrique. Elle est très utile pour la régression linéaire qui suppose une distribution symétrique de la variable cible. Dans notre projet, on ne l'applique pas sur l'indice de qualité de l'air car on utilise Random Forest et XGBoost, deux algorithmes complètement insensibles à la distribution de la variable cible. Ces algorithmes découpent les données en partitions et ne font aucune hypothèse sur la forme de la distribution.

---

### AQI\_mean\_6h - La feature la plus importante

AQI\_mean\_6h est la moyenne de l'indice de qualité de l'air sur les 6 dernières heures disponibles. C'est une feature construite à partir de nos propres données historiques et elle représente 71.7% de l'importance du modèle. La raison est simple : la qualité de l'air évolue lentement, et si l'indice était à 40 il y a 3 heures, il a peu de chances d'être à 200 maintenant. Elle est calculée avec un rolling sur index datetime plutôt que sur un comptage de lignes, pour gérer correctement les trous temporels.

---

### Rolling\_mean\_24h et Lag features - Pourquoi on ne les a pas utilisés

Les lag features utilisent les valeurs passées d'une variable comme features : AQI\_lag\_1 serait l'indice de l'heure précédente, rolling\_mean\_24h serait la moyenne sur les 24 dernières heures. On ne les utilise pas car nos trous temporels les rendraient peu fiables : si le pipeline était éteint pendant 12 heures, AQI\_lag\_1 contiendrait une valeur vieille de 12 heures présentée comme si c'était la valeur de l'heure précédente, ce qui introduirait du bruit plutôt que du signal.

---

### Data Leakage - La fuite de données

Le Data Leakage se produit quand on donne au modèle des informations qui ne seraient pas disponibles en production. Le modèle apprend à tricher plutôt qu'à vraiment prédire. Dans notre projet, PM25, PM10, NO2 et O3 sont corrélés avec l'indice de qualité de l'air car ce sont ses composantes directes. Les utiliser comme features reviendrait à donner la réponse au modèle car en production, on ne connaît pas les valeurs futures de ces polluants.

L'analogie avec l'immobilier : c'est comme créer un modèle pour prédire le prix de vente d'un appartement demain, et donner comme feature le prix de vente réel de demain. Le modèle aurait 100% de précision mais n'aurait rien prédit du tout.

---

### Binarisation

La binarisation transforme une variable continue en variable binaire 0 ou 1. Dans notre projet, on binarise les précipitations car plus de 75% des heures ont 0 mm de précipitation. La valeur continue (0.1 mm, 2.3 mm, 11 mm) apporte peu d'information supplémentaire par rapport au simple fait qu'il pleut ou non, et la binarisation capture mieux l'effet "lavage de l'air" que produit la pluie sur les polluants.

---

## Modélisation

### Overfitting - Surapprentissage

L'overfitting se produit quand le modèle apprend trop précisément les données d'entraînement, y compris leur bruit et leurs particularités, et qu'il échoue à généraliser sur de nouvelles données. Le signe caractéristique est un R² très élevé sur les données d'entraînement et un R² faible sur les données de test. Dans notre projet, on prévient l'overfitting avec max\_depth=12 pour Random Forest, min\_samples\_leaf=5, max\_features=0.5 et l'évaluation via TimeSeriesSplit.

---

### Underfitting - Sous-apprentissage

L'underfitting se produit quand le modèle est trop simple pour capturer les patterns dans les données, et qu'il performe mal aussi bien sur les données d'entraînement que sur les nouvelles données. Le signe caractéristique est un R² faible sur les deux. Dans notre projet, un R² en dessous de 0.5 sur les splits d'entraînement serait un signe d'underfitting. Ce n'est pas notre cas avec R²=0.87.

---

### TimeSeriesSplit

TimeSeriesSplit est une méthode de validation croisée adaptée aux données temporelles. Elle garantit que le modèle est toujours entraîné sur le passé pour être évalué sur le futur, ce qui est indispensable pour des données où l'ordre chronologique a un sens. Un split aléatoire mélangerait passé et futur, ce qui revient à permettre au modèle d'utiliser des données futures pendant l'entraînement, une situation impossible en production.

---

### R² - Coefficient de détermination

Le R carré mesure la proportion de la variance de la variable cible expliquée par le modèle. Il va de 0 à 1, où 0 signifie que le modèle n'est pas meilleur qu'une prédiction par la moyenne, et 1 signifie que le modèle prédit parfaitement. Notre modèle atteint R²=0.87, ce qui signifie qu'il explique 87% de la variance de l'indice de qualité de l'air. La fiche d'évaluation EPSI exige R² > 0.5.

---

### MAE - Erreur Absolue Moyenne

Le MAE est la moyenne des erreurs absolues entre les prédictions et les valeurs réelles. Il s'exprime dans la même unité que la variable cible, ce qui le rend très intuitif à interpréter. Dans notre projet, MAE=4.25 points d'indice de qualité de l'air signifie qu'en moyenne notre modèle se trompe de 4.25 points, ce qui représente une erreur de moins de 5% sur les valeurs normales.

---

### RMSE - Racine de l'Erreur Quadratique Moyenne

Le RMSE pénalise davantage les grosses erreurs que le MAE : une erreur de 20 compte 4 fois plus qu'une erreur de 10. Dans notre projet, RMSE=6.42. L'écart modéré entre MAE (4.25) et RMSE (6.42) indique que les grosses erreurs sont rares mais existent, ce qui signifie que le modèle est globalement précis mais peut parfois se tromper plus significativement sur des situations inhabituelles.

---

### Faux positifs et faux négatifs

Dans le contexte de notre règle d'alerte (indice prédit > 100 = ALERTE) : un faux positif est une alerte déclenchée alors qu'il n'y a pas de vrai épisode de pollution (le modèle dit ALERTE mais la réalité est OK), et un faux négatif est une alerte non déclenchée alors qu'il y a un vrai épisode de pollution (le modèle dit OK mais la réalité est ALERTE). Dans un contexte santé et environnement, les faux négatifs sont plus graves que les faux positifs car manquer une vraie alerte de pollution peut avoir des conséquences sur la santé des populations. On préfère prévenir trop que pas assez.

---

### Malédiction de la dimensionnalité

La malédiction de la dimensionnalité désigne le phénomène où l'ajout de trop de features par rapport au nombre de lignes rend l'apprentissage difficile car l'espace des données devient trop grand. Dans notre projet, on a 25 features pour 10526 lignes, soit un ratio de 421 lignes par feature, largement suffisant. La malédiction commence à poser problème quand ce ratio descend en dessous de 10.

---

### Régression linéaire - Pourquoi on ne l'a pas choisie

La régression linéaire suppose qu'il existe une relation directe et proportionnelle entre chaque feature et la variable cible. Elle ne peut pas capturer les interactions entre variables ni les relations non linéaires. Dans notre projet, l'effet du vent sur l'indice de qualité de l'air dépend de la ville, de la saison et de l'heure, ce que la régression linéaire ne peut pas modéliser. De plus, notre variable cible est asymétrique et contient des valeurs extrêmes qui déstabilisent la régression linéaire.

---

### Modèles de séries temporelles - Pourquoi on ne les a pas choisis

ARIMA, SARIMA et Prophet prédisent une variable à partir de ses propres valeurs passées uniquement, sans pouvoir exploiter naturellement des variables complémentaires comme la météo. De plus, ils exigent une série temporelle continue sans trous, ce qui est incompatible avec notre infrastructure locale qui génère des discontinuités régulières.

---

### Random Forest vs XGBoost

Random Forest construit plusieurs centaines d'arbres de décision indépendants en parallèle et fait la moyenne de leurs prédictions. Cette approche par consensus est naturellement robuste sur des petits datasets avec des trous temporels. XGBoost construit les arbres de manière séquentielle, chaque arbre corrigeant les erreurs du précédent : très puissant sur de grands datasets mais moins efficace quand les données sont limitées. Sur notre dataset de 3 mois, Random Forest (R²=0.87) surpasse XGBoost (R²=0.81). Sur un historique de 2 ans avec des données continues, XGBoost aurait probablement été plus performant.

---

## Stratégies et compromis

### Biais de saisonnalité

Notre dataset couvre uniquement mars à juillet 2026, principalement le printemps et le début de l'été. Le modèle a donc appris les patterns de cette période et ses prédictions en hiver ou en automne seront moins fiables car il n'a jamais vu des données hivernales. C'est un biais assumé et documenté : le Continuous Training trimestriel permettra progressivement de couvrir toutes les saisons.

---

### Continuous Training

Le Continuous Training est la pratique de ré-entraîner régulièrement le modèle sur de nouvelles données pour qu'il reste à jour. Dans notre projet, on prévoit un ré-entraînement manuel tous les 3 mois via les notebooks. À chaque ré-entraînement, le modèle verra plus de données, plus de saisons et plus d'épisodes de pollution, ce qui améliorera progressivement ses prédictions.

---

### Points de vigilance

**Horizon de prédiction de 6 heures :** Notre modèle prédit l'évolution de l'indice de qualité de l'air à 6 heures en se basant sur son historique récent et les conditions météo. Il ne recalcule pas l'indice depuis les polluants bruts, et les prédictions au-delà de 6 heures nécessiteraient une architecture différente.

**Dépendance à AQI\_mean\_6h :** La feature la plus importante du modèle est l'historique récent de l'indice. Si le pipeline a des trous temporels importants, cette feature sera moins précise et les prédictions le seront aussi.

**Événements exceptionnels :** Le modèle ne peut pas prédire un pic de pollution lié à un événement imprévu comme un incendie ou un épisode de pollution transfrontalière, car ces événements ne sont pas capturés par les variables météo.

**Saisonnalité limitée :** Le modèle est entraîné sur le printemps et le début de l'été. Les prédictions en hiver ou en automne seront moins fiables jusqu'au prochain ré-entraînement.
