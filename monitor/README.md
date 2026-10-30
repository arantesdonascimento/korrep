# monitor app

## Szerepe
A `monitor` a meglévő `subscriptions.Subscriber` modellből dolgozik, saját feliratkozói modellje nincs. Feladatai:

- **Statisztika** (`services.py`): összes megerősített feliratkozó, elmúlt 24 óra (gördülő), megerősítésre váró jelentkezések. Mind ORM-lekérdezés, nincs külön számláló.
- **Gyűjtőfelület az adminban** (Monitor szekció): minden új feliratkozóról egy bejegyzés (*Subscriber notifications*), napi riportok (*Daily reports*), élő statisztika a lista tetején. Ez **email nélkül is működik**.
- **Email** (`notifications.py`): azonnali értesítés és napi riport, **csak ha** `MONITOR_NOTIFY_EMAIL` be van állítva.
- **Nyilvános számláló**: a főoldalon csak a megerősített feliratkozók száma látszik.

Fogalmak (a meglévő double opt-in alapján): *megerősített* = `is_active=True`; *megerősítésre váró* (`unconfirmed`) = `is_active=False`. A „24 óra” a beküldés (`created_at`) ideje szerint értendő, mellette külön szám a megerősítésekre (`activated_at`).

## Új és módosított fájlok
Új: `monitor/` (`apps`, `models`, `services`, `notifications`, `signals`, `views`, `admin`, `tests`, `management/commands/send_daily_report.py`, admin sablonok), `.env.example`.

Módosított:
| Fájl | Változás |
|---|---|
| `korrep/settings.py` | `monitor` az `INSTALLED_APPS`-ban; SMTP-kulcsok env-ből; `MONITOR_*`; `LOGGING` |
| `korrep/urls.py` | a `home` útvonal a `monitor.views.HomeView`-ra mutat (a név és a sablon ugyanaz) |
| `subscriptions/admin.py` | statisztikasáv a feliratkozói listán (a modell **nem** változott) |
| `templates/index.html` | számláló az 5. kártyán |

## Környezeti változók
Lásd `.env.example`. Új kulcsok: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `EMAIL_TIMEOUT`, `MONITOR_NOTIFY_EMAIL`, `MONITOR_REPORT_TIMEZONE`. Mind opcionális alapértékkel; a titkok csak a `.env`-ben legyenek.

## Telepítés és migráció (helyben)
```
copy db.sqlite3 db.sqlite3.bak          (előbb mentés)
python manage.py check
python manage.py makemigrations monitor
python manage.py migrate
```
A `makemigrations` csak a `monitor` számára hozhat létre fájlt (a válaszok naplója új táblát kap, ezért ha korábban már futtattad, most `0002_...` jön létre); a `subscriptions` nem változik. Ha mást is létrehozna, küldd el a kimenetet.

## Tesztek
```
python manage.py test monitor
```
A tesztek nem küldenek valódi emailt (locmem backend), külön teszt-adatbázist használnak, és nem függnek a `.env` tartalmától.

## Message mező
A feliratkozó űrlapon opcionális `Message` mező van (legfeljebb 1000 karakter, a `Subscriber.message` mezőbe kerül; ehhez a `subscriptions` appnak új migrációja van). Megjelenése:
- **Admin → Subscribers**: rövidített oszlop a listában, teljes szöveg a részletező oldalon (csak olvasható), és a keresés is erre is szűr.
- **Admin → Monitor → Subscriber notifications**: rövidített oszlop a listában, teljes szöveg a részletező oldalon.
- Az azonnali emailben teljes szöveggel, a napi összesítőben egy sorra rövidítve (legfeljebb 200 karakter).
- A nyilvános oldalakon sehol nem jelenik meg. Mindenhol HTML-escape-elve látszik.

## Működés email nélkül (jelenlegi állapot)
- A feliratkozói megerősítő levél a `console` backend miatt a `runserver` terminálban jelenik meg, a `SITE_MODE=local` szerinti `localhost` linkkel.
- Minden új feliratkozás bekerül az **Admin → Monitor → Subscriber notifications** listába, felül a statisztikákkal.
- A napi riport futtatása rögzíti az adatokat (**Admin → Monitor → Daily reports**), emailt nem küld.

