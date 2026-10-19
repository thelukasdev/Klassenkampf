# Raumadressen und Einladungen

Nach gültigem Sitzungscode wird die Adressleiste per `replaceState` auf `/raum/<64 Hexzeichen>` gesetzt. Der Wert hängt vom zufälligen internen Raumbezeichner ab, nicht vom sechsstelligen Code. Er ist weder Code noch Zugangsberechtigung. Der öffentliche Pfad liefert lediglich die allgemeine Spielseite ohne Raumdaten; der WebSocket verlangt weiterhin einen gültigen Code.

Eine kopierte Raumadresse öffnet in einem neuen Browser die Code-Abfrage. Einladungslinks `/?code=…` und QR-Codes bleiben direkte Einladungen. Nach deren Verwendung wird der Code aus der Adressleiste entfernt. Der eigene, bereits angemeldete Tab kann mit gespeichertem Code und Spielerschlüssel weiterhin neu laden und wiederverbinden. `sessionStorage.cw_room_path` ordnet die Tab-Anmeldung der Raumadresse zu. Lokale Browserdaten sind keine zusätzliche serverseitige Berechtigung.

Der Ladebildschirm bleibt mindestens etwa zwei Sekunden sichtbar und wartet bei langsamer Verbindung länger.
