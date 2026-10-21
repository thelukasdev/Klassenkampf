# Auslieferung, Verwaltung und Datenbank

CSS, JavaScript, SVG und HTML werden bei geeigneter `Accept-Encoding`-Angabe
komprimiert ausgeliefert. `gzip;q=0` wird respektiert. PNG/WebP sind bereits
komprimierte Bildformate. Statische Assets erhalten repräsentationsabhängige
ETags und `public, max-age=0, must-revalidate`: Browser speichern sie, prüfen
aber bei Wiederverwendung auf Änderungen. HTML, Konten und APIs bleiben
`no-store`. Eine 304-Antwort enthält keinen Body. HEAD liefert nur Header.
Cloudflares bestehende Cache-Bypass-Regel für die Spieldomain bleibt erhalten.

Ein auf 16 MiB und 128 Einträge begrenzter Dateicache hält Original und
gzip-Version vor. Dateigröße und Änderungszeit invalidieren den Cache. Die
Statusseite verwendet dieselbe Auslieferung; ihre Sicherheitsheader bleiben
erhalten. `lp-logo-small.webp` ist eine 256-Pixel-Variante des Original-Logos,
`lp-icon.png` ein separates 64-Pixel-Favicon. Das Original bleibt unverändert.

Die Verwaltung fragt Übersichten nur bei sichtbarem Tab ab und überspringt sie
in Konten-/Ticketansichten. Gleichzeitige Übersichtsabfragen werden zusammengeführt;
veraltete Antworten nach einem Sitzungswechsel werden verworfen. Unveränderte
Snapshots lösen keinen DOM-Neuaufbau aus. Rein laufende Systemmetriken und die
Partiedauer erzwingen außerhalb ihrer jeweiligen Ansicht keinen Neuaufbau.

Replay-Listen nutzen einen partiellen Index nach Sitzung und Startzeit;
abgeschlossene Replays zusätzlich einen Index nach Endzeit. Ticketlisten haben
Indizes für die Aktivitätssortierung, mit und ohne Statusfilter. Vorhandene
Indizes für Besitzer, Nachrichten, Primärschlüssel und Freigaben bleiben erhalten.
Die Ranglisten liegen im Arbeitsspeicher; hierfür ist kein SQL-Index sinnvoll.
Die neuen Indizes entstehen beim Start ohne Löschung bestehender Daten.
Tests prüfen die tatsächlichen SQLite-Ausführungspläne auf vermeidbare Sortierung.

Bei einer gestörten Spielverbindung prüft der Client `/healthz`, mit Zeitlimit und
höchstens einer Prüfung je zehn Sekunden. Er unterscheidet Offline-Zustand,
HTTP-Serverfehler und erreichbaren Server bei unterbrochener WebSocket-Verbindung.
Eine fehlgeschlagene HTTP-Verbindung nennt Netzwerk, DNS oder TLS als mögliche
Ursachen. Browser können diese Ursachen nicht zuverlässig einzeln bestimmen;
lädt die Seite gar nicht erst, kann auch ihre JavaScript-Diagnose nicht laufen.

Prüfungen: `python -m unittest discover -s tests -q` sowie
`node --test tests/test_beamer_performance.cjs`. Browserprüfungen umfassen
Sitzungswechsel, Freigaben, unveränderte DOM-Knoten, Hintergrundtabs,
Verbindungshinweise und die Darstellung auf kleinen Bildschirmen.
