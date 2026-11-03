# evidence AISYS – instalace serveru a bezpečný přístup zvenku

Kopie dokumentu z claude.ai (stav k 3. 11. 2026). Živá verze: https://claude.ai/artifact/J2JSHm1dvAxoAQ51zuJsCY

## Přehled a doporučení

Doporučuji přístup zvenku jen přes **VPN WireGuard přímo na aplikačním VM**. Na FortiGate se otevře jediný port, UDP 51820, a webová aplikace ani SSH na internetu vůbec nebudou.

Důvody:

- **FortiGate 110C už nedostává bezpečnostní opravy.** Hardware je po konci podpory od roku 2018 (FG-110C-G od 2019) a firmware končí u řady FortiOS 5.x ([endoflife.ai](https://endoflife.ai/fortigate-appliances/FortiGate-110C)). Jeho vestavěné SSL-VPN ani publikování webu přes něj proto nedoporučuji.
- WireGuard na port bez platného klíče neodpovídá. Pro skenery z internetu port vypadá jako zavřený a i na starém firewallu je to nejmenší možné vystavení.
- Evidence obsahuje adresy a popisy bodů řídicího systému (PLC, vstupy, rozvaděče). Taková data na veřejný web nepatří, ani za heslem.

**Použité hodnoty (uprav podle skutečnosti):**

| Položka | Hodnota |
| --- | --- |
| Veřejná adresa / DDNS | 62.168.59.78 / lb-iot.fortiddns.com |
| LAN | 192.168.105.0/24 |
| Brána LAN (FortiGate) | 192.168.105.1 – ověř |
| IP aplikačního VM | 192.168.105.20 – zvol volnou adresu mimo DHCP |
| Hostname VM | aisys |
| Síť VPN | 10.105.0.0/24, VM = 10.105.0.1 |
| Port VPN | UDP 51820 |
| Debian | 13 „Trixie“ (aktuální stable, PHP 8.4, MariaDB 11.8) |

Pokud by bylo opravdu potřeba otevřít web lidem bez VPN, je to popsané jako varianta B v kapitole 5, včetně rizik.

```
 Internet                     FortiGate 110C                LAN 192.168.105.0/24
 ┌──────────────────┐        ┌─────────────────────┐       ┌─────────────────────────────┐
 │ Vzdálený klient  │  UDP   │ lb-iot.fortiddns.com│  UDP  │ Proxmox                     │
 │ notebook,telefon │ 51820  │ 62.168.59.78        │ 51820 │ ┌─────────────────────────┐ │
 │ WG 10.105.0.x    ├───────►│ VIP jen UDP 51820   ├──────►│ │ VM aisys · Debian 13    │ │
 └──────────────────┘        │ firmware bez oprav  │       │ │ 192.168.105.20          │ │
                             └─────────────────────┘       │ │ wg0 10.105.0.1          │ │
 ┌───────────────────────────────────────────────┐         │ │ Apache 443, PHP 8.4     │ │
 │ Aisys SCADA (jiná síť)                        │ ┄┄┄┄┄┄┄►│ │ MariaDB jen 127.0.0.1   │ │
 │ objects.dbf nahrává admin ručně přes web      │         │ └────────────▲────────────┘ │
 └───────────────────────────────────────────────┘         │     HTTPS 443│              │
                                                           │ Počítače v LAN              │
                                                           └─────────────────────────────┘
```

Zvenku vede jediná cesta: tunel WireGuard přes FortiGate na VM. Z LAN se na aplikaci chodí přímo přes HTTPS.

## 1. Virtuál v Proxmoxu a instalace Debianu 13

**ISO:** v Proxmoxu otevři *local → ISO Images → Download from URL* a zadej odkaz na `debian-13.x.x-amd64-netinst.iso` z [debian.org/distrib/netinst](https://www.debian.org/distrib/netinst). Kontrolní součet SHA256 vlož ze souboru `SHA256SUMS` ze stejného adresáře.

**Parametry VM (Create VM):**

| Záložka | Nastavení |
| --- | --- |
| General | Name `aisys`, Start at boot zapnout |
| OS | Debian ISO, Guest OS Linux 6.x |
| System | Machine q35, BIOS výchozí (SeaBIOS), SCSI VirtIO SCSI single, **Qemu Agent zapnout** |
| Disks | 32 GB, Discard zapnout, SSD emulation dle úložiště |
| CPU | 2 jádra, Type `host` |
| Memory | 2048 MB (stačí, 4096 MB s rezervou) |
| Network | Bridge `vmbr0` (síť 192.168.105.0/24), Model VirtIO, Firewall dle zvyku |

**Instalátor (Install, ne Graphical install):**

1. Jazyk: čeština nebo angličtina (angličtina dává lepší hlášky pro vyhledávání), umístění Czechia, klávesnice dle zvyku.
2. Síť: nechej DHCP, statickou adresu nastavíme po instalaci. Hostname `aisys`, doména `lan` nebo prázdná.
3. Heslo roota **nech prázdné**. Instalátor pak roota zamkne a tvůj uživatel dostane `sudo`.
4. Uživatel: např. `libor` se silným heslem.
5. Disk: *Guided – use entire disk*, *All files in one partition*.
6. Zrcadlo balíčků: Czechia, `deb.debian.org`.
7. Výběr software: **jen „SSH server“ a „standard system utilities“**, žádné desktopové prostředí ani webový server (Apache nainstalujeme ručně).
8. GRUB na `/dev/sda`, restart, v Proxmoxu odpoj ISO (Hardware → CD/DVD → Do not use any media).

## 2. Základní nastavení Debianu

**Aktualizace a základní balíčky:**

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y qemu-guest-agent nftables unattended-upgrades apt-listchanges \
  curl ca-certificates htop vim
sudo systemctl enable --now qemu-guest-agent
sudo timedatectl set-timezone Europe/Prague
```

**Statická IP:** název rozhraní zjisti příkazem `ip -br a`, ve VM na Proxmoxu je to obvykle `ens18`. Uprav `/etc/network/interfaces`:

```
auto lo
iface lo inet loopback

auto ens18
iface ens18 inet static
    address 192.168.105.20/24
    gateway 192.168.105.1
    dns-nameservers 192.168.105.1
```

Pak `sudo apt install -y resolvconf` (kvůli řádku `dns-nameservers`) a `sudo systemctl restart networking`, případně restart VM. Jestli FortiGate dělá DHCP, dej adresu do rezervace nebo mimo rozsah poolu.

**SSH jen s klíčem:** ze svého PC `ssh-copy-id libor@192.168.105.20`, ověř přihlášení klíčem a pak vytvoř `/etc/ssh/sshd_config.d/10-hardening.conf`:

```
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
AllowUsers libor
```

`sudo sshd -t && sudo systemctl reload ssh`. Okno se stávajícím přihlášením zavři až po úspěšném novém přihlášení.

**Automatické bezpečnostní aktualizace:** `sudo dpkg-reconfigure -plow unattended-upgrades` a zvol *Yes*. Výchozí nastavení instaluje jen balíčky z `trixie-security`.

**Firewall na VM (nftables)**, soubor `/etc/nftables.conf`:

```
#!/usr/sbin/nft -f
flush ruleset

table inet filter {
  chain input {
    type filter hook input priority 0; policy drop;
    iif lo accept
    ct state established,related accept
    ct state invalid drop
    ip protocol icmp accept
    ip6 nexthdr ipv6-icmp accept

    udp dport 51820 accept                                # WireGuard z internetu
    ip saddr { 192.168.105.0/24, 10.105.0.0/24 } tcp dport { 22, 80, 443 } accept
  }
  chain forward { type filter hook forward priority 0; policy drop; }
  chain output  { type filter hook output  priority 0; policy accept; }
}
```

`sudo systemctl enable --now nftables` a kontrola `sudo nft list ruleset`. SSH a web jsou dostupné jen z LAN a z VPN. Forward je zakázaný, takže VPN klient se dostane pouze na tento server, ne dál do sítě.

## 3. Aplikační stack: Apache, PHP 8.4, MariaDB

**Instalace:**

```bash
sudo apt install -y apache2 mariadb-server mdbtools \
  php8.4-fpm php8.4-mysql php8.4-mbstring php8.4-intl php8.4-xml php8.4-zip php8.4-cli
sudo a2enmod proxy_fcgi setenvif headers rewrite ssl
sudo a2enconf php8.4-fpm
sudo a2dismod -f autoindex status
sudo systemctl restart apache2
```

**MariaDB:** spusť `sudo mariadb-secure-installation` (root přes unix_socket nech, anonymní uživatele a testovací DB smaž). Pak vytvoř databázi a uživatele aplikace:

```sql
CREATE DATABASE aisys CHARACTER SET utf8mb4 COLLATE utf8mb4_czech_ci;
CREATE USER 'aisys_app'@'localhost' IDENTIFIED BY 'DLOUHE_NAHODNE_HESLO';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE TEMPORARY TABLES ON aisys.* TO 'aisys_app'@'localhost';
FLUSH PRIVILEGES;
```

Aplikační uživatel nesmí měnit strukturu tabulek. Schéma a data nahraješ jako root:

```bash
sudo mariadb aisys < db/aisys_schema.sql
sudo mariadb aisys < aisys_data.sql      # vytvoří tools/migrate.py, není v repozitáři
```

MariaDB poslouchá v Debianu jen na `127.0.0.1`. Tak to nech, aplikace běží na stejném stroji.

**PHP:** v `/etc/php/8.4/fpm/conf.d/90-aisys.ini`:

```
expose_php = Off
display_errors = Off
log_errors = On
upload_max_filesize = 16M
post_max_size = 20M
session.cookie_httponly = 1
session.cookie_secure = 1
session.cookie_samesite = Strict
session.use_strict_mode = 1
date.timezone = Europe/Prague
```

`sudo systemctl restart php8.4-fpm`. Limit 16 MB stačí na objects.dbf (dnes asi 0,9 MB) i s rezervou.

**Adresáře aplikace:**

```
/var/www/aisys/
├── public/            # DocumentRoot – jen index.php, css, js
├── app/               # PHP třídy, šablony (mimo web)
├── config/config.php  # přihlašovací údaje k DB (mimo web)
└── storage/import/    # nahrané objects.dbf (mimo web)
```

```bash
sudo mkdir -p /var/www/aisys/{public,app,config,storage/import}
sudo chown -R libor:www-data /var/www/aisys
sudo chmod -R 750 /var/www/aisys
sudo chmod 770 /var/www/aisys/storage/import
sudo chmod 640 /var/www/aisys/config/config.php   # až soubor vznikne
```

## 4. HTTPS a virtuální host Apache

Aplikace bude dostupná jen z LAN a z VPN. Veřejný certifikát Let's Encrypt proto nepotřebuješ (ten vyžaduje otevřený port 80 do internetu). Použij vlastní certifikát na 10 let s oběma adresami serveru:

```bash
sudo openssl req -x509 -newkey rsa:3072 -sha256 -days 3650 -nodes \
  -keyout /etc/ssl/private/aisys.key -out /etc/ssl/certs/aisys.crt \
  -subj "/CN=aisys" \
  -addext "subjectAltName=DNS:aisys,DNS:aisys.lan,IP:192.168.105.20,IP:10.105.0.1"
sudo chmod 600 /etc/ssl/private/aisys.key
```

Soubor `aisys.crt` naimportuj na svých počítačích a telefonu jako důvěryhodný (ve Windows do *Důvěryhodné kořenové certifikační autority*). Prohlížeč pak přestane varovat.

**Virtuální host** `/etc/apache2/sites-available/aisys.conf`:

```apache
<VirtualHost *:80>
    ServerName aisys
    Redirect permanent / https://192.168.105.20/
</VirtualHost>

<VirtualHost *:443>
    ServerName aisys
    ServerAlias aisys.lan 192.168.105.20 10.105.0.1
    DocumentRoot /var/www/aisys/public

    SSLEngine on
    SSLCertificateFile    /etc/ssl/certs/aisys.crt
    SSLCertificateKeyFile /etc/ssl/private/aisys.key
    Protocols h2 http/1.1

    <Directory /var/www/aisys/public>
        Options -Indexes +FollowSymLinks
        AllowOverride None
        Require all granted
        FallbackResource /index.php
    </Directory>

    <FilesMatch "\.php$">
        SetHandler "proxy:unix:/run/php/php8.4-fpm.sock|fcgi://localhost"
    </FilesMatch>

    Header always set Strict-Transport-Security "max-age=31536000"
    Header always set X-Content-Type-Options "nosniff"
    Header always set X-Frame-Options "DENY"
    Header always set Referrer-Policy "same-origin"
    Header always set Content-Security-Policy "default-src 'self'; frame-ancestors 'none'"

    ErrorLog  ${APACHE_LOG_DIR}/aisys_error.log
    CustomLog ${APACHE_LOG_DIR}/aisys_access.log combined
</VirtualHost>
```

Skrytí verze serveru v `/etc/apache2/conf-available/security.conf`: `ServerTokens Prod` a `ServerSignature Off`.

```bash
sudo a2enmod http2
sudo a2dissite 000-default
sudo a2ensite aisys
sudo apache2ctl configtest && sudo systemctl reload apache2
```

Kontrola z LAN: `https://192.168.105.20/`.

## 5. Přístup zvenku

### Varianta A (doporučeno): WireGuard na VM

**Server:**

```bash
sudo apt install -y wireguard qrencode
sudo mkdir -p /etc/wireguard/clients && cd /etc/wireguard
umask 077
wg genkey | sudo tee server.key | wg pubkey | sudo tee server.pub
```

`/etc/wireguard/wg0.conf`:

```ini
[Interface]
Address    = 10.105.0.1/24
ListenPort = 51820
PrivateKey = <obsah server.key>

# notebook Libor
[Peer]
PublicKey    = <veřejný klíč klienta>
PresharedKey = <psk klienta>
AllowedIPs   = 10.105.0.2/32
```

```bash
sudo systemctl enable --now wg-quick@wg0
sudo wg show
```

**Klient** (pro každé zařízení zvlášť, další dostane 10.105.0.3 atd.):

```bash
cd /etc/wireguard/clients
wg genkey | sudo tee notebook.key | wg pubkey | sudo tee notebook.pub
wg genpsk | sudo tee notebook.psk
```

Konfigurace pro klienta, `notebook.conf`:

```ini
[Interface]
PrivateKey = <obsah notebook.key>
Address    = 10.105.0.2/32

[Peer]
PublicKey    = <obsah server.pub>
PresharedKey = <obsah notebook.psk>
Endpoint     = lb-iot.fortiddns.com:51820
AllowedIPs   = 10.105.0.1/32
PersistentKeepalive = 25
```

`AllowedIPs = 10.105.0.1/32` znamená, že tunelem jde jen provoz na aplikační server. Ostatní internet klienta jde normálně. Veřejný klíč a PSK klienta doplň do `[Peer]` na serveru a dej `sudo systemctl restart wg-quick@wg0`. Na telefon konfiguraci přeneseš QR kódem: `sudo qrencode -t ansiutf8 < notebook.conf`. Klienti WireGuard existují pro Windows, macOS, Android i iOS. Po připojení otevři `https://10.105.0.1/`.

Ztracené zařízení zablokuješ smazáním jeho `[Peer]` a restartem služby.

### Nastavení FortiGate 110C

Potřebuješ jen přesměrování UDP 51820 na VM. V GUI: *Policy & Objects → Virtual IPs → Create New* a pak politiku *WAN → internal* s cílem tohoto VIP. Stejné v CLI (názvy rozhraní `wan1` a `internal` uprav podle svého FortiGate):

```
config firewall vip
    edit "VIP-aisys-wg"
        set extintf "wan1"
        set extip 62.168.59.78
        set mappedip "192.168.105.20"
        set portforward enable
        set protocol udp
        set extport 51820
        set mappedport 51820
    next
end

config firewall service custom
    edit "WireGuard"
        set udp-portrange 51820
    next
end

config firewall policy
    edit 0
        set srcintf "wan1"
        set dstintf "internal"
        set srcaddr "all"
        set dstaddr "VIP-aisys-wg"
        set action accept
        set schedule "always"
        set service "WireGuard"
        set logtraffic all
    next
end
```

Jestli adresa 62.168.59.78 není pevná, dej `set extip 0.0.0.0`. Klienti se připojují přes DDNS jméno, takže změna adresy jim nevadí.

**Volitelně jen z Česka:** vytvoř adresu typu Geography a použij ji jako `srcaddr` místo `all`. Neplatí to pro roaming v zahraničí.

```
config firewall address
    edit "geo-CZ"
        set type geography
        set country "CZ"
    next
end
```

Na FortiGate **neotvírej** porty 22, 80 ani 443 směrem na VM. Pokud je na WAN zapnutá správa FortiGate (HTTPS/SSH admin), vypni ji nebo ji omez na důvěryhodné adresy (Trusted Hosts u admin účtu). U neaktualizovaného firmwaru je to největší riziko celé sítě.

**Test z internetu** (např. z mobilních dat): připojit WireGuard, na serveru `sudo wg show` musí u klienta ukazovat *latest handshake*, pak otevřít `https://10.105.0.1/`.

### Varianta B (nedoporučeno): web přímo do internetu

Jen pokud musí přistupovat lidé, kterým VPN nenastavíš. Pak je potřeba:

- VIP TCP 443 a 80 na VM (port 80 kvůli ověření Let's Encrypt), certifikát přes `certbot --apache -d lb-iot.fortiddns.com` a ve firewallu VM povolit 80/443 odkudkoli.
- Povinné dvoufázové přihlášení (TOTP) v aplikaci, fail2ban na neúspěšná přihlášení a omezení na Geography CZ.
- Ověřit, že Let's Encrypt vydá certifikát pro subdoménu fortiddns.com. Doménu sdílí všichni uživatelé FortiDDNS, takže může narazit na limity vydávání.

I tak zůstává riziko neopravovaného FortiGate a vystavení dat řídicího systému. Rozumný kompromis je varianta A pro všechny a pro ty bez VPN přístup jen z LAN.

## 6. Uživatelé, role a zabezpečení

### Role v aplikaci

Každý uživatel má vlastní účet a jednu ze tří rolí. Oprávnění kontroluje server u každé akce, ne jen skrytí tlačítek v prohlížeči.

| Akce | Prohlížení (`viewer`) | Prohlížení a změny (`editor`) | Admin (`admin`) |
| --- | --- | --- | --- |
| Prohlížet body, SpMaR, přehledy, export | ano | ano | ano |
| Upravit SpMaR, funkčnost, obrazovky | ne | ano | ano |
| Přidat a smazat řádek SpMaR | ne | ano | ano |
| Nahrát objects.dbf (import z Aisysu) | ne | ne | ano |
| Spravovat číselníky (typy, funkčnosti, obrazovky) | ne | ne | ano |
| Spravovat uživatele a role | ne | ne | ano |
| Prohlížet historii změn | ano | ano | ano |

Tabulky `uzivatel` a `zmena_log` jsou v `db/aisys_schema.sql`.

**Pravidla přihlášení:** hesla jen jako `password_hash()` (Argon2id), nová session po přihlášení (`session_regenerate_id`), odhlášení po 60 minutách nečinnosti, CSRF token u každého formuláře. Po 5 chybných pokusech se účet zamkne na 15 minut. Prvního admina založíš z příkazové řádky skriptem, který bude součástí aplikace.

### fail2ban

```bash
sudo apt install -y fail2ban python3-systemd
```

`/etc/fail2ban/jail.local`:

```ini
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5
backend  = systemd
banaction = nftables

[sshd]
enabled = true
```

`sudo systemctl restart fail2ban`, stav `sudo fail2ban-client status sshd`.

### Zálohy

**Databáze každý den** do `/var/backups/aisys` s uchováním 30 dní, soubor `/etc/cron.d/aisys-backup`:

```
30 2 * * * root mkdir -p /var/backups/aisys && mariadb-dump --single-transaction --routines aisys | gzip > /var/backups/aisys/aisys-$(date +\%F).sql.gz && find /var/backups/aisys -name '*.sql.gz' -mtime +30 -delete
```

**Celé VM:** v Proxmoxu *Datacenter → Backup → Add*, VM `aisys`, denně nebo týdně, režim Snapshot, nejlépe na jiné úložiště než disk VM (NAS, Proxmox Backup Server). Obnovu jednou za čas vyzkoušej.

## 7. Kontrolní seznam

- [ ] VM `aisys` běží, Debian 13 aktualizovaný, qemu-guest-agent aktivní
- [ ] Statická IP 192.168.105.20, mimo DHCP pool
- [ ] SSH jen klíčem, root se nepřihlásí
- [ ] nftables aktivní, `nft list ruleset` odpovídá kapitole 2
- [ ] unattended-upgrades zapnuté
- [ ] MariaDB: databáze `aisys`, uživatel `aisys_app` bez práv na změnu struktury, schéma a data nahraná
- [ ] Apache: web běží na `https://192.168.105.20/`, certifikát importovaný na klientech
- [ ] WireGuard `wg0` běží, každé zařízení má vlastní klíč a PSK
- [ ] FortiGate: VIP a politika jen pro UDP 51820, správa FortiGate z WAN vypnutá nebo omezená
- [ ] Test připojení z mobilních dat funguje
- [ ] fail2ban aktivní
- [ ] Denní dump DB a záloha VM v Proxmoxu, obnova vyzkoušená
- [ ] Nahrát PHP aplikaci a založit prvního admina

Na delší dobu stojí za zvážení náhrada FortiGate 110C za model s podporovaným firmwarem. Dokud tam je, nechej z internetu otevřený jen port WireGuardu.
