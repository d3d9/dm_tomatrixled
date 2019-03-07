cat /tmp/out.ppm | sed 's/\x0/ /g' | hexdump -s 14 -v -e '384/1 "%_p" "\n"'
