# Projekt

Ziel dieses Projekts ist, Abfahrten im ÖPNV auf LED-Matrizen darzustellen.
Dazu wird [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) (genauer gesagt [dieser Fork](https://github.com/d3d9/rpi-rgb-led-matrix)) mit dem Raspberry Pi verwendet.

Ursprünglich habe ich die EFA-Schnittstelle vom [VRR](http://openvrr.de) nur so ausprobiert, dabei vor allem das Darstellen von Abfahrten, was überraschend einfach ging. Dann wollte ich es mit LED-Matrizen verbinden, um eine interessante Darstellung zu erhalten, nicht nur in der Kommandozeile. Daraus entstand das hier sichtbare Projekt.    
Mittlerweile können auch Daten der DB eingebunden werden[.](https://twitter.com/cabinentaxi/status/1095810658355068930)

In der zweiten Jahreshälfte 2018 wurde die Entwicklung über das Mobilitätsstipendium Baden-Württemberg gefördert, der Projekttitel lautet "Preiswertes digitales Fahrgastinformationssystem für Schaufenster, Geschäfte, Wohnungen und Räume".

<span float="left">
<a href="https://github.com/d3d9/dm_tomatrixled/raw/_media/matrix_closeup.jpg">
<img src="https://github.com/d3d9/dm_tomatrixled/raw/_media/_thumb/matrix_closeup.jpg" width="28%"></a>
<a href="https://github.com/d3d9/dm_tomatrixled/raw/_media/matrix_above.jpg">
<img src="https://github.com/d3d9/dm_tomatrixled/raw/_media/_thumb/matrix_above.jpg" width="37%"></a>
<a href="https://github.com/d3d9/dm_tomatrixled/raw/_media/matrix_differentconfig.jpg">
<img src="https://github.com/d3d9/dm_tomatrixled/raw/_media/_thumb/matrix_differentconfig.jpg" width="32%"></a>
</span>

Beispielvideos: [Datenaktualisierung](https://github.com/d3d9/dm_tomatrixled/raw/_media/matrix_dataupdate.webm), [Verspätung & Infotext](https://github.com/d3d9/dm_tomatrixled/raw/_media/matrix_messages_delay.webm), [Teilausfall](https://github.com/d3d9/dm_tomatrixled/raw/_media/matrix_earlytermination.webm)

__Nutzungsbeispiele__ siehe [service/run.sh](service/run.sh).    
__Lizenzen__ siehe [LICENSE.md](LICENSE.md).

Das Projekt hat noch keine schöne Bezeichnung, deswegen bleibt es hier erstmal noch beim "temporären" Repo-Titel.

## Ziele
Zeitnah sollen (eventuell erst temporär) Matrizen mit dieser Software in Schaufenstern an Haltestellen aufgestellt werden, um da wo es geht für bessere Fahrgastinformation und für Aufmerksamkeit auf das Vorhandensein von Echtzeitdaten zu sorgen sowie Rückmeldungen zu erhalten und auszuwerten.

Dieses Projekt wird wahrscheinlich nicht ausschlaggebend weit verbreitet werden können, aufgrund einiger Voraussetzungen (Strom, Internet, Indoor, ...). Ich hoffe, dass es in vielen weiteren Situationen eingesetzt werden kann, und dass dieses Projekt auf dem Weg zu einer insgesamt besseren Fahrgastinformation die Vorteile und auch aktuelle Probleme (u. a. in Datenqualität, -bereitstellung, Lizenzen usw.) verständlich darstellen kann, wovon letztendlich jede erdenkliche Datennutzung weiterer Anwendungen profitieren kann.

Weitere softwarebezogene Ideen und Ziele sind in den [Projekten](https://github.com/d3d9/dm_tomatrixled/projects) enthalten.

## Gefördert von
<a href="https://vm.baden-wuerttemberg.de/de/verkehrspolitik/zukunftskonzepte/digitale-mobilitaet/mobilitaetsstipendium-bw/"><img alt="Ministerium für Verkehr Baden-Württemberg" src="https://github.com/d3d9/dm_tomatrixled/raw/_media/logo_vmbw.png" width="250"></a>


# Funktionalität
Folgend werden einige Möglichkeiten der Software beschrieben.

### Konfiguration
Es gibt viele Kommandozeilenparameter sowie weitere potenzielle Einstellungen, eventuell wird das besser strukturiert sein.    
Verschiedene Betriebs- und Darstellungsbezogene Dinge können konfiguriert werden, siehe Anfang von [dm_tomatrixled.py](dm_tomatrixled.py).

Grundsätzlich ist es möglich, weitere, z. B. größere Schriftarten zu nutzen, dabei wurde allerdings noch nicht viel getestet und manche Parameter müssen je nach Schrift manuell angepasst werden. Proportionale Schriftarten werden unterstützt. Wichtig ist, dass in der Regel ein Pixel rechts frei sein soll, dies ist eine Annahme, die aktuell noch an vielen Stellen im Code vorhanden ist.    
Auch andere Symbole können verwendet werden.

Es wird eine Logdatei geschrieben, die Anfang und Ende sowie auftretende Fehler und ggf. die fehlerhaften Schnittstellendaten protokolliert, optional wird auch eine Datei geschrieben, in der die Datenaktualisierungszeitpunkte sowie die Anzahl der enthaltenen Abfahrten (und Anzahl der Echtzeitabfahrten) festgehalten werden.    
Alle diese Informationen werden auch auf der Standardfehlerausgabe ausgegeben und sind, wenn man den systemd service (siehe unten) nutzt, auch über journalctl aufrufbar (z. B. ```journalctl -o cat -fu matrix```, optional auch bunt mit ```| ccze -A``` dahinter).

Konfiguration bezogen auf die LED-Matrizen ist unter [hzeller/rpi-rgb-led-matrix/README.md](https://github.com/hzeller/rpi-rgb-led-matrix/blob/master/README.md) beschrieben.

Beispiel mit mehreren Matrizen:    
<a href="https://github.com/d3d9/dm_tomatrixled/raw/_media/matrix-128x64.jpg"><img src="https://github.com/d3d9/dm_tomatrixled/raw/_media/_thumb/matrix-128x64.jpg" width="40%"></a>

### Darstellung

__Abfahrtszeilen__:    
Jede Abfahrtszeile besteht aktuell aus Liniennummer, Zieltext, Countdown, und optional Steignummer. Weitere Möglichkeiten wie eigene Steigsymbole/-referenzen oder ergänzende Symbole soll es zukünftig geben.    
Horizontale Abstände in Pixeln zwischen den folgend genannten Elementen können angegeben werden (beispielsweise dass zwischen Zieltext und Countdown 1px frei sein muss).

Für die Liniennummer kann eine Hintergrundfarbe verwendet werden. Die Breite in Pixel kann mit Parameter ```-w``` angepasst werden. Es wird versucht, die Liniennummer so passend wie möglich darzustellen, indem z. B. bei Grenzfällen eine kleinere Schriftart verwendet wird. Wenn etwas abgeschnitten werden muss, die Liniennummer aber z. B. "ICE" am Anfang hat, so wird anstatt einer abgeschnittenen Bezeichnung nur noch "ICE" angezeigt.

Für den Countdown wird basierend auf der Verspätung bzw. der Verfügbarkeit von Echtzeitdaten eine Farbe ausgewählt, die Grenzen (ab wann etwas eine leichte oder hohe Verspätung ist) können angepasst werden.    
Einstellbar kann anstatt eines Verkehrsmittelsymbols auch nur "0min" angezeigt werden. Die Darstellung vom "min" an sich ist ebenfalls einstellbar; so wie auch das Blinken bei sofortigen Abfahrten.    
Fahrtausfälle werden standardmäßig mit einem Symbol (aktuell ein kleiner Text "fällt aus") dargestellt.    
Abfahrten ab einem konfigurierbaren Countdownwert, z. B. ab 60 Minuten Entfernung, werden mit der absoluten Uhrzeit dargestellt.

Zieltexte werden jeweils mit so viel Platz, wie noch zwischen Liniennummer und Countdown verfügbar ist, dargestellt. Mit dem mehrfach nutzbaren Parameter ```--place-string``` können zu entfernende Ausschnitte wie z. B. "Hagen ", "HA-" oder ", Hagen (Westf)" vorbereitend entfernt werden, ein Abkürzungsverzeichnis o. ä. gibt es aber noch nicht.

__Scrollzeilen__:    
Die vorhandenen Meldungen besitzen optional auch zugehörige Symbole, diese können gemeinsam mit dem Text gescrollt werden. Standardmäßig wird nach der letzten Meldung etwas Platz gelassen, um "Durchläufe" voneinander zu unterscheiden.    
Aktuell gibt es noch keine eingebaute Logik, die bei Meldungsaktualisierung darauf achtet, keine Sprünge/vollen Resets zu machen, wenn dies nicht nötig ist.    
Deswegen kommt es aktuell bei einer hohen Anzahl an Aktualisierungen sowie sich ändernden Meldungen zu erkennbaren Sprüngen an den Anfang, dies ist z. B. insbesondere bei Hauptbahnhöfen oder anderen Haltestellen mit relativ vielen Abfahrten erkennbar.    
Immerhin: Die offiziellen Anzeigen machen es meistens nicht viel besser 😌 (und das sogar schon wenn auch nur Abfahrtsinformationen bei gleichbleibender scrollender Nachricht aktualisiert werden, gerne auch sehr oft nacheinander..).

__Weiteres__:    
Optional kann als erste Zeile eine Überschrift mit dem Haltestellennamen dargestellt werden.    
Außerdem gibt es mit dem Kommandozeilenparameter ```-r``` die Möglichkeit, rechts etwas Platz wegzunehmen, um die Uhrzeit und Symbole dadrunter darzustellen, oder platzsparend auch nur die Uhrzeit vertikal darzustellen. Der horizontale Abstand zu den zuvor genannten Zeileninhalten kann angepasst werden. Die Option -r3 (horizontale Uhrzeit mit Symbol dadrunter) erlaubt ganz unten immernoch scrollenden Text, so dass zumindest dafür die volle Matrizenbreite verwendet werden kann, siehe Beispieldarstellung unten.

Mit dem Kommandozeilenparameter ```--write-ppm DATEINAME``` kann laufend eine binäre ppm-Datei von der Matrizenausgabe erstellt werden (am besten an einem Standort, der sich nicht auf der microSD-Karte befindet, z. B. als tmpfs).

__Beispieldarstellung__ (```--write-ppm```-Ausgabe, mit [ppmtools/ppm-enlarger.py](ppmtools/ppm-enlarger.py) bearbeitet):    
![Beispieldarstellung](https://github.com/d3d9/dm_tomatrixled/raw/_media/ppm-beispiel.png)

### Datenladung
Aktuell werden Daten von EFA-Systemen (z. B. VRR, EFA-BW, ...) sowie von der Deutschen Bahn über [db-rest](https://github.com/derhuerst/db-rest) unterstützt. Weitere Datenquellen können hinzugefügt werden.    
Mehrere Datenquellen können parallel abgefragt werden, um so z. B. für verschiedene Verkehrsmittel unterschiedliche Quellen zu benutzen, oder mehrere Haltestellen/Steige gleichzeitig abzufragen, wenn die Datenquelle selber diese Möglichkeit nicht anbietet. Auch Datenquellen, die nur Informationstexte liefern, ohne Abfahrtsdaten, können verwendet werden.    
Es ist möglich, Ersatzquellen anzugeben. Wenn beispielsweise 4 Mal keine Abfrage bei der VRR EFA erfolgen konnte, wird auf EFA-BW als Fallback zurückgegriffen.

Abfragen erfolgen aktuell noch nicht basierend auf der Uhrzeit (z. B. "sofort zu jeder neuen Minute"), sondern basierend auf Darstellungsschritten. Die "sleeptime" zwischen jedem neuen Bild sowie die gewünschte Schrittanzahl ergeben multipliziert ungefähr die erwartbare Aktualisierungsrate, beispielsweise sorgen 0.03 s * 330 Schritte + etwas Latenz (Datenabfragen an sich) für neue Daten ca. alle 11 Sekunden.

Standardmäßig werden automatisch zusätzliche Meldungen generiert, aktuell wird dies für Verspätungen (wenn eine Fahrt eigentlich dargestellt werden sollte, dies aber nicht so ist weil genug andere Fahrten vor dem verspäteten Abfahrtszeitpunkt abfahren und demnach die hoch verspätete Fahrt verdecken) und für frühzeitig endende Fahrten getan (Beispiele siehe oben verlinkte Videos).

Die Datenladung erfolgt in einem eigenen Prozess, in dem wiederum für jede Quelle die spezifische Bearbeitung in einem eigenen Thread "parallel" erfolgt. Auf die Darstellung gibt es keine großen negativen Auswirkungen, z. B. fließt scrollender Text währenddessen ungestört weiter (außer auf Systemen mit einem CPU-Kern).

### Wiederverwendbarkeit
Einiges vom Code kann vermutlich auch außerhalb dieses Projekts und außerhalb des Nahverkehrskontexts verwendet werden, beispielsweise die Scrollzeilen aus dm_lines.py oder die Versuchslogik aus dm_depdata.py. Eventuell lässt sich weiteres verallgemeinern und besser nutzbar machen; außerdem fehlt an sehr vielen Stellen noch Dokumentation.


# Installation
__Voraussetzungen__
* Raspberry Pi (z. B. 3 Model B+ oder 4; insbesondere die viel älteren Modelle oder auch Pi Zero sind hierfür nicht empfohlen) mit (micro)SD-Karte, Netzteil usw.
* LED-Matrizen und alles dafür benötigte, siehe https://github.com/hzeller/rpi-rgb-led-matrix/blob/master/README.md.

__Vorgehensweise__
1. Raspbian Lite auf dem Pi installieren, (empfohlen:) ssh aktivieren (leere Datei "ssh" in der Bootpartition erstellen) und verbinden.
2. apt-get update und upgrade durchführen, dann grundsätzliche Konfiguration mit raspi-config vornehmen (z. B. WLAN einrichten, Interfaces ausschalten, ...), ggf. weiteres wie z. B. tmpfs unter /tmp einrichten, isolcpus=3 in /boot/cmdline.txt ergänzen, dtparam=audio=off in /boot/config.txt ergänzen, mehr siehe oben verlinktes Readme. Danach neustarten.
3. Sicherstellen, dass Python 3.8 oder höher installiert ist
4. ```apt-get install git libjpeg-dev libopenjp2-7 python3-pip```, ggf. venv aktivieren, ```pip3 install -r requirements.txt```
5. ```git clone```: [d3d9/rpi-rgb-led-matrix](https://github.com/d3d9/rpi-rgb-led-matrix) sowie [d3d9/dm_tomatrixled](https://github.com/d3d9/dm_tomatrixled) (hier).
6. Im rpi-rgb-led-matrix-Verzeichnis siehe <https://github.com/d3d9/rpi-rgb-led-matrix/tree/master/bindings/python#building>
7. Im dm_tomatrixled-Verzeichnis: siehe Beispiele, das Programm (als Root) ausführen, ggf. Optionen, insbesondere bzgl. der Matrix, anpassen. Bei Darstellungsproblemen Hinweise unter [hzeller/rpi-rgb-led-matrix/README.md](https://github.com/hzeller/rpi-rgb-led-matrix/blob/master/README.md) beachten. Weitere Probleme gerne hier melden.

### Service
Im Verzeichnis [service/](service/) befinden sich Dateien, mit denen man das Programm beim Systemstart automatisch ausführen lassen kann. Es kann je nach Bedarf angepasst werden.    
Mit z. B. ```sudo systemctl enable /home/pi/dm_tomatrixled/service/matrix.service``` lässt es sich direkt für den Systemstart aktivieren.  
Vorher sollte die Datei ```run.env.example``` in eine Datei ```run.env``` kopiert werden.
