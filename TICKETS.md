# Fehlermeldungen als Tickets

Angemeldete Spieler erstellen wie bisher eine Meldung unter `/report`. Neue Meldungen sind dem meldenden Konto zugeordnet. Unter `/tickets` und im Kontobereich finden Spieler ihre eigenen Tickets. Fremde Konten und Gäste erhalten keinen Zugriff auf Inhalte; der Link ersetzt keine Anmeldung.

In der Verwaltung unter **Fehlermeldungen → Ticket öffnen** können Inhaber und Administratoren den Verlauf lesen und mit **Antworten & E-Mail senden** antworten. Die E-Mail enthält die Antwort und den Ticketlink. Nach der Anmeldung führt der Link zurück zum Ticket. Spieler antworten dort im Browser; Antworten direkt auf die E-Mail werden nicht eingelesen. Neue Antworten öffnen erledigte Tickets erneut und schieben sie in der Verwaltungsübersicht nach oben. Beide Ansichten aktualisieren sich alle 30 Sekunden.

Der Versand nutzt dieselbe private SMTP-Konfiguration wie Registrierung und Passwortreset. Antworten werden vor dem Versand gespeichert. Bei Versandfehlern zeigt die Verwaltung den Fehlerstatus und bietet **E-Mail erneut senden**. Wiederholtes Absenden derselben Nachrichtenkennung erzeugt keine doppelten Nachrichten. Bereits als versendet bestätigte E-Mails werden nicht erneut verschickt. Nach einem unterbrochenen Versand ist nach zwei Minuten ein erneuter Versuch möglich. Bei einem Abbruch unmittelbar nach SMTP-Annahme kann ein erneuter Versuch eine E-Mail doppelt zustellen; die Ticketnachricht bleibt einmalig.

Ältere Meldungen haben keinen gespeicherten Absender. Für sie ist der Verlauf lesbar, aber es wird weder eine Kontozuordnung geraten noch eine Antwort an einen unbekannten Empfänger versendet.

Nachrichten sind auf 2000 Zeichen begrenzt. Antworten werden pro Konto und global begrenzt. Der Verlauf wird in Seiten mit bis zu 100 Nachrichten geladen. Admin-Aktionen protokollieren nur die Ticketreferenz, nicht den Antworttext. Spieler sehen keine internen Admin-E-Mail-Adressen oder Versanddetails.

Die Migration ergänzt `owner` und `last_activity` in `issue_reports` und legt `report_messages` an. Vor dem Update eine konsistente Sicherung der SQLite-Datenbank anlegen. Offene Tickets einschließlich Nachrichten werden 90 Tage nach letzter Aktivität entfernt, erledigte Tickets nach 30 Tagen. Die Löschung eines Spielerkontos entfernt dessen Tickets und Nachrichten sofort aus den laufenden Anwendungsdaten. Geschützte Betriebsbackups werden davon nicht rückwirkend verändert.

Tests: `python -m unittest discover -s tests -p test_tickets.py -v`. SMTP wird in den Tests simuliert; es gehen keine Test-E-Mails an echte Nutzer.
