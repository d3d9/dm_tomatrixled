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
emilienplatz)
  ./dm_tomatrixled.py -s de:05914:2075:0:1 -b$brightness -per1 -l8 -f8 --update-steps 330 --ignore-infoid 45828_HST --ignore-infoid 54354_HST # --test-d3d9 emilienplatz-land
  ;;
emilienplatz3)
  ./dm_tomatrixled.py -s de:05914:2075:0:1 -b$brightness -per3 -l8 -f8 --update-steps 330 --ignore-infoid 45828_HST --ignore-infoid 54354_HST -w15 # --test-d3d9 emilienplatz-land
  ;;
hagenhbfefa)
  ./dm_tomatrixled.py -s de:05914:2007 -b$brightness -per1 -l8 -f8 --update-steps 330
  ;;
hagenhbf)
  ./dm_tomatrixled.py -s de:05914:2007 -b$brightness -per1 -l8 -f8 --update-steps 330 --place-string ", Hagen (Westf)" --place-string "Hagen " --place-string "HA-" --ibnr "08000142"
  ;;
essenhbfefa)
  ./dm_tomatrixled.py -s de:05113:9289 -b$brightness -per1 -l8 -f8 --update-steps 330 --place-string "Essen " --place-string "E-"
  ;;
essenhbf)
  ./dm_tomatrixled.py -s de:05113:9289 -b$brightness -per1 -l8 -f8 --update-steps 330 --place-string ", Essen (Ruhr)" --place-string "Essen " --place-string "E-" --ibnr "08000098"
  ;;
*)
  echo "ungültige Auswahl $selection"
  exit 1
  ;;
esac
