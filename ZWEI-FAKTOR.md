# Anmeldung mit Authenticator-App

Die Verwaltung erfordert jetzt immer zwei Faktoren: E-Mail/Passwort und einen Code aus einer Authenticator-App. Teilnehmer können ohne Konto per Sitzungscode beitreten. Spielerkonten verwenden E-Mail-Codes.

## Erstmalig einrichten

1. `https://spiele.example.org/admin` öffnen und die bisherigen Zugangsdaten eingeben.
2. Den angezeigten QR-Code mit der Authenticator-App auf dem eigenen Handy scannen. Alternativ den Schlüssel unter „Manuell einrichten“ verwenden.
3. Den sechsstelligen App-Code eingeben und bestätigen. Erst dieser Schritt aktiviert den zweiten Faktor und erlaubt den Verwaltungszugriff.
4. Die zehn angezeigten Wiederherstellungscodes sicher aufbewahren. Sie werden nur einmal angezeigt; jeder ersetzt genau einmal einen App-Code.

Bei weiteren Anmeldungen wird nur der aktuelle App-Code abgefragt, kein neuer QR-Code. Die Handyzeit sollte automatisch eingestellt sein. Die Uhr des VPS wird synchronisiert.

## Verlorenes Handy

Nach Eingabe des Passworts „Wiederherstellungscode verwenden“ wählen und einen noch unbenutzten Code eingeben. Verwendete Codes sind sofort ungültig.

Wenn weder Handy noch Wiederherstellungscodes vorhanden sind, über die vertrauenswürdige SSH-Konsole zurücksetzen:

```sh
cd /opt/klassenkampf
docker compose exec app python reset_admin_2fa.py
```

Die Rückfrage mit `RESET` bestätigen. Für ein anderes Konto `--email adresse@beispiel.de` ergänzen. Danach beim nächsten Passwortlogin den neuen QR-Code scannen. Der Reset beendet bestehende Verwaltungssitzungen des Kontos. Ein normaler Passwortwechsel setzt 2FA ausdrücklich nicht zurück.

## Technische Eigenschaften

TOTP gemäß RFC 6238, SHA-1, sechs Stellen, 30-Sekunden-Intervalle mit Toleranz eines Intervalls. Bereits verwendete Zeitcodes werden nicht erneut akzeptiert. Einrichtung erst nach korrektem Passwort und gültigem ersten App-Code. Vorher gibt es nur eine fünf Minuten gültige, nicht zur Verwaltung berechtigende Zwischensitzung. Fünf Fehlversuche sperren weitere Code-Prüfungen des Kontos für bis zu 15 Minuten; neue Passwort-Anmeldungen umgehen dieses Limit nicht.

Die QR-Codes werden direkt auf dem Server erzeugt und über die eigene HTTPS-Verbindung übertragen. Kein QR-Webdienst erhält den Einrichtungsschlüssel. Einmalcodes, QR-Inhalte und Wiederherstellungscodes werden nicht protokolliert. Wiederherstellungscodes werden nur gehasht in SQLite gespeichert. Der TOTP-Schlüssel muss zur Prüfung serverseitig vorliegen und ist in der zugriffsgeschützten Datenbank gespeichert. Datenbank und vollständige Backups entsprechend privat aufbewahren.
