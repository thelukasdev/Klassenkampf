# Parallele Spielsitzungen

In der Verwaltung unter **Spielsitzungen** einen Namen eingeben und **Spielsitzung starten** wählen. Der Server erzeugt einen eigenen sechsstelligen Code aus gut unterscheidbaren Buchstaben und Zahlen. Diesen Code an die Teilnehmer weitergeben. Spieler geben ihn auf `https://spiele.example.org` ein und wählen dann ihren Namen.

## Trennung

Jede Sitzung hat eigene Spielerprofile, Browser-Schlüssel, Credits, Ranglisten, Sperren, Spielmodi, Herausforderungen, Partien und Sicherungen. Gleiche Spielernamen sind in unterschiedlichen Sitzungen erlaubt. Die Spielleitung sieht im Auswahlfeld oben immer, welche Sitzung gerade verwaltet wird. Änderungen an Spielern oder Spielständen gelten nur für diese Auswahl. Verwaltungsrechte und Verwaltungskonten gelten weiterhin für die gesamte Verwaltung.

Bis zu 16 Sitzungen können gleichzeitig aktiv sein. Das ist eine Obergrenze, keine Zusage für 16 parallel voll besetzte Räume auf dem kleinen VPS. Tatsächliche Last hängt von Spielerzahl und Spielen ab.

## Sitzung beenden

Unter **Spielsitzungen** auf **Beenden** klicken und bestätigen. Der Beitrittscode wird ungültig, alle Verbindungen dieser Sitzung werden geschlossen und laufende Partien neutral beendet. Andere Sitzungen laufen weiter. Rangliste, Credits und Sicherungen bleiben zur Ansicht erhalten. Beendete Sitzungen sind schreibgeschützt und lassen sich nicht mit ihrem alten Code betreten. Für eine neue Runde eine neue Sitzung starten.

## Neustart und Migration

Aktive Sitzungen behalten ihren Code und ihre Ergebnisse bei einem Serverneustart. Spieler verbinden sich mit ihrem Browser-Schlüssel erneut. Laufende Partien werden nicht wiederhergestellt. Beendete Sitzungen bleiben beendet.

Der bisherige gemeinsame Spielbetrieb wird beim ersten Start einmalig als **Bisherige Spielsitzung** übernommen, einschließlich Spielern, Credits, Modus und bisherigem Code. Dieser Übergangscode ist länger als neu erzeugte Codes. Groß-/Kleinschreibung, Leerzeichen und Bindestriche werden bei der Code-Eingabe normalisiert. Der alte Betrieb ist danach ebenfalls eine regulär beendbare Sitzung.

## Speicherung und Sicherungen

`/data/admin.sqlite3` enthält die Tabelle `game_rooms` mit Metadaten und Spielstand jeder Sitzung. Bestehende Verwaltungsberechtigungen und Verwaltungssitzungen bleiben unberührt. Die bisherigen Einträge in `game_state` und `state.json` bleiben als Legacy-Bestand erhalten und werden nicht als gemeinsamer aktueller Spielstand verwendet. Aktuelle Sitzungsdaten aus SQLite sichern, nicht nur `state.json` kopieren.

Benannte Sicherungen werden pro Sitzung unter `/data/session-saves/<sitzungs-id>/` abgelegt. Alte allgemeine Sicherungen verbleiben unter `/data/saves`; sie werden nicht automatisch in andere Sitzungen geladen. Backups sollten immer das gesamte Daten-Volume einschließlich einer konsistenten SQLite-Kopie umfassen.

## SSH-Verwaltung

```sh
cd /opt/klassenkampf
docker compose exec app python admin_cli.py sessions
docker compose exec app python admin_cli.py create-session "Klasse 8a"
docker compose exec app python admin_cli.py status --session SITZUNGS-ID
docker compose exec app python admin_cli.py code --session SITZUNGS-ID
docker compose exec app python admin_cli.py save freitag --session SITZUNGS-ID
docker compose exec app python admin_cli.py end-session --session SITZUNGS-ID
```

Schreibende Spielverwaltungsaktionen benötigen jetzt eine explizite Sitzungs-ID. Die ID steht in der Sitzungsübersicht. `status` ohne ID zeigt eine Zusammenfassung der Sitzungen.

Der Google-Login der Browserverwaltung benötigt weiterhin einen eingerichteten OAuth-Client; siehe `GOOGLE-LOGIN.md`. Die Sitzungsfunktion umgeht diesen Schutz nicht.
