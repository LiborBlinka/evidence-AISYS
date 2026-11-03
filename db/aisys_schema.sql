-- =====================================================================
-- evidence AISYS – schéma MySQL/MariaDB (náhrada MS Access)
-- Klíč celé evidence: IDN z objects.dbf (Aisys), vždy velkými písmeny
-- =====================================================================
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP VIEW  IF EXISTS v_kontrola_spmar, v_volne_vstupy, v_objekt_prehled, v_chybejici_idn;
DROP TABLE IF EXISTS zmena_log, uzivatel, objekt_obrazovka, objekt_funkcnost, mereni_medii, spmar,
                     aisys_zmena, aisys_import, aisys_objekt,
                     ciselnik_typ, obrazovka, funkcnost, medium_typ, medium;
SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------
-- 1) Body z Aisysu – plní VÝHRADNĚ import z objects.dbf
--    Obsah = přesná kopie objects.dbf, hodnoty se neupravují.
--    Při dalších importech se nic nemaže: zmizelé IDN dostane v_dbf = 0.
-- ---------------------------------------------------------------------
CREATE TABLE aisys_objekt (
    idn          VARCHAR(10)  NOT NULL PRIMARY KEY,
    server       VARCHAR(4)   NULL,
    station      VARCHAR(4)   NULL,          -- STATION
    type         VARCHAR(4)   NULL,          -- TYPE -> ciselnik_typ
    address      VARCHAR(10)  NULL,
    unit         SMALLINT     NULL,
    grp          INT          NULL,          -- GROUP
    name         VARCHAR(50)  NULL,
    label        VARCHAR(15)  NULL,
    area         SMALLINT     NULL,
    user_addr    VARCHAR(10)  NULL,
    eventoff     INT          NOT NULL DEFAULT 0,
    v_dbf        TINYINT(1)   NOT NULL DEFAULT 1,  -- 0 = není v objects.dbf
    prvni_import DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    zmeneno      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_station (station),
    INDEX ix_type (type),
    INDEX ix_area (area)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci;

CREATE TABLE aisys_import (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    cas       DATETIME     NOT NULL,
    soubor    VARCHAR(255) NULL,
    uzivatel  VARCHAR(50)  NULL,
    zaznamu   INT NOT NULL DEFAULT 0,
    novych    INT NOT NULL DEFAULT 0,
    zmenenych INT NOT NULL DEFAULT 0,
    zmizelych INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci;

CREATE TABLE aisys_zmena (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    import_id  INT         NOT NULL,
    idn        VARCHAR(10) NOT NULL,
    akce       ENUM('novy','zmena','zmizel','vraceny') NOT NULL,
    pole       VARCHAR(20) NULL,
    stara_hodn VARCHAR(60) NULL,
    nova_hodn  VARCHAR(60) NULL,
    INDEX ix_idn (idn),
    FOREIGN KEY (import_id) REFERENCES aisys_import(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci;

-- ---------------------------------------------------------------------
-- 2) Číselníky (z tbl_object_typ, tbl_seznam_*)
-- ---------------------------------------------------------------------
CREATE TABLE ciselnik_typ (
    kod   VARCHAR(4)   NOT NULL PRIMARY KEY,   -- TE
    nazev VARCHAR(100) NULL                    -- Teplota
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci;

CREATE TABLE funkcnost (
    kod      VARCHAR(10)  NOT NULL PRIMARY KEY, -- F, N, REZ, ...
    poznamka VARCHAR(255) NULL,
    poradi   INT          NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci;

CREATE TABLE obrazovka (
    id_obrazovky VARCHAR(100) NOT NULL PRIMARY KEY,
    skupina      VARCHAR(100) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci;

-- ---------------------------------------------------------------------
-- 3) Funkčnost bodu – 1 hodnota na IDN (jako v Accessu, PK = IDN)
-- ---------------------------------------------------------------------
CREATE TABLE objekt_funkcnost (
    idn       VARCHAR(10) NOT NULL PRIMARY KEY,
    funkcnost VARCHAR(10) NOT NULL,
    zmeneno   DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (funkcnost) REFERENCES funkcnost(kod) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci;

-- ---------------------------------------------------------------------
-- 4) Bod na obrazovkách – M:N
-- ---------------------------------------------------------------------
CREATE TABLE objekt_obrazovka (
    idn          VARCHAR(10)  NOT NULL,
    id_obrazovky VARCHAR(100) NOT NULL,
    PRIMARY KEY (idn, id_obrazovky),
    INDEX ix_obr (id_obrazovky),
    FOREIGN KEY (id_obrazovky) REFERENCES obrazovka(id_obrazovky) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci;

-- ---------------------------------------------------------------------
-- 5) SpMaR – fyzické vstupy/výstupy PS. IDN volitelné (bez IDN = volný
--    vstup). Jedno IDN může mít víc řádků (např. více vodičů / linek).
--    Vazba na aisys_objekt je jen přes index (bez cizího klíče), aby šly
--    uložit i IDN, která v objects.dbf nejsou – ukáže je v_chybejici_idn.
-- ---------------------------------------------------------------------
CREATE TABLE spmar (
    id                    INT          NOT NULL PRIMARY KEY,  -- ID z Accessu
    cislo_ps              VARCHAR(50)  NULL,
    cislo_karty           VARCHAR(255) NULL,
    vstupni_modul         VARCHAR(255) NULL,
    adresa                VARCHAR(255) NULL,
    vstup_ps              VARCHAR(255) NULL,
    popis_mar             VARCHAR(255) NULL,
    idn                   VARCHAR(10)  NULL,
    nazev_objektu         VARCHAR(255) NULL,
    rs_mbus_adresa        VARCHAR(255) NULL,
    svorkovnice_odvod     VARCHAR(255) NULL,
    cislo_svorky          VARCHAR(255) NULL,
    rozvadec_sk           VARCHAR(255) NULL,
    svorkovnice_zakonceni VARCHAR(255) NULL,
    svorka                VARCHAR(255) NULL,
    poznamka              TEXT         NULL,
    f16                   VARCHAR(255) NULL,   -- sloupec F16 z importu (ověřit význam)
    INDEX ix_ps_karta (cislo_ps, cislo_karty),
    INDEX ix_idn (idn)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci;

-- ---------------------------------------------------------------------
-- 6) Uživatelé a role
--    viewer = jen prohlížení, editor = prohlížení a změny, admin = vše
--    (import objects.dbf, číselníky, správa uživatelů)
-- ---------------------------------------------------------------------
CREATE TABLE uzivatel (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    login               VARCHAR(50)  NOT NULL UNIQUE,
    jmeno               VARCHAR(100) NULL,
    heslo_hash          VARCHAR(255) NOT NULL,          -- password_hash(), Argon2id
    role                ENUM('viewer','editor','admin') NOT NULL DEFAULT 'viewer',
    aktivni             TINYINT(1)   NOT NULL DEFAULT 1,
    posledni_prihlaseni DATETIME     NULL,
    chybnych_pokusu     INT          NOT NULL DEFAULT 0,
    zamceno_do          DATETIME     NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci;

-- Historie ručních změn v evidenci (kdo, kdy, co)
CREATE TABLE zmena_log (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    cas         DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uzivatel_id INT         NOT NULL,
    tabulka     VARCHAR(40) NOT NULL,
    zaznam      VARCHAR(40) NOT NULL,
    akce        ENUM('insert','update','delete') NOT NULL,
    pole        VARCHAR(40) NULL,
    stara_hodn  TEXT NULL,
    nova_hodn   TEXT NULL,
    INDEX ix_zaznam (tabulka, zaznam),
    FOREIGN KEY (uzivatel_id) REFERENCES uzivatel(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci;

-- ---------------------------------------------------------------------
-- 7) Pohledy
-- ---------------------------------------------------------------------
-- Hlavní přehled bodu (náhrada hlavního formuláře / dot_meření_Medií)
CREATE VIEW v_objekt_prehled AS
SELECT o.idn, o.station, o.type, t.nazev AS type_nazev, o.address, o.name,
       o.label, o.user_addr, o.area, o.v_dbf,
       f.funkcnost,
       (SELECT GROUP_CONCAT(oo.id_obrazovky ORDER BY oo.id_obrazovky SEPARATOR ', ')
          FROM objekt_obrazovka oo WHERE oo.idn = o.idn) AS obrazovky,
       (SELECT COUNT(*) FROM spmar s WHERE s.idn = o.idn) AS spmar_radku
FROM aisys_objekt o
LEFT JOIN ciselnik_typ     t ON t.kod = o.type
LEFT JOIN objekt_funkcnost f ON f.idn = o.idn;

-- Volné vstupy na kartách (SpMaR bez IDN)
CREATE VIEW v_volne_vstupy AS
SELECT id, cislo_ps, cislo_karty, vstupni_modul, vstup_ps, adresa, poznamka, f16
FROM spmar
WHERE idn IS NULL;

-- Nesoulad SpMaR vs. Aisys: adresa jiná než ADDRESS v DBF, nebo bod
-- už v objects.dbf není
CREATE VIEW v_kontrola_spmar AS
SELECT s.id, s.idn, s.cislo_ps, o.station, s.adresa, o.address,
       s.popis_mar, o.name, o.v_dbf
FROM spmar s
JOIN aisys_objekt o ON o.idn = s.idn
WHERE o.v_dbf = 0
   OR COALESCE(s.adresa,'') <> COALESCE(o.address,'');

-- IDN použitá v evidenci, která v objects.dbf nejsou
CREATE VIEW v_chybejici_idn AS
SELECT x.idn, GROUP_CONCAT(DISTINCT x.zdroj ORDER BY x.zdroj SEPARATOR ', ') AS kde
FROM (SELECT idn, 'SpMaR' AS zdroj FROM spmar WHERE idn IS NOT NULL
      UNION ALL SELECT idn, 'funkčnost' FROM objekt_funkcnost
      UNION ALL SELECT idn, 'obrazovky' FROM objekt_obrazovka) x
LEFT JOIN aisys_objekt o ON o.idn = x.idn
WHERE o.idn IS NULL
GROUP BY x.idn;
