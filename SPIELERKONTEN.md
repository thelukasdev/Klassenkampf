# Spielerkonten und eigene Sitzungen

Die Startseite bietet oben **Anmelden** und **Registrieren**, der Verwaltungslink wurde dort entfernt. Teilnahme per Sitzungscode funktioniert weiterhin ohne Spielerkonto. **Meine Sitzungen** führt zu `/account`; die unabhängige Verwaltung bleibt unter `/admin` erreichbar.

## Ablauf
Freie Registrierung mit E-Mail-Adresse und Passwort (12 bis 256 Zeichen). Erst ein einmaliger sechsstelliger E-Mail-Code bestätigt das Konto. Bei jeder weiteren Anmeldung werden erneut Passwort und ein neuer E-Mail-Code benötigt. Codes gelten fünf Minuten, haben höchstens fünf Versuche und werden nach erfolgreicher Bestätigung verbraucht. Anmeldungen gelten acht Stunden; Abmelden widerruft die entsprechende Sitzung sofort.

Jedes Spielerkonto kann eine eigene aktive Sitzung erstellen, höchstens fünf neue Sitzungen in 24 Stunden. Zusätzlich gilt weiterhin die Kapazität des Servers von 16 aktiven Sitzungen. Spieler sehen ausschließlich ein kleines Panel zum Starten, Teilen, Beitreten und Beenden ihrer eigenen Sitzung. Regeln, Spielerbearbeitung, Sicherungen, Replays und Serverstatus sind für diese Konten auch per API gesperrt. Administratoren sehen weiterhin alle Sitzungen. Kontenverwaltung und Systemstatus bleiben der Verwaltung vorbehalten.

Spielerkonten verwenden separate Passwort- und Code-Tabellen sowie eigene Cookies. Interne, eindeutig mit `player:` benannte Konten haben ausschließlich die Rolle `host`; selbst dieselbe E-Mail-Adresse wie ein Administratorkonto führt nicht zu Verwaltungszugriff. Alle freigegebenen Aktionen überprüfen die eigene Sitzungszuordnung serverseitig. Die Authenticator-2FA der Verwaltung wurde nicht durch E-Mail-Codes ersetzt.

## Mailkonfiguration
Die Anwendung liest `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_FROM`, `SMTP_PASSWORD` ausschließlich aus der geschützten Serverkonfiguration. Das Passwort gehört nicht in Quellcode, statische Dateien oder Archive. Der Statusdienst erhält diese Variablen nicht.

IONOS verwendet hier Port 587 mit STARTTLS und Zertifikatsprüfung; Port 465 war vom VPS aus nicht erreichbar. Die authentifizierte SMTP-Verbindung wurde vom Server erfolgreich geprüft. Verifikation der Zustellung an echte Empfänger erfolgt bei deren eigener Registrierung/Anmeldung; automatische Tests versenden keine echten E-Mails.

Missbrauchsbegrenzungen: höchstens drei Code-Mails pro E-Mail-Adresse in zehn Minuten, fünf Code-Mails pro Absender-IP in 15 Minuten und insgesamt 30 pro Stunde. Anmeldung/Registrierung sind zusätzlich begrenzt. Rate-Limits und Codeversuche werden in SQLite gespeichert und bleiben nach einem Neustart wirksam. Bei SMTP-Ausfällen wird kein Konto ohne E-Mail-Bestätigung angelegt und kein Spielerzugang ausgegeben.

Die Daten liegen in `/data/admin.sqlite3` und werden durch vollständige Datenbanksicherungen mit erfasst. Über „Passwort vergessen?“ kann ein neues Passwort mit einem einmaligen E-Mail-Code gesetzt werden (5 Minuten, höchstens 5 Versuche). Danach werden alle Spieler-Anmeldungen und ausstehenden Anmeldecodes dieses Kontos widerrufen. Admin-Zugänge bleiben getrennt.

## Automatisches Ende
Neue Spielersitzungen schließen nach fünf Minuten ohne ersten Beitritt. Nach dem letzten getrennten Teilnehmer gilt eine Minute Wiederverbindungsfrist. Ein erfolgreicher Beitritt setzt diese Leerfrist zurück; ein geöffnetes Kontopanel oder Zuschauer zählt nicht als Spielteilnahme. Beitritt mit gültigem Sitzungscode zählt bereits vor der Nickname-Auswahl. Fristen werden gespeichert; Prüfung spätestens alle zehn Sekunden sowie vor Kontostatus/Neuerstellung. Das gilt ausschließlich für Spielersitzungen, nicht für Sitzungen der Verwaltung. Bereits bestehende Mehrfachsitzungen eines Spielerkontos werden auf eine reduziert; eine verbundene Sitzung wird bevorzugt erhalten.

## Kontenverwaltung
Inhaber und Administratoren finden unter **Spielerkonten** die registrierten Konten, eine E-Mail-Suche und Seiten mit jeweils 25 Konten. Spielleiter und Spielerkonten haben keinen Zugriff. „Abmelden“ widerruft alle Spieler-Anmeldungen und offenen Anmelde-/Resetcodes. „Konto löschen“ entfernt zusätzlich das Spielerkonto, seine Zuordnungen und die Gastgeber-Metadaten und beendet eigene aktive Spielrunden. Historische Runden und Ergebnisse sowie die Aktivitätsprotokolle bleiben erhalten. Ein gleichnamiges Verwaltungskonto bleibt einschließlich Passwort und Authenticator getrennt erhalten. Änderungen werden protokolliert. Nach Löschung ist eine neue Registrierung mit derselben E-Mail möglich.
