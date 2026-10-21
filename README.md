# Klassenkampf

Browser-Minispiele mit parallelen Spielsitzungen, Webverwaltung und öffentlicher Statusseite. Serverfassung für Python 3.12, Linux und Docker Compose.

## Funktionen

- Neun Minispiele: Bomber, Connect4, Dots, Duel, Jump’n’Bump, Pong, Tanks, Tron und WnR.
- Getrennte Spielräume mit sechsstelligen Beitrittscodes und eigenen Spielern und Ergebnissen.
- Spielerkonten mit einmaliger E-Mail-Bestätigung bei der Registrierung; spätere Anmeldung nur mit Passwort. Passwortreset weiterhin per E-Mail-Code.
- Ein aktiver Spielraum je Spielerkonto, automatische Schließung nach fünf Minuten ohne ersten Beitritt oder einer Minute nach dem letzten Spieler.
- Verwaltung mit Authenticator-2FA, Rollen, Kontenverwaltung, Spielsteuerung, Ergebnissen und Sicherungen.
- Pro Spielerkonto schaltbare Zusatzrechte, eigene erweiterte Verwaltung und einstellbare Sitzungslimits.
- Zuschauerfreigaben und Replays für die Spielleitung.
- Einladungslinks und QR-Codes, Passwortänderung im Konto und Fehlermeldungen für angemeldete Nutzer mit Referenznummer und Verwaltungsansicht.
- Separate Statusüberwachung mit 90 Tagen Verlauf und Anzeige der letzten sechs Ereignisse.
- Unterprozess je spielender Sitzung, getrennte Spielzustände je Partie.

## Installation

Voraussetzungen: Linux-VPS, Docker Engine mit Compose-Plugin, Python 3 und eine Domain mit passendem DNS-Eintrag. Ports 80 und 443 müssen für Caddy erreichbar sein.

```sh
git clone https://github.com/thelukasdev/Klassenkampf.git
cd Klassenkampf
python3 configure.py spiele.example.org
```

Die erzeugte `.env` ist privat. Vor dem ersten Start ergänzen:

```dotenv
KLASSENKAMPF_OWNER_EMAIL=admin@example.org
SMTP_HOST=smtp.example.org
SMTP_PORT=587
SMTP_USER=spiele@example.org
SMTP_FROM=spiele@example.org
SMTP_PASSWORD=HIER_DAS_MAILPASSWORT_EINTRAGEN
```

Die automatisch erzeugten Token beibehalten. Eine vorhandene `.env` wird nicht überschrieben. SMTP-Port 587 verwendet STARTTLS, Port 465 TLS. Registrierung und Passwortreset benötigen Mailversand; die Passwortanmeldung bestätigter Konten funktioniert auch ohne Mailkonfiguration. Der separate Verwaltungszugang benötigt keine E-Mail-Codes.

```sh
docker compose config --quiet
docker compose up -d --build
docker compose exec app python set_admin_password.py
```

Das Passwort wird unsichtbar abgefragt. Anschließend `/admin` öffnen und den Authenticator einrichten. Den Inhaber vor dem ersten Start festlegen: Änderungen der Umgebungsvariable ersetzen einen bestehenden Inhaber nicht. Caddy richtet HTTPS für die konfigurierte Domain ein.

Teilnehmer treten auf der Startseite per Sitzungscode bei. Registrierte Nutzer verwalten ihre Runde unter `/account`. Der öffentliche Status liegt unter `/status`.

## Betrieb und Daten

```sh
docker compose ps
docker compose logs --tail=50 app status caddy
docker compose exec app python admin_cli.py sessions
docker compose exec app python admin_cli.py status --session SITZUNGS_ID
```

Nur Caddy veröffentlicht Netzwerkports. Der zusätzliche Konsolenzugang bindet im App-Container an Loopback und verwendet einen separaten Schlüssel. Die Anwendung läuft ohne Root-Rechte mit schreibgeschütztem Containerdateisystem.

Konten, Spielstände und Ergebnisse liegen in SQLite im Volume `game_data`; Replays und Sicherungen ebenfalls unter `/data`. Der Statusdienst hat das separate Volume `status_data`. Caddy speichert Zertifikate in eigenen Volumes. `docker compose down -v` löscht diese Daten. Vor Updates konsistente SQLite-Sicherungen und private Kopien der übrigen Daten erstellen. Zugangsdaten und Sicherungen niemals veröffentlichen.

