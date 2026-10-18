# Verwaltung mit E-Mail und Passwort

Die Verwaltung unter `/admin` verwendet E-Mail, Passwort und verpflichtende Authenticator-2FA. Google ist deaktiviert. Spielerkonten verwenden ein separates Passwort und bestätigen ihre E-Mail nur bei Registrierung und Passwortreset; siehe [SPIELERKONTEN.md](SPIELERKONTEN.md).

## Ersten Zugang einrichten

Vor dem ersten Start `KLASSENKAMPF_OWNER_EMAIL` in der privaten `.env` setzen. Danach:

```sh
docker compose exec app python set_admin_password.py
```

Das Passwort wird zweimal unsichtbar abgefragt. Bei der ersten Browseranmeldung den QR-Code mit der Authenticator-App scannen und die Wiederherstellungscodes privat sichern. Siehe [ZWEI-FAKTOR.md](ZWEI-FAKTOR.md).

## Weitere Zugänge

Der Inhaber verwaltet unter **Zugriffsverwaltung** Administratoren, Spielleiter, Rollen, Passwörter und Sitzungszuweisungen. Alle Verwaltungsrollen verwenden 2FA. Der Inhaber kann nicht entfernt werden. Passwörter enthalten mindestens zwölf Zeichen. Das Anlegen eines Verwaltungskontos versendet keine E-Mail; Zugangsdaten separat übermitteln.

## Passwort vergessen

Über die vertrauenswürdige Serverkonsole:

```sh
docker compose exec app python set_admin_password.py --email admin@example.org
```

Die Änderung beendet Verwaltungssitzungen des Kontos, erhält die Authenticator-Einrichtung und gilt sofort. Für verlorene Authenticator-Geräte siehe [ZWEI-FAKTOR.md](ZWEI-FAKTOR.md). Kein Standardpasswort und kein öffentlicher Admin-Passwortreset.

Gespeichert werden gesalzene PBKDF2-SHA256-Hashes mit 600.000 Iterationen. HTTPS, HttpOnly-Cookies, CSRF-/Origin-Prüfungen und begrenzte parallele Passwortprüfungen schützen die Anmeldung. Datenbank, 2FA-Schlüssel und Sicherungen privat halten.
