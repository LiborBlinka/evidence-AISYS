#!/usr/bin/env python3
"""
Migrace evidence AISYS (bez měření médií):  objects.dbf + AisysEvidence.accdb  ->  SQL pro MySQL/MariaDB

Použití:
    python3 migrate.py objects.dbf AisysEvidence.accdb  aisys_data.sql  migrace_report.md

Vyžaduje mdbtools (mdb-export):  apt install mdbtools
Výstup se nahraje do DB vytvořené ze schématu aisys_schema.sql:
    mysql aisys < aisys_schema.sql && mysql aisys < aisys_data.sql
"""
import csv, io, struct, subprocess, sys, collections, datetime

DBF, ACCDB, OUT_SQL, OUT_REP = sys.argv[1:5]
NOW = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
report = collections.defaultdict(list)


# ---------------------------------------------------------------- pomocné
def s(v):
    """Ořízne text, prázdné -> None."""
    if v is None:
        return None
    v = str(v).replace('\r\n', '\n').strip()
    return v or None


def idn(v):
    return s(v)


def num(v):
    v = s(v)
    if v is None:
        return None
    try:
        return int(float(v.replace(',', '.')))
    except ValueError:
        return None


def q(v):
    if v is None:
        return 'NULL'
    if isinstance(v, int):
        return str(v)
    v = str(v).replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')
    return "'" + v + "'"


def table(name):
    out = subprocess.run(['mdb-export', ACCDB, name], capture_output=True, check=True).stdout
    return list(csv.DictReader(io.StringIO(out.decode('utf-8'))))


# ---------------------------------------------------------------- objects.dbf
def read_dbf(path):
    d = open(path, 'rb').read()
    n, hl, rl = struct.unpack('<IHH', d[4:12])
    fields, o = [], 32
    while d[o] != 0x0D:
        fields.append((d[o:o + 11].split(b'\0')[0].decode(), chr(d[o + 11]),
                       struct.unpack('<I', d[o + 12:o + 16])[0], d[o + 16]))
        o += 32
    rows = []
    for i in range(n):
        r = d[hl + i * rl: hl + (i + 1) * rl]
        if r[0:1] == b'*':
            continue
        rec = {}
        for name, t, off, ln in fields:
            b = r[off:off + ln]
            if t == 'I':
                v = struct.unpack('<i', b)[0]
                rec[name] = v
            else:
                rec[name] = b.decode('cp1250').strip()
        rows.append(rec)
    return rows


dbf = read_dbf(DBF)
objekty = {}
eventoff_fix = 0
for r in dbf:
    k = idn(r['IDN'])
    ev = r['EVENTOFF']          # bez úprav, jen spočítat podezřelé hodnoty
    if ev == 0x20202020:
        eventoff_fix += 1
    objekty[k] = dict(idn=k, server=s(r['SERVER']), station=s(r['STATION']), type=s(r['TYPE']),
                      address=s(r['ADDRESS']), unit=num(r['UNIT']), grp=r['GROUP'],
                      name=s(r['NAME']), label=s(r['LABEL']), area=num(r['AREA']),
                      user_addr=s(r['USER_ADDR']), eventoff=ev, v_dbf=1)
report['info'].append(f'objects.dbf: {len(objekty)} bodů převzato beze změn; EVENTOFF = 538976288 (4 mezery v binárním poli) u {eventoff_fix} bodů – ponecháno')

# tbl_object v Accessu – jen pro porovnání
acc_obj = {idn(r['IDN']) for r in table('tbl_object')}
nove = sorted(set(objekty) - acc_obj)
report['info'].append(f'tbl_object v Accessu: {len(acc_obj)} bodů; v DBF navíc (Access je ještě nemá): {len(nove)} – {", ".join(nove)}')

orphan_names = {}
objekty_ci = {k.upper() for k in objekty}


def ref(k, source, hint=None):
    """Jen zaznamená IDN, které v objects.dbf není – nic nezakládá."""
    if k is None:
        return None
    if k.upper() not in objekty_ci:     # MySQL porovnává bez ohledu na velikost písmen
        orphan_names.setdefault(k, [set(), None])
        orphan_names[k][0].add(source)
        if hint and not orphan_names[k][1]:
            orphan_names[k][1] = hint
    return k