## Küldő és fogadó cím (két külön dolog)
- **Fogadó**: `MONITOR_NOTIFY_EMAIL`. Bármilyen címe lehet, bármelyik szolgáltatónál, a Djangóban semmi mást nem kell hozzá beállítani.
- **Küldő**: az az SMTP-fiók/szolgáltatás (`EMAIL_HOST` stb.), amelyen keresztül a Django a leveleket kiküldi, és a `DEFAULT_FROM_EMAIL` (a „Feladó”). Ez nem azonos a fogadó címmel, de **szükséges**: SMTP-szolgáltatás nélkül semmilyen email nem megy ki, akármilyen a fogadó cím. A `DEFAULT_FROM_EMAIL` olyan cím legyen, amelyről a küldő fiók küldhet, különben a levél elutasításra vagy a spambe kerülhet.

Mit kap a fogadó cím:
- **Azonnal, minden új feliratkozásról**: a feliratkozó emailje, időpontja, az aktuális megerősített/várakozó számok és admin link (HTML + szöveges változat).
- **Naponta egy összesítőt**: a négy statisztika és az aznapi jelentkezők listája (időpont, email, állapot). A lista legfeljebb 200 sort tartalmaz, a többi az adminban látható. A telefonszám nem kerül a levélbe.

## Gmail beállítása (küldő és fogadó ugyanaz a cím)
1. A Google-fiókban kapcsold be a **2 lépéses azonosítást** (Google-fiók → Biztonság). Enélkül az alkalmazásjelszó nem hozható létre.
2. Hozz létre **alkalmazásjelszót** (Google-fiók → Biztonság → 2 lépéses azonosítás → Alkalmazásjelszavak, vagy myaccount.google.com/apppasswords). Ez egy 16 karakteres kód. A rendes Gmail-jelszó SMTP-hez nem működik.
3. A `.env` fájlba (soha ne commitold, és a jelszót senkinek ne küldd el):
```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=te@gmail.com
EMAIL_HOST_PASSWORD=abcdefghijklmnop
DEFAULT_FROM_EMAIL=te@gmail.com
MONITOR_NOTIFY_EMAIL=te@gmail.com
SITE_MODE=local
```
A `DEFAULT_FROM_EMAIL` lehet megjelenített névvel is: `Korrep <te@gmail.com>`. A Gmail a feladót úgyis a hitelesített fiókra állítja.
4. Indítsd újra a `runserver`-t (a `.env` csak induláskor töltődik be).
5. Próba:
```
python manage.py check_email_setup --send-test
```
A parancs kiírja a hatályos beállításokat (a jelszót soha nem), figyelmeztet a tipikus hibákra, és elküld egy teszt levelet a `MONITOR_NOTIFY_EMAIL` címre. Hibánál az `SMTPAuthenticationError` az alkalmazásjelszóra vagy a 2 lépéses azonosításra utal.

Tudnivalók:
- Személyes Gmail-fiókon naponta kb. 500 levél küldhető, ez bőven elég.
- A levelekben lévő linkek alapját (megerősítő link, admin és válasz linkek) a `SITE_MODE` kapcsoló adja, lásd a következő szakaszt.
- Ha a `MONITOR_NOTIFY_EMAIL` üres, nem megy értesítő, az adatok az adminban így is gyűlnek.
- **PythonAnywhere:** a beállítások ugyanezek, de a szerveren külön `.env` kell. Ingyenes fióknál a PythonAnywhere dokumentációja szerint a Gmail SMTP-szerverek ki vannak vételezve a tűzfalból, más SMTP-szerver nem érhető el; a fórumon viszont vannak friss jelentések elutasított kapcsolatról, ezért az első telepítés után a fenti `check_email_setup --send-test` próbát futtasd a szerver konzoljában.

## Localhost vagy szerver: a `SITE_MODE` kapcsoló
Egyetlen sor a `.env`-ben dönti el, hová mutatnak a levelekben lévő linkek (megerősítő link, admin- és válasz-linkek, napi összesítő):

| `SITE_MODE` | A linkek alapja |
|---|---|
| `local` (alapértelmezett) | `http://localhost:8000` |
| `server` | `https://korrep.pythonanywhere.com` |
| `custom` | a `.env` `SITE_URL` értéke (bármilyen más cím) |

