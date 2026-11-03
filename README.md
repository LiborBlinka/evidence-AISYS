# evidence AISYS

Webová evidence bodů řídicího systému Aisys (PLC, vstupy/výstupy, SpMaR) jako náhrada aplikace v MS Access.
Klíčem celé evidence je `IDN` z `objects.dbf` (Aisys).

Stack: Debian 13, Apache, PHP 8.4 (FPM), MariaDB.

## Obsah repozitáře

| Cesta | Co to je |
| --- | --- |
| `db/aisys_schema.sql` | Schéma databáze: body z Aisysu, SpMaR, funkčnost, obrazovky, číselníky, uživatelé a role, historie změn, pohledy |
| `tools/migrate.py` | Jednorázový převod `objects.dbf` + `AisysEvidence.accdb` do SQL a report problémů v datech |
| `docs/instalace.md` | Instalace serveru (Proxmox VM) a bezpečný přístup zvenku přes WireGuard |

## Datový model

- `aisys_objekt` – přesná kopie `objects.dbf`, plní ji jen import. Body se nemažou, zmizelé dostanou `v_dbf = 0`.
- `spmar` – hardware s popisem (karta, vstup, svorky, rozvaděč). Řádek bez `IDN` = volný vstup.
- `objekt_funkcnost` – funkčnost bodu (1 na IDN), `objekt_obrazovka` – na kterých obrazovkách bod je.
- `uzivatel` – role `viewer` (jen prohlížení), `editor` (prohlížení a změny), `admin` (import, číselníky, uživatelé).
- `zmena_log` – kdo, kdy a co ručně změnil.
- Pohledy: `v_objekt_prehled`, `v_volne_vstupy`, `v_kontrola_spmar`, `v_chybejici_idn`.

## Migrace z Accessu

```bash
sudo apt install mdbtools
python3 tools/migrate.py objects.dbf AisysEvidence.accdb aisys_data.sql migrace_report.md
sudo mariadb aisys < db/aisys_schema.sql
sudo mariadb aisys < aisys_data.sql
```

`objects.dbf` se převezme beze změn. Úpravy dat z Accessu (prázdné řádky, mezery v kódech, sloučené názvy obrazovek)
a nalezené problémy vypíše `migrace_report.md`.

**Data se do repozitáře neukládají** (`objects.dbf`, `*.accdb`, `aisys_data.sql`, report) – obsahují popisy
řídicího systému. Blokuje je `.gitignore`.

## Stav

- [x] Schéma databáze a migrace dat z Accessu
- [x] Návod na instalaci serveru
- [ ] PHP aplikace (přihlášení a role, hlavní formulář podle IDN, SpMaR, přehledy, import objects.dbf)