# ---------------------------------------------------------------- číselníky
typy = [(s(r['TYPE']), s(r['TYPE popis'])) for r in table('tbl_object_typ')]

funk = {}
for r in table('tbl_seznam_funkčnost'):
    funk[s(r['funkčnost'])] = (s(r['Poznámka']), num(r['ID']))

obrazovky = {}
for r in table('tbl_seznam_Obrazovky'):
    obrazovky[s(r['ID_obrazovky'])] = s(r['Skupina_obrazovky'])
obr_ci = {k.lower().replace(' ', ''): k for k in obrazovky}

def funk_norm(v, ctx):
    v = s(v)
    if v is None:
        return None
    if v not in funk:
        up = v.upper()
        if up in funk:
            return up
        funk[v] = ('doplněno při migraci', None)
        report['ciselniky'].append(f'Funkčnost „{v}“ nebyla v číselníku – doplněna ({ctx})')
    return v


# ---------------------------------------------------------------- funkčnost
obj_funk = {}
empty_f = 0
for r in table('tbl_objekty_funkčnost'):
    k = idn(r['IDN'])
    f = funk_norm(r['funkčnost'], f'IDN {k}')
    if not f:
        empty_f += 1
        continue
    obj_funk[ref(k, 'funkčnost')] = f
report['cisteni'].append(f'tbl_objekty_funkčnost: {len(obj_funk)} převedeno, {empty_f} řádků bez hodnoty vynecháno, mezery za kódem (např. „F   “) odstraněny')

# ---------------------------------------------------------------- obrazovky
obj_obr = set()
empty_o = dup_o = 0
for r in table('tbl_objekty_na_obrazovkách'):
    k = idn(r['IDN'])
    o = s(r['ID_obrazovky'])
    if not k or not o:
        empty_o += 1
        continue
    key = o.lower().replace(' ', '')
    if key in obr_ci:
        if obr_ci[key] != o:
            report['ciselniky'].append(f'Obrazovka „{o}“ sloučena s „{obr_ci[key]}“')
        o = obr_ci[key]
    else:
        obrazovky[o] = None
        obr_ci[key] = o
        report['ciselniky'].append(f'Obrazovka „{o}“ nebyla v seznamu obrazovek – doplněna')
    pair = (ref(k, 'obrazovky'), o)
    if pair in obj_obr:
        dup_o += 1
    obj_obr.add(pair)
report['cisteni'].append(f'tbl_objekty_na_obrazovkách: {len(obj_obr)} vazeb převedeno, {empty_o} prázdných řádků a {dup_o} duplicit vynecháno')

# ---------------------------------------------------------------- SpMaR
spmar = []
for r in table('tbl_SpMaR'):
    k = idn(r['IDN'])
    spmar.append(dict(
        id=num(r['ID']), cislo_ps=s(r['číslo_PS']), cislo_karty=s(r['číslo_karty']),
        vstupni_modul=s(r['vstupní_modul']), adresa=s(r['adresa']), vstup_ps=s(r['vstup_PS']),
        popis_mar=s(r['popis_MaR']), idn=ref(k, 'SpMaR', s(r['Název_objektu']) or s(r['popis_MaR'])),
        nazev_objektu=s(r['Název_objektu']), rs_mbus_adresa=s(r['RS_MBUS_adresa']),
        svorkovnice_odvod=s(r['Svorkovnice_odvod']), cislo_svorky=s(r['číslo_svorky']),
        rozvadec_sk=s(r['Rozvaděč_SK']), svorkovnice_zakonceni=s(r['Svorkovnice_zakončení']),
        svorka=s(r['Svorka']), poznamka=s(r['Poznámka']), f16=s(r['F16'])))
report['info'].append(f'SpMaR: {len(spmar)} řádků, z toho bez IDN (volné vstupy): {sum(1 for x in spmar if not x["idn"])}')

dup_sp = collections.Counter(x['idn'] for x in spmar if x['idn'])
dups = []
by_idn = collections.defaultdict(list)
for x in spmar:
    if x['idn']:
        by_idn[x['idn']].append(x)
for k, lst in by_idn.items():
    if len(lst) > 1:
        sig = {(x['cislo_ps'], x['cislo_karty'], x['adresa'], x['vstup_ps'], x['popis_mar']) for x in lst}
        if len(sig) < len(lst):
            dups.append(f'{k}: ID ' + ', '.join(str(x['id']) for x in lst))