A régi `SITE_URL` sor `local` és `server` mellett **figyelmen kívül marad**, így nem írja felül a kapcsolót; törölheted a `.env`-ből. Hibás érték esetén a Django induláskor érthető hibát ad.

**Fontos:** a link azt az alkalmazást kell elérje, amelyik a feliratkozót tárolja. A saját gépen leadott feliratkozás a helyi adatbázisba kerül, a szerveren leadott a szerveré. Ezért minden környezetnek saját `.env`-je van:
- **a gépeden**: `SITE_MODE=local`, a megerősítő link a helyi szerverre mutat, és működik;
- **a szerveren**: `SITE_MODE=server`, a linkek a `korrep.pythonanywhere.com`-ra mutatnak.
Ha a gépeden `server`-re állítod, a levelek a szerver linkjét tartalmazzák, de a feliratkozó a szerveren nem létezik, ezért a link nem találna semmit (404). A szerver teszteléséhez a feliratkozást magán a szerver oldalán add le.

A szerveren a `.env` minimuma (a titkos értékeket ott add meg, ne másold át a laptopról és ne commitold):
```
SECRET_KEY=<új, hosszú, véletlen érték>
DEBUG=False
ALLOWED_HOSTS=korrep.pythonanywhere.com
SITE_MODE=server
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=te@gmail.com
EMAIL_HOST_PASSWORD=<alkalmazásjelszó>
DEFAULT_FROM_EMAIL=te@gmail.com
MONITOR_NOTIFY_EMAIL=te@gmail.com
```
A napi összesítőt a szerveren a PythonAnywhere *Tasks* fülén kell ütemezni (`python manage.py send_daily_report`), mert a parancs magától nem fut. A `https://` címhez a beállítás automatikusan felveszi a `CSRF_TRUSTED_ORIGINS`-t is.

Ellenőrzés bármelyik környezetben:
```
python manage.py check_email_setup
python manage.py check_email_setup --send-test
```
Az első kiírja a hatályos módot és a linkek alapját, és figyelmeztet (például ha a gépnév nincs az `ALLOWED_HOSTS`-ban, SMTP mellett a linkek `localhost`-ra mutatnak, a `DEBUG` be van kapcsolva szerver módban, vagy a `.env`-ben maradt egy figyelmen kívül hagyott `SITE_URL`). A második egy teszt levelet is küld a `MONITOR_NOTIFY_EMAIL` címre.

## Válasz a feliratkozónak
- Az **azonnali értesítő** és a **napi összesítő** levélben a feliratkozó email-címe kattintható: a címre kattintva az admin **válaszűrlapja** nyílik meg (be kell jelentkezned az adminba). Mellette „Válasz küldése” gomb is van.
- Az adminban ugyanez: **Monitor → Subscriber notifications** (az email-cím a link), a **Subscribers** lista „✉ Reply” oszlopa és a feliratkozó oldalán a „✉ Reply” gomb.
- Az űrlap megmutatja a feliratkozó üzenetét és a korábbi válaszokat. A levél a beállított Gmail-fiókról megy ki (ugyanez a Gmail „Elküldött” mappájában is megjelenhet), a megerősítetlen címnél figyelmeztet.
- A válasz **csak akkor** kerül naplózásra (`Monitor → Sent replies`, és a feliratkozó oldalán), ha a küldés sikerült. Hibánál a szöveg megmarad az űrlapban.
- A **Subscribers** listán a „Replied” oszlop és a „reply status” szűrő mutatja, kinek nem válaszoltál még; a statisztikasáv és a levelek is kiírják a számot („Még nem kapott választ”).
- Jogosultság: a küldéshez a `change_subscriber` jog kell, a csak olvasási jog nem elég. A válaszok a feliratkozó törlésekor törlődnek.

## A megerősítő email
A feliratkozó a megerősítő levelet a Gmail-fiókról kapja. Ha a küldés hibázik, a feliratkozás ettől még mentve marad, a látogató érthető üzenetet kap (nem 500-as hibát), és ugyanazzal az email-címmel újra elküldheti az űrlapot: ilyenkor új sor nem jön létre, a megerősítő levél újra elmegy. Az már megerősített címet az űrlap elutasítja.

