#!/bin/bash
scriptdir=$(dirname $0)

#echo $scriptdir/venv/bin/python3 $scriptdir/main.py $@ >&2
# shellcheck disable=SC2068
"$scriptdir"/venv/bin/python3 "$scriptdir"/main.py $@
