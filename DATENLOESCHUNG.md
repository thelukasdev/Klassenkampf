# Kontolöschung und Bereinigung

Unter **Kontoeinstellungen → Konto löschen**: aktuelles Passwort und `LÖSCHEN`. Server prüft Anmeldung, Origin, CSRF, Passwort und bestätigt unmittelbar vor dem Löschen im Schreibvorgang erneut Session und unveränderten Passwort-Hash. Alle Spieleranmeldungen/Codes/Rechte werden entfernt, eigene laufende Sitzungen geschlossen und eigene Replay-Freigaben widerrufen. Ein separater Verwaltungszugang bleibt bestehen. Andere Konten sind nicht über den Lösch-Endpunkt auswählbar.

| Daten | Frist |
| --- | --- |
| Beendete Sitzungen inkl. Ergebnisse, Profile und Sitzungssicherungen | 30 Tage nach Ende |
| Replays inkl. Freigaben | 7 Tage nach Aufnahmeende, ggf. früher bei Speicherlimit |
| Erledigte Fehlermeldungen | 30 Tage nach Erledigung |
| Offene Fehlermeldungen einschließlich Ticketverlauf | 90 Tage nach der letzten Aktivität |
| Aktivitätsprotokolle, Statusereignisse/Tageswerte | 90 Tage; Tageswerte auf UTC-Kalendertage begrenzt |
| Öffentliche Daten beendeter Sitzungen | 30 Tage nach Erkennung des Endes |
| Abgelaufene Anmeldungen, OAuth/MFA-/Registrierungs-/Resetdaten | Nächster Lauf nach Ablauf |
| Versuchsbegrenzungen | 24 Stunden ohne Aktualisierung |

App: beim Start und stündlich (`retention.cleanup`), maximal 100 alte Sitzungen pro Lauf. Dateipfade werden auf das Sitzungssicherungs-Verzeichnis begrenzt; aktive Räume werden ausgeschlossen. Fehler werden protokolliert und später erneut versucht. Statusdienst: beim nächsten Messlauf, stündliche Bereinigung. Bestehende erledigte Meldungen ohne Erledigungszeit bekommen den Umstellungszeitpunkt; wiederholtes Erledigen verlängert die Frist nicht, erneutes Öffnen setzt `resolved_at` zurück.

Keine automatische Löschung bestehender Konten oder aktiver Räume nach Alter. Die Bereinigung entfernt Datensätze aus der laufenden Anwendung, ist kein sicheres Überschreiben von Datenträgern. SQLite/WAL-Dateien, manuelle globale Sicherungen, alte Migrationsstände, Deployment-Backups und Exporte brauchen eine getrennte Betriebs- und Löschstrategie. Dockerprotokolle bleiben nach Größe begrenzt. Vor Wiederherstellung alter Backups müssen gelöschte Konten und abgelaufene Daten erneut entfernt werden.

Bei Kontolöschung werden eigene Tickets einschließlich aller Nachrichten entfernt.