## Napi riport
Kézi futtatás:
```
python manage.py send_daily_report --dry-run          (csak a számokat írja ki)
python manage.py send_daily_report --preview riport.html   (a levelet HTML-fájlba írja, böngészőben megnyitható; nem ír DB-t, nem küld)
python manage.py send_daily_report                    (tegnap, Europe/Budapest szerint)
python manage.py send_daily_report --date 2026-10-28  (adott nap)
python manage.py send_daily_report --date 2026-10-28 --force   (újraszámol és újraküld)
```
Naponta egy riport készül (`report_date` egyedi), és riportonként legfeljebb egy email megy, akkor is, ha a parancs többször vagy egyszerre fut. Sikertelen küldésnél a parancs nem-nulla kilépési kóddal áll meg, a riport megmarad, és újrafuttatással újrapróbálható. A „total” és „unconfirmed” a riport generálásakori állapot.

Időzítés: a parancs maga nem ütemez. Éles környezetben a hosting ütemezőjét kell használni, például PythonAnywhere *Tasks* fül (napi feladat, az idő UTC szerint; a „tegnap” a kódban Budapest szerint számolódik, így a nyári/téli időszámítás nem okoz gondot), vagy Linux cron: `0 6 * * * cd /ÚT/korrep_project && /ÚT/python manage.py send_daily_report`.

## Nyilvános számláló és NODE-doboz
A főoldalon (`HomeView`) csak a NODE telemetria dobozban jelennek meg aggregált számok, mind **csak megerősített** feliratkozókból (`get_public_stats`), így a 24 órás és a 7 napos szám sosem lehet nagyobb az összesnél: **ÖSSZESEN** (összes megerősített), **ELMÚLT 24h** (az elmúlt 24 órában megerősítettek), **ELMÚLT 7 NAP** (az elmúlt 7 napban megerősítettek). A feliratkozás szakaszban nincs számláló.
Az adminban látható „New signups, last 24 hours” a *beküldéseket* számolja (a még megerősítetlenekkel együtt), ezért eltérhet a nyilvános 24h-s számtól.

A `HomeView` a `public_stats` objektumot adja a sablonnak (egy DB-lekérdezés, cache nélkül). Se email, se üzenet, se a megerősítésre várók száma nem jelenik meg a nyilvános oldalon.

## Admin elérés
`/admin/` → **Monitor** szekció (gyűjtő és napi riportok), **Subscriptions → Subscribers** (statisztikasáv). A meglévő Django jogosultságok érvényesek: a Monitor adatai csak olvashatók, kézzel nem hozhatók létre, és külön jogosultság kell hozzájuk (a superuser mindent lát).

## Éles telepítés előtti ellenőrzőlista
- [ ] `DEBUG=False`, új `SECRET_KEY` (ha a zip bárhová kikerült)
- [ ] `SITE_MODE=server`, és az `ALLOWED_HOSTS` tartalmazza a `korrep.pythonanywhere.com`-ot (`check_email_setup` ellenőrzi)
- [ ] valódi SMTP és `DEFAULT_FROM_EMAIL`, `MONITOR_NOTIFY_EMAIL`
- [ ] `db.sqlite3` mentése, `migrate`, `collectstatic` (a `style.css` miatt)
- [ ] a napi riport ütemezése, és egy kézi `--dry-run`
- [ ] teszt-feliratkozás végigpróbálása, majd a gyűjtő és az email ellenőrzése
- [ ] adatvédelmi tájékoztató és hozzájárulási szöveg tisztázva

## Visszaállítás
1. `python manage.py migrate monitor zero` (csak a monitor táblái törlődnek, a feliratkozók nem)
2. `'monitor.apps.MonitorConfig'` törlése az `INSTALLED_APPS`-ból
3. `korrep/urls.py`: a `home` visszaállítása `TemplateView.as_view(template_name='index.html')`-ra; `subscriptions/admin.py`, `templates/index.html`, `static/style.css` visszaállítása (a mellékelt `changes.diff` visszafelé alkalmazható)
4. A `monitor/` mappa törölhető.
Vagy egyszerűen az `db.sqlite3.bak` visszamásolása, ha a migrálás előtt mentettél.