report['kontrola_spmar_dup'] = dups

adr_diff = []
for x in spmar:
    o = objekty.get(x['idn']) or objekty.get((x['idn'] or '').upper())
    if o and (x['adresa'] or '') != (o['address'] or ''):
        adr_diff.append(x)
report['info'].append(f'SpMaR: adresa jiná než ADDRESS v objects.dbf u {len(adr_diff)} řádků (viz pohled v_kontrola_spmar)')

report['orphans'] = [f'{k} – {v[1] or "?"} (odkazuje: {", ".join(sorted(v[0]))})'
                     for k, v in sorted(orphan_names.items())]

# ---------------------------------------------------------------- zápis SQL
def inserts(f, tbl, cols, rows, chunk=500):
    for i in range(0, len(rows), chunk):
        f.write(f'INSERT INTO {tbl} ({", ".join(cols)}) VALUES\n')
        f.write(',\n'.join('(' + ', '.join(q(r[c]) for c in cols) + ')' for r in rows[i:i + chunk]))
        f.write(';\n')


with open(OUT_SQL, 'w', encoding='utf-8') as f:
    f.write(f'-- evidence AISYS – data z migrace {NOW}\nSET NAMES utf8mb4;\nSET FOREIGN_KEY_CHECKS = 0;\nSTART TRANSACTION;\n\n')
    inserts(f, 'ciselnik_typ', ['kod', 'nazev'], [dict(kod=a, nazev=b) for a, b in typy])
    inserts(f, 'funkcnost', ['kod', 'poznamka', 'poradi'],
            [dict(kod=k, poznamka=v[0], poradi=v[1]) for k, v in funk.items()])
    inserts(f, 'obrazovka', ['id_obrazovky', 'skupina'],
            [dict(id_obrazovky=k, skupina=v) for k, v in obrazovky.items()])
    ocols = ['idn', 'server', 'station', 'type', 'address', 'unit', 'grp', 'name', 'label',
             'area', 'user_addr', 'eventoff', 'v_dbf']
    inserts(f, 'aisys_objekt', ocols, list(objekty.values()))
    f.write(f"INSERT INTO aisys_import (cas, soubor, uzivatel, zaznamu) VALUES ('{NOW}', 'objects.dbf', 'migrace', {len(dbf)});\n")
    inserts(f, 'objekt_funkcnost', ['idn', 'funkcnost'],
            [dict(idn=k, funkcnost=v) for k, v in obj_funk.items()])
    inserts(f, 'objekt_obrazovka', ['idn', 'id_obrazovky'],
            [dict(idn=a, id_obrazovky=b) for a, b in sorted(obj_obr)])
    inserts(f, 'spmar', list(spmar[0].keys()), spmar)
    f.write('\nCOMMIT;\nSET FOREIGN_KEY_CHECKS = 1;\n')

# ---------------------------------------------------------------- report
with open(OUT_REP, 'w', encoding='utf-8') as f:
    f.write(f'# Migrace evidence AISYS – report ({NOW})\n\n## Přehled\n')
    for x in report['info']:
        f.write(f'- {x}\n')
    f.write('\n## Čištění dat\n')
    for x in report['cisteni']:
        f.write(f'- {x}\n')
    f.write('\n## Úpravy číselníků\n')
    for x, c in collections.Counter(report['ciselniky']).items():
        f.write(f'- {x}' + (f' ({c}×)' if c > 1 else '') + '\n')
    f.write(f'\n## IDN, která nejsou v objects.dbf ({len(report["orphans"])})\n'
            'Data převedena, v aisys_objekt nic nezaloženo (objects.dbf beze změn). Zobrazí je pohled v_chybejici_idn.\n\n')
    for x in report['orphans']:
        f.write(f'- {x}\n')
    f.write(f'\n## SpMaR – pravděpodobně zdvojené řádky ({len(report["kontrola_spmar_dup"])})\n'
            'Stejné IDN, PS, karta, adresa, vstup i popis.\n\n')
    for x in report['kontrola_spmar_dup']:
        f.write(f'- {x}\n')

print(open(OUT_REP, encoding='utf-8').read())
