#!/usr/bin/env bash
#
# This script updates radio stations list in configs
#
# Copyright (c) 2020, Andrey "Limych" Khrolenok <andrey@khrolenok.ru>
# Creative Commons BY-NC-SA 4.0 International Public License
# (see LICENSE.md or https://creativecommons.org/licenses/by-nc-sa/4.0/)
#

WDIR=$(cd `dirname $0` && pwd)
ROOT=$(dirname ${WDIR})

STATIONS_FPATH=${ROOT}/radio_stations.yaml  # From here we get list of radio stations
MEDIA_FPATH=${ROOT}/packages/media.yaml     # There we patch configs

INPUT=""
AUTOMATION=""

s='[[:space:]]*' 

# Check for required utilites and install it if they are not available
test -n "$(which gawk)" || apk -q add gawk

parse() {
   local callback=${2:-'%s%s%s=\"%s\"'}
   local w='[^:]*' fs=$(echo @|tr @ '\034'|tr -d '\015')
   sed -e "/^[ \t]*#/d" \
        -ne "s|^\($s\)\($w\)$s:$s\"\(.*\)\"$s\$|\1$fs\2$fs\3|p" \
        -e "s|^\($s\)\($w\)$s:$s\(.*\)$s\$|\1$fs\2$fs\3|p" "$1" |
   gawk -F$fs "{
      indent = length(\$1)/2;
      vname[indent] = \$2;
      for (i in vname) {if (i > indent) {delete vname[i]}}
      if (length(\$3) > 0) {
         vn=\"\"; for (i=0; i<indent; i++) {vn=(vn)(vname[i])(\"_\")}
         printf(\"$callback\n\", \$2, \$3);
      }
   }"
}

quote() {
  echo "$1" | sed 's|\([&./]\)|\\\1|g'
}

# Define callback
stations() {
  local key=$(quote "$1") value=$(quote "$2")

  INPUT="${INPUT}      - \"${key}\"\n"
  if [ "$AUTOMATION" == "" ]; then
    AUTOMATION="${AUTOMATION}            {% if is_state(\"input_select.radio_station\", \"${key}\") %}${value}\n"
  else
    AUTOMATION="${AUTOMATION}            {% elif is_state(\"input_select.radio_station\", \"${key}\") %}${value}\n"
  fi
}

eval $(parse ${STATIONS_FPATH} 'stations \"%s\" \"%s\";')

TMP_FPATH=${MEDIA_FPATH}.tmp
sed ":a;N;\$!ba;s/\($s# INPUT_BEGIN$s\n\).*\n\($s# INPUT_END\)/\1${INPUT}\2/g" "$MEDIA_FPATH" |
sed ":a;N;\$!ba;s/\($s{# AUTOMATION_BEGIN #}$s\n\).*\n\($s{# AUTOMATION_END #}\)/\1${AUTOMATION}\2/g" >"$TMP_FPATH"
mv -f "$TMP_FPATH" "$MEDIA_FPATH"

exit
