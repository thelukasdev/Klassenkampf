# Verwaltung und getrennte Spielprozesse

Unter /admin mit bestehendem Passwort und Authenticator anmelden. LP-Logo, dunkle Flächen, grüne Buttons und türkisfarbene Titel entsprechen der Spielseite. Die Navigation ist auf kleinen Displays horizontal scrollbar.

## Bedienung
- Übersicht zeigt aktive Sitzungen, Online-Spieler und laufende Partien insgesamt sowie Details der ausgewählten Sitzung.
- Spielsitzungen: sechsstelligen Code kopieren, lokalen QR-Code mit direktem Beitrittslink anzeigen, Sitzung auswählen oder beenden.
- Spieler: suchen, trennen, sperren/entsperren, Credits zurücksetzen, Profil löschen oder in eine andere aktive Sitzung verschieben. Verschieben übernimmt Credits, Ergebnisse und Browserberechtigung. Derselbe Browser bleibt notwendig. Aktive Partien zuerst beenden. Bei Namenskollision wird das Verschieben abgelehnt.
- Spielsteuerung: Spiele freigeben, Sitzung oder einzelne Partien pausieren, Partien ohne zusätzliche Wertung beenden. Einstellbare Regeln: erlaubte Spiele, normales/doppeltes Simulationstempo, Credits für Sieg/Niederlage/Unentschieden (-100 bis 100). Mindestens ein Spiel muss freigegeben bleiben.
- Ergebnisse: Rangliste und die letzten 100 abgeschlossenen Partien ansehen, Rangliste bzw. bis zu 2000 gespeicherte Partien als CSV exportieren. Alte Partien vor diesem Update können nicht nachträglich rekonstruiert werden. Historische Namen bleiben beim Löschen eines Profils in Partieergebnissen erhalten.
- Sicherungen: pro Sitzung Spieler, Credits, Sperren, Modus, Regeln und Ergebnisverlauf sichern/wiederherstellen. Laufende Partien werden nicht wiederhergestellt; beim Laden ohne zusätzliche Wertung geschlossen.
- Zugriffsverwaltung (Inhaber): Konten, Passwort, Rollen und Sitzungszuweisungen. Administratoren verwalten alle Sitzungen; Spielleiter sehen und ändern ausschließlich explizit zugewiesene Sitzungen. 2FA gilt für alle Rollen. Die Inhaberrolle kann nicht entfernt werden.
- Aktivitäten: letzte 25 Verwaltungsaktionen mit Person, Zeitpunkt und Sitzung. Spielleiter sehen nur Aktionen ihrer Sitzungen.
- Serverstatus (Administratoren): App-Laufzeit, Verbindungen, RAM des App-Containers, freier Datenträgerspeicher, Host-Last, aktive Spielprozesse und Fehlerzähler seit Prozessstart.

## Architektur
Caddy übernimmt HTTPS, der App-Prozess verwaltet Anmeldung, WebSockets, Lobby und Speicherung. Jede spielende Sitzung erhält einen eigenen Python-Unterprozess ohne Netzwerkport und ohne übergebene Zugangsdaten. Jede Partie besitzt darin eine separate Engine-ID und ihren eigenen Zustand. Zustandsnachrichten gehen ausschließlich an ihre Teilnehmer, einschließlich spielerspezifischer Ansichten.

Es handelt sich um Prozessaufteilung der Simulation auf demselben VPS, nicht um zusätzliche physische Server oder eine Sicherheits-Sandbox. Spielprofile und Verwaltung liegen weiter zentral in SQLite. Eine Sitzung ohne laufende Partie braucht keinen Unterprozess. Nach der letzten Partie beendet sich dieser Prozess; beim nächsten Spiel wird er neu erstellt.

Der kleine VPS erlaubt maximal 16 aktive Sitzungen, davon höchstens acht gleichzeitig mit laufenden Spielen, maximal 16 Partien pro Sitzung. Unterprozesse haben auf Linux ein Adressraumlimit von 96 MiB; das App-Containerlimit bleibt zusätzlich wirksam. Ein ausgefallener Simulationsprozess beendet betroffene Partien ohne zusätzliche Wertung. Andere Sitzungsprozesse bleiben unabhängig. Die nächste Partie startet einen neuen Prozess. Der gemeinsame App-Prozess und die Datenbank bleiben gemeinsame Ausfallpunkte.

Zum lokalen Vergleich kann KLASSENKAMPF_WORKERS=0 die Simulation im App-Prozess aktivieren. Produktion verwendet standardmäßig 1. Ein späterer Wechsel auf mehrere Hosts benötigt einen Broker und eine gemeinsame Datenbank; diese Infrastruktur wurde hier nicht vorgetäuscht.

## Validierung
Automatisierte Tests prüfen Authentifizierung und 2FA, serverseitige Rollen-/Sitzungsrechte, Regeln, neutrale Abbrüche, Sicherungen, Spielerzuordnung, getrennte Engines, alle neun Spiele im Worker sowie einen echten WebSocket-Spielstart und Prozessausfall bei weiterlaufender zweiter Sitzung. Browserprüfungen prüfen QR, Regeländerung, Pause/Fortsetzen, CSV, Suche und alle neun Verwaltungsbereiche bei 390 Pixeln Breite.
