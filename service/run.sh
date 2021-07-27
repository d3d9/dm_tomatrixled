#!/bin/bash

brightness=${brightness:-20}

if [ ! $(id -u) -eq 0 ]; then
  echo "muss als root ausgeführt werden"
  exit 1
fi

if [ -z "$selection" ]; then
  echo "keine Auswahl angegeben.."
  exit 1
fi

# warten wegen Netzwerk usw.
# besser wäre es, wenn systemd-time-wait-sync.service verfügbar wäre
if [[ ! ( -z "$sleeptime" || $sleeptime -eq 0 )]]; then
  echo "sleeping $sleeptime s"
  sleep $sleeptime
  addsleep=3
  echo "sleeping for additional $addsleep s"
  sleep $addsleep
fi

if [ ! -z "$shutdowntime" ]; then
  echo "shutdown $shutdowntime"
  shutdown --no-wall $shutdowntime
fi

echo "selection: $selection"
case $selection in
feuerwache)
  ./dm_tomatrixled.py -s de:05914:2216 -b$brightness -er0 -w16 -l8 -f8 --led-slowdown-gpio 2 --update-steps 330 --sleep-interval 0.025 --test-ext https://d3d9.xyz:8008/data?id=feuerwache --hst-colors --platform-width 13 --local-deps "./feuerwache.csv" --nina-url "https://warnung.bund.de/api31/dashboard/" --nina-ags "059140000000" --nina-ignore-msgType "Update" --nina-ignore-id "lhp.HOCHWASSERZENTRALEN.DE.NW" --nina-ignore-id "mow.DE-NW-HA-SE087-20210723-87-000" # --no-rt-msg -1
  ;;
emilienplatz)
  ./dm_tomatrixled.py -s de:05914:2075:0:1 -b$brightness -er1 -l8 -f8 --update-steps 330 --ignore-infoid 45828_HST --ignore-infoid 54354_HST
  ;;
emilienplatz3)
  ./dm_tomatrixled.py -s de:05914:2075:0:1 -b$brightness -er3 -l8 -f8 --update-steps 330 --ignore-infoid 45828_HST --ignore-infoid 54354_HST -w15
  ;;
hagenhbfefa)
  ./dm_tomatrixled.py -s de:05914:2007 -b$brightness -er1 -l8 -f8 --update-steps 330
  ;;
hagenhbf)
  ./dm_tomatrixled.py -s de:05914:2007 -b$brightness -er1 -l8 -f8 --update-steps 330 --place-string ", Hagen (Westf)" --place-string "Hagen " --place-string "HA-" --ibnr "08000142"
  ;;
essenhbfefa)
  ./dm_tomatrixled.py -s de:05113:9289 -b$brightness -er1 -l8 -f8 --update-steps 330 --place-string "Essen " --place-string "E-"
  ;;
essenhbf)
  ./dm_tomatrixled.py -s de:05113:9289 -b$brightness -er1 -l8 -f8 --update-steps 330 --place-string ", Essen (Ruhr)" --place-string "Essen " --place-string "E-" --ibnr "08000098"
  ;;
*)
  echo "ungültige Auswahl $selection"
  exit 1
  ;;
esac
