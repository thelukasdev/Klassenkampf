# Wiederverbindung während einer Partie

Nach erkanntem Verbindungsverlust pausiert nur die betroffene Partie für **30 Sekunden je fehlendem Spieler**. Die anderen Teilnehmer sehen Namen und Countdown. Der Client versucht automatisch, den WebSocket neu zu öffnen; dieselbe Sitzung, Rolle, Browserberechtigung und der letzte zulässige Spielzustand werden wiederhergestellt. Auch ein Neuladen im selben Browser kehrt zur laufenden Partie zurück, sofern der gespeicherte Spielerschlüssel verfügbar ist.

- Die Simulation tickt während der Wiederverbindung nicht weiter. Eingabemasken und gepufferte Tastendrücke werden zurückgesetzt; Eingaben während einer Pause werden verworfen. Funktioniert auch mit dem separaten Sitzungs-Spielprozess und verdeckten Spieleransichten.
- Die Wiederverbindung hebt weder manuelle Partiepausen noch Sitzungspausen auf. Nach Rückkehr aller Teilnehmer läuft die Partie weiter, sofern keine solche Pause besteht.
- Der Server überprüft Fristen unabhängig von manuellen Pausen. Nach Ablauf gilt die bisherige Abbruchwertung (Niederlage, Gegner gewinnt; in Mehrspielerpartien scheidet der betroffene Spieler aus). Sind alle Teilnehmer offline, endet die Partie ohne zusätzliche Wertung.
- Aufgeben, Sitzungswechsel, Sperren und administrative Beendigung warten nicht auf die Frist. Konto-/Sitzungslöschung und vorhandene automatische Leerraumfristen bleiben wirksam; 30 Sekunden liegen unter der 60-Sekunden-Leerraumfrist.
- Ein fehlerhafter Schlüssel kann weder das Profil übernehmen noch die Frist verlängern. Ein bereits abgelaufener Rückkehrversuch führt in die Lobby.
- Anwendungspings alle zehn Sekunden, Empfangsüberwachung im Client und 45 Sekunden Lese-Timeout im Server erkennen auch stille Ausfälle. Die 30 Sekunden beginnen bei Erkennung, nicht zwingend bei der physischen Unterbrechung. Gedrosselte Hintergrund-Tabs können vorübergehend neu verbinden müssen.
- Ein Serverneustart stellt keine laufende Spielsimulation wieder her; bestehende technische Abbruch- und Replayregeln gelten weiter.

Es gibt keine zusätzlichen Ports, Konten, Cookies oder dauerhaften Verbindungsprotokolle. Fristen liegen nur im Speicher der laufenden Partie. Replays verwenden weiterhin die normalen Zeitstempel; während der Pause bleibt das letzte Bild stehen.
