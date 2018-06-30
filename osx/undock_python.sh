#!/bin/bash

version=`python3 --version | cut -d " " -f 2`
path="/usr/local/Cellar/python/$version/Python*3.app/Contents"
info_file="$path/Info.plist"

lines=`wc -l $info_file | awk '{print $1}'`
lines=$((lines-2))

if [ -z $(grep "LSUIElement" $info_file) ]; then 
  echo "Backing up Info.plist in Info.plist.bck"
  cp $info_file ./Info.plist.bck
  head -n $lines ./Info.plist.bck > $info_file
  echo -e "\t<key>LSUIElement</key>" >> $info_file 
  echo -e "\t<true/>" >> $info_file
  tail -n 2 ./Info.plist.bck >> $info_file
else
  echo "FOUND"
fi
