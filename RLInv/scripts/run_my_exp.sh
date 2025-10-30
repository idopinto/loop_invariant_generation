#!/usr/bin/env bash

name=$1
bname=$(basename $name)

# echo $name
# echo $bname

working_dir=my_exp  # Fixed: removed space
#mkdir the working_dir if it doesn't exist
if [ ! -d "$working_dir" ]; then
    mkdir $working_dir
fi

timeout 900 ./run.sh "$name".yml -v uautomizer -w $working_dir