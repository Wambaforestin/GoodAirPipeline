-- Création des rôles et utilisateurs - GoodAir Data Warehouse
-- Conformément aux spécifications de sécurité du cahier des charges
USE GoodAirDW;
GO

-- 1. Création des rôles de base de données

-- Role_Chercheur : lecture seule sur Gold et Ref
CREATE ROLE Role_Chercheur;
GO
GRANT SELECT ON SCHEMA::Gold TO Role_Chercheur;
GRANT SELECT ON SCHEMA::Ref TO Role_Chercheur;
GO

-- Role_Directeur : lecture seule sur Gold et Ref
CREATE ROLE Role_Directeur;
GO
GRANT SELECT ON SCHEMA::Gold TO Role_Directeur;
GRANT SELECT ON SCHEMA::Ref TO Role_Directeur;
GO

-- Role_RSSI : aucun accès aux données, gestion des accès uniquement
CREATE ROLE Role_RSSI;
GO

-- 2. Création des logins (niveau serveur)
-- MUST_CHANGE = ON : mot de passe à changer à la première connexion
-- CHECK_POLICY = ON : obligatoire pour que MUST_CHANGE fonctionne

CREATE LOGIN UsrChercheur
    WITH PASSWORD = 'Chercheur2026!' MUST_CHANGE,
    CHECK_POLICY = ON,
    CHECK_EXPIRATION = OFF,
    DEFAULT_DATABASE = GoodAirDW;
GO

CREATE LOGIN UsrDirecteur
    WITH PASSWORD = 'DirDash2026$' MUST_CHANGE,
    CHECK_POLICY = ON,
    CHECK_EXPIRATION = OFF,
    DEFAULT_DATABASE = GoodAirDW;
GO

CREATE LOGIN UsrRSSI
    WITH PASSWORD = 'Securite2026*' MUST_CHANGE,
    CHECK_POLICY = ON,
    CHECK_EXPIRATION = OFF,
    DEFAULT_DATABASE = GoodAirDW;
GO

-- Le RSSI gère les accès via securityadmin
ALTER SERVER ROLE securityadmin ADD MEMBER UsrRSSI;
GO

-- 3. Création des utilisateurs (niveau base) et assignation des rôles

CREATE USER UsrChercheur FOR LOGIN UsrChercheur;
GO
ALTER ROLE Role_Chercheur ADD MEMBER UsrChercheur;
GO

CREATE USER UsrDirecteur FOR LOGIN UsrDirecteur;
GO
ALTER ROLE Role_Directeur ADD MEMBER UsrDirecteur;
GO

CREATE USER UsrRSSI FOR LOGIN UsrRSSI;
GO
ALTER ROLE Role_RSSI ADD MEMBER UsrRSSI;
GO

-- 4. Vérification
SELECT 
    dp.name AS NomUtilisateur,
    dp.type_desc AS TypeUtilisateur,
    r.name AS Role
FROM sys.database_principals dp
INNER JOIN sys.database_role_members drm ON dp.principal_id = drm.member_principal_id
INNER JOIN sys.database_principals r ON drm.role_principal_id = r.principal_id
WHERE dp.name IN ('UsrChercheur', 'UsrDirecteur', 'UsrRSSI');
GO