# Zuschauen und Replays

## Zuschauen
In der Verwaltung eine Sitzung auswählen, unter **Spielsteuerung** eine laufende Partie mit **Zuschauer freigeben** öffnen. Danach sind **Zuschauen** und **Link kopieren** verfügbar. Teilnehmer sehen die freigegebene Partie außerdem in ihrer Lobby.

Der Link enthält einen zufälligen, widerrufbaren Schlüssel im URL-Fragment. Der Viewer öffnet keinen Spieler-WebSocket und sendet keine Spieleingaben; er liest maximal fünfmal pro Sekunde die neueste Spielansicht über einen separaten HTTP-Endpunkt. Diese Freigabe zeigt auch die Teilnehmernamen der Partie. Ein Link darf bewusst weitergegeben werden; alle Empfänger können bis zum Widerruf zuschauen.

**Freigabe beenden**, Partieende oder Serverneustart widerrufen den Link. Eine neue Freigabe erstellt einen neuen Schlüssel. Spiele mit verdeckten spielerspezifischen Ansichten (derzeit W’n’R) bleiben vom öffentlichen Zuschauen ausgeschlossen. Spielerprofile, Sitzungscodes und Browser-Tokens werden nicht an Zuschauer übertragen.

## Replays
Neue Partien werden automatisch ab ihrem Start als Spielzustände aufgezeichnet. Unter **Ergebnisse → Replays → Replay öffnen** stehen Abspielen/Pause, Zeitleiste, 0,5×/1×/2×/4×, Perspektivwechsel und JSON-Download bereit. Die Perspektiven eines verdeckten Spiels sind ausschließlich im geschützten Replay verfügbar. Spielleiter sehen Replays ihrer zugewiesenen Sitzungen; Administratoren alle Sitzungen. Die Berechtigung wird für jede Metadaten- und Chunk-Anfrage serverseitig geprüft, auch für archivierte Sitzungen.

Bestehende Partien vor dem Update können nicht nachträglich aufgezeichnet werden. Ein Replay ist eine bildhafte Wiedergabe gespeicherter Zustände, keine erneute Simulation mit nachgebildetem Zufall. Es beeinflusst weder Credits noch Ergebnisse.

## Ressourcen und Aufbewahrung
- Höchstens zehn Zustände pro Sekunde, komprimierte Chunks aus ungefähr 100 Frames; Abschlussbild und reale Pausenzeiten bleiben enthalten.
- Maximal 16 gleichzeitig aufzeichnende Partien. Andere Partien laufen weiter, werden jedoch in der Verwaltung als **Keine Aufnahme** gekennzeichnet.
- Pro Replay maximal 16 MiB unkomprimierte Aufnahmedaten. Bei Erreichen des Limits wird die Aufnahme beendet und als **Teilaufnahme** ausgewiesen; die Partie läuft weiter.
- Sieben Tage nach dem Ende wird ein Replay nicht mehr ausgeliefert; Dateibereinigung mindestens stündlich sowie bei Start/Abschluss von Aufzeichnungen.
- Maximal 256 MiB abgeschlossene komprimierte Aufnahmen: Älteste werden bei Bedarf vorher entfernt. Laufende, einzeln begrenzte Aufnahmen kommen hinzu.
- Der Download exportiert das Replay mit Metadaten und Frames als JSON zur Archivierung; ein Import fremder Dateien ist derzeit nicht vorgesehen.

Die Dateien liegen im bestehenden persistenten Spiel-Volume unter `/data/replays`, die Metadaten in `/data/admin.sqlite3`. Öffentliche statische Routen liefern diese Dateien nicht aus. Die Spielstand-Sicherung einzelner Sitzungen enthält keine Replay-Dateien; vollständige Server-Backups müssen Datenbank und Replay-Verzeichnis zusammen sichern. Der unabhängige Statusverlauf bleibt separat.

Schreibarbeit erfolgt über begrenzte Hintergrundwarteschlangen. Ein Speicherausfall beendet die Aufzeichnung, nicht das Spiel. Nach einem ungeplanten Neustart werden bereits geschriebene Chunks als Teilaufnahme gerettet; der noch nicht geschriebene letzte Puffer kann fehlen. Reguläres Herunterfahren wartet auf das Abschließen der Aufnahmen.
