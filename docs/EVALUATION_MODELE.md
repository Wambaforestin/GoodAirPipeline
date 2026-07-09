# Évaluation du Modèle GoodAir - Points forts, Vigilances et Perspectives

Ceci est une synthèse des forces de notre modèle Random Forest, ses limites connues et assumées, les stratégies d'amélioration envisagées (manuelles et automatiques), ainsi que les cas d'usage complémentaires que l'architecture actuelle permet de dériver.

---

## Points forts du modèle

**R² de 0.87 sur la période de test**
Notre modèle explique 87% de la variance de l'indice de qualité de l'air sur la période juin-juillet 2026, qui est la période la plus récente et donc la plus représentative de la situation en production. Ce résultat dépasse largement l'exigence de R² > 0.5 fixée par la fiche d'évaluation.

**Stabilité entre les splits**
L'écart-type du R² entre les 3 splits temporels est de 0.022, ce qui est très faible. Cela signifie que le modèle est cohérent et ne dépend pas d'une période particulière pour bien performer. Un modèle instable avec un écart-type élevé serait difficile à faire confiance en production.

**Erreur moyenne de 4.25 points**
Le MAE de 4.25 points signifie qu'en moyenne le modèle se trompe de moins de 5 points sur un indice qui va de 0 à 100 pour les valeurs normales. C'est une précision suffisante pour un système d'alerte préventive.

**Robustesse aux données manquantes**
Random Forest gère nativement les valeurs NULL, ce qui est indispensable dans notre contexte où certaines villes comme Lyon n'ont pas de capteurs pour tous les polluants. Aucune imputation artificielle n'a été nécessaire.

**Explicabilité via la feature importance**
Random Forest fournit nativement l'importance de chaque feature dans les prédictions. Cela permet aux chercheurs de GoodAir de comprendre quelles variables météo influencent le plus l'indice de qualité de l'air, ce qui a une valeur scientifique en plus de la valeur opérationnelle.

**Intégration transparente dans le pipeline**
Le modèle est intégré directement dans Airflow sans infrastructure supplémentaire. Chaque run horaire génère 66 prédictions (11 villes × 6 heures) et les stocke dans le Data Warehouse sans intervention humaine.

---

## Points de vigilance

**Horizon de prédiction limité à 6 heures**
Notre modèle prédit l'évolution de l'indice de qualité de l'air à 6 heures en se basant sur son historique récent et les conditions météo. Il ne recalcule pas l'indice depuis les polluants bruts. Les prédictions au-delà de 6 heures nécessiteraient une architecture différente car la feature AQI\_mean\_6h ne serait plus disponible sans prédire d'abord les heures intermédiaires.

**Dépendance forte à AQI\_mean\_6h**
Cette feature représente 71.7% de l'importance du modèle. Si le pipeline ETL a des trous temporels importants (par exemple plusieurs heures d'absence), la moyenne glissante sera calculée sur des données plus anciennes que prévu et les prédictions seront moins précises. La qualité des prédictions dépend donc directement de la disponibilité du pipeline de collecte.

**Biais de saisonnalité**
Notre dataset couvre uniquement mars à juillet 2026, principalement le printemps et le début de l'été. Le modèle a appris les patterns de cette période et ses prédictions en hiver ou en automne seront moins fiables car il n'a jamais vu des données hivernales. C'est un biais assumé qui sera progressivement corrigé par le Continuous Training.

**Événements exceptionnels non prédictibles**
Le modèle ne peut pas détecter un pic de pollution lié à un événement imprévu comme un incendie, une explosion industrielle ou un épisode de pollution transfrontalière venant d'un autre pays. Ces événements ne sont pas capturés par les variables météo et sortent complètement des patterns appris par le modèle.

**Alertes rares dans les données d'entraînement**
Les dépassements du seuil d'alerte de 100 représentent seulement 0.2% du dataset (24 cas sur 10 526 lignes). Le modèle a très peu d'exemples de situations d'alerte pour apprendre à les détecter. La précision des alertes s'améliorera naturellement à mesure que le pipeline collecte plus de données sur le long terme.

---

## Stratégies d'amélioration

### Amélioration manuelle - Continuous Training

Le Continuous Training consiste à ré-entraîner régulièrement le modèle sur un dataset enrichi avec les nouvelles données collectées. Dans notre projet, on prévoit un ré-entraînement manuel tous les 3 mois via les notebooks de modélisation.

**Processus manuel :**

1. Exporter le nouvel historique depuis Gold.FactMesures
2. Télécharger les nouvelles données Open-Meteo Archive pour la période
3. Relancer les notebooks 03 (EDA combined), 04 (data preparation) et 05 (modeling)
4. Comparer le nouveau R² avec le R² actuel
5. Si le nouveau modèle est meilleur, remplacer `aqi_model.pkl` dans `src/ml/models/`
6. Redéployer via `docker compose up -d`

