# Impressum und Datenschutz

Die öffentlichen Seiten `/impressum` und `/datenschutz` sind aus allen Footern verlinkt. Bei der Registrierung steht zusätzlich ein Datenschutzhinweis. Die Seiten benötigen keine Anmeldung und setzen selbst keine Cookies. Sie verwenden ausschließlich lokale Darstellungsmittel.

Die HTML-Vorlagen unter `templates/` enthalten keine persönlichen Betreiberangaben. Diese liegen nur im privaten Daten-Volume in `/data/legal.json`. Die Datei wird nicht in Git oder ins Docker-Image aufgenommen. Fehlt eine vollständige freigegebene Konfiguration, liefern die beiden Seiten HTTP 503 statt erfundener Angaben.

Erforderliche Konfiguration (Beispielwerte vor Nutzung vollständig ersetzen):

```json
{
  "published": true,
  "name": "Vorname Nachname",
  "street": "Musterstraße 1",
  "postal_code": "12345",
  "city": "Musterstadt",
  "country": "Deutschland",
  "email": "kontakt@example.org",
  "hosting_provider": "Tatsächlicher Hostinganbieter",
  "hosting_location": "Stadt, Land",
  "updated": "TT.MM.JJJJ"
}
```

Die Datei muss für den App-Benutzer 10001 lesbar sein, beispielsweise mit Eigentümer `10001:10001` und Modus `600`. Die Anwendung liest sie bei jedem Seitenaufruf erneut. Datei konsistent über eine temporäre Datei ersetzen; keine Zugangsdaten hinzufügen. Der Statusdienst benötigt diese Datei nicht.

Die Datenschutzerklärung beschreibt die tatsächlichen Funktionen einschließlich zeitlich begrenzter Spielhistorien, manueller Fehlermeldungen, privater Sicherungen und lokaler Browserberechtigungen. Sie ersetzt keine organisatorischen Maßnahmen: Verträge zur Auftragsverarbeitung mit Infrastruktur- und Mailanbietern, konkrete Speicher- und Löschpraxis sowie Änderungen an Empfängern und Drittlandverarbeitung müssen vom Betreiber geprüft und aktuell gehalten werden. Andere Hosting- oder Mailanbieter erfordern auch eine Anpassung der Links und Texte in der Vorlage.

Die Kontolöschung ist unter Kontoeinstellungen verfügbar. Die Anwendung bereinigt beendete Sitzungen nach 30 Tagen, Replays nach sieben Tagen, erledigte Meldungen nach 30 Tagen, offene Meldungen und Aktivitäts-/Statusverläufe nach 90 Tagen. Details und Ausnahmen für separate Betriebsbackups, globale Sicherungen und alte Migrationsstände: `DATENLOESCHUNG.md`.

Die Seiten sind ein auf diesen Softwarestand abgestimmter Entwurf. Eine verbindliche Prüfung der rechtlichen Vollständigkeit, insbesondere der eingesetzten Vertrags- und Dienstleisterkonstellation, ist damit nicht verbunden.