Alle Dienste liegen auf demselben Host; dies ist keine Hochverfügbarkeitslösung. Grenzen: maximal 16 aktive Sitzungen, acht gleichzeitig mit Spielprozessen und 16 Partien je Sitzung. Die tatsächliche Kapazität hängt von der Hardware ab. Nach Neustarts bleiben Sitzungen erhalten; laufende Partien werden nicht fortgesetzt.

## Entwicklung und Tests

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Tests verwenden temporäre Daten und simulierten Mailversand. Sie prüfen unter anderem WebSockets, Rechte, 2FA, E-Mail-Codes, Passwortreset, Kontenlöschung, Sitzungsisolation, Unterprozesse, Replays und Statusverläufe. Der Stand wurde unter Python 3.12 auf Windows und im Linux-Container mit 141 Tests geprüft.

## Anleitungen

- [Verwaltungszugang](PASSWORT-LOGIN.md) und [Authenticator-2FA](ZWEI-FAKTOR.md)
- [Spielerkonten und Kontenverwaltung](SPIELERKONTEN.md)
- [Spielsitzungen](SPIELSITZUNGEN.md)
- [Verwaltung und Prozesse](VERWALTUNG-UND-PROZESSE.md)
- [Zuschauer und Replays](ZUSCHAUER-UND-REPLAYS.md)
- [Öffentlicher Status](OEFFENTLICHER-STATUS.md)

Enthalten sind Quellcode, statische Assets, Tests und allgemeine Deployment-Dateien. Persönliche Konfiguration, Datenbanken, Nutzerkonten, Schlüssel, Logs und Sicherungen sind ausgeschlossen.

## Impressum und Datenschutz
Die öffentlichen Seiten `/impressum` und `/datenschutz` benötigen eine private, vollständige Betreiberkonfiguration in `/data/legal.json`. Vorlagen und Anleitung: [RECHTLICHE-SEITEN.md](RECHTLICHE-SEITEN.md). Persönliche Betreiberangaben sind nicht im Repository enthalten. Vor öffentlichem Betrieb eigene Angaben, Vertragsgrundlagen und tatsächliche Datenverarbeitung prüfen und die Konfiguration einrichten.

Kontolöschung und automatische Löschfristen: siehe [DATENLOESCHUNG.md](DATENLOESCHUNG.md).

Automatische Wiederverbindung mit 30 Sekunden Partiepause: siehe [WIEDERVERBINDUNG.md](WIEDERVERBINDUNG.md).

Raumadressen ohne Beitrittscode und weiterhin direkte Einladungen: [RAUMADRESSEN.md](RAUMADRESSEN.md).

Öffentliche Demos für Vier gewinnt und Tennis42 gegen lokale Bots: [DEMO.md](DEMO.md). Zusätzliche Bot-/Regeltests für die Entwicklung: `node --test tests/test_demo_engine.cjs tests/test_demo_tennis.cjs` (18 Tests). Der Produktivserver benötigt dafür kein Node.js.

Revanche, Viererabstimmung und optionaler Warteraum: [RUNDENABLAUF.md](RUNDENABLAUF.md).

Private Support-Tickets mit Admin-Antworten, E-Mail-Link und Spieler-Verlauf: [TICKETS.md](TICKETS.md).

Beamer-Ansicht mit Live-Partie-Auswahl, Rangliste und widerrufbarer Freigabe: [BEAMER.md](BEAMER.md).

Zeichnen & Raten für vier bis acht Spieler: [ZEICHNEN-UND-RATEN.md](ZEICHNEN-UND-RATEN.md).

Hinweise zu Auslieferung, Verwaltung, Datenbankindizes und Verbindungsdiagnose: [PERFORMANCE.md](PERFORMANCE.md).

## Grafana Cloud

Optionales Monitoring mit begrenzten technischen Messwerten und einem kleinen Sender: [Einrichtung und Betrieb](monitoring/README.md). Keine lokale Grafana-/Prometheus-Installation erforderlich.