À chaque ré-entraînement, le modèle verra plus de données, plus de saisons et plus d'épisodes de pollution, ce qui améliorera progressivement ses prédictions.

---

### Amélioration automatique - DockerOperator Airflow

Pour automatiser le Continuous Training, on peut ajouter un DAG Airflow dédié qui s'exécute tous les 3 mois et utilise le `DockerOperator` pour lancer l'entraînement dans un conteneur isolé.

**Principe du DockerOperator :**

Le DockerOperator est un opérateur Airflow qui lance un conteneur Docker à la demande, exécute un script Python à l'intérieur, et récupère le résultat. Cela permet d'isoler l'entraînement du modèle dans son propre environnement sans perturber le pipeline ETL en cours.

**DAG de Continuous Training prévu :**

```python
from airflow.providers.docker.operators.docker import DockerOperator

retrain_model = DockerOperator(
    task_id="retrain_model",
    image="goodair-ml:latest",
    command="python src/ml/retrain.py",
    volumes=["/opt/airflow/src:/app/src"],
    schedule="0 0 1 */3 *",  # tous les 3 mois le 1er du mois à minuit
    dag=dag
)
```

**Ce que fait `retrain.py` :**

1. Exporte les nouvelles données depuis Gold.FactMesures
2. Fusionne avec Open-Meteo Archive via l'API
3. Applique les mêmes transformations que le notebook 04
4. Entraîne Random Forest et XGBoost
5. Compare les R² et sélectionne le meilleur modèle
6. Sauvegarde le nouveau `aqi_model.pkl` uniquement si R² > R² actuel
7. Envoie un email de confirmation avec les métriques du nouveau modèle

---

## Cas d'usage complémentaires

Notre modèle actuel répond à la question : **"Quel sera l'indice de qualité de l'air dans les prochaines heures ?"** En gardant la même architecture et en adaptant légèrement la cible ou les features, on peut répondre à des questions métier beaucoup plus riches.

| Cas d'usage                         | Question métier                                                | Ce qui change                                                                     | Effort                                         |
| ----------------------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------------- | ---------------------------------------------- |
| **Prédiction des pics**             | "Quand et où l'indice dépassera-t-il 100 dans les 24h ?"       | Transformer la régression en classification binaire (AQI > 100 = Alerte)          | Faible - 1 ligne de code sur la sortie         |
| **Analyse des causes**              | "Quels facteurs déclenchent les pics ?"                        | Exploiter le `feature_importance` de Random Forest déjà disponible                | Nul — c'est un output natif du modèle          |
| **Comparaison entre villes**        | "Quelle ville est la plus à risque demain ?"                   | Agréger les prédictions par ville et produire un classement                       | Faible — requête SQL sur Gold.AlertesPredites  |
| **Prédiction à 7 jours**            | "Quel sera l'indice cette semaine ?"                           | Utiliser les prévisions météo Open-Meteo sur 7 jours disponibles dans leur API    | Moyen - changer la fenêtre de prédiction       |
| **Alertes personnalisées**          | "Envoyer une alerte aux asthmatiques si indice > 50 ?"         | Créer des profils utilisateurs avec des seuils personnalisés                      | Moyen - nouveau paramètre dans la règle métier |
| **Impact des politiques publiques** | "L'interdiction de circulation a-t-elle réduit la pollution ?" | Comparer indice prédit (sans restriction) vs indice réel (avec restriction)       | Moyen - analyse causale post-hoc               |
| **Optimisation des capteurs**       | "Où placer un nouveau capteur ?"                               | Identifier les villes avec le plus de valeurs NULL ou d'incertitude de prédiction | Fort - nécessite une analyse géospatiale       |

---

## Random Forest vs XGBoost - Pourquoi Random Forest a gagné

Random Forest construit plusieurs centaines d'arbres de décision indépendants en parallèle et fait la moyenne de leurs prédictions. Cette approche par consensus est naturellement robuste sur des petits datasets avec des trous temporels. XGBoost construit les arbres de manière séquentielle, chaque arbre corrigeant les erreurs du précédent : très puissant sur de grands datasets mais moins efficace quand les données sont limitées.

| Métrique                      | Random Forest | XGBoost |
| ----------------------------- | ------------- | ------- |
| R² moyen                      | **0.8487**    | 0.8111  |
| Std R²                        | **0.0221**    | 0.0434  |
| R² Split 1 (moins de données) | **0.8185**    | 0.7508  |
| R² Split 3 (plus de données)  | **0.8711**    | 0.8510  |

Sur notre historique de 3 mois, Random Forest surpasse XGBoost sur tous les critères. Sur un historique de 2 ans avec des données continues, XGBoost aurait probablement été plus performant car il bénéficierait davantage du volume de données pour affiner son apprentissage séquentiel.
