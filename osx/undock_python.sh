#!/bin/bash

python3_path1=`which python3`
python3_link_path1=`readlink $python3_path1`

dir1=`dirname $python3_path1`
dir2=`echo -n $python3_link_path1 | cut -d "/" -f 2-`

python3_path2="`dirname $dir1`/$dir2"
python3_link_path2=`readlink $python3_path2`

rdir1=`dirname $python3_path2`
rdir2=`echo -n $python3_link_path2 | cut -d "/" -f 2-`

python3_real_path="`dirname $rdir1`/$rdir2"

pdir1=`dirname $python3_real_path`
pdir2=`dirname $pdir1`

info_dir="$pdir2/Resources/Python.app/Contents"
info_file="$info_dir/Info.plist"

lines=`wc -l $info_file | awk '{print $1}'`
lines=$((lines-2))

if [ -z $(grep "LSUIElement" $info_file) ]; then 
  echo "Backing up \"$info_file\" into \"./Info.plist.bck\""
  cp $info_file ./Info.plist.bck
  head -n $lines ./Info.plist.bck > $info_file
  echo -e "\t<key>LSUIElement</key>" >> $info_file 
  echo -e "\t<true/>" >> $info_file
  tail -n 2 ./Info.plist.bck >> $info_file
else
  echo "File seems already patched - skipping"
fi
