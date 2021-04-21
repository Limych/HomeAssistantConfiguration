#!/usr/bin/env sh
##
## This is service function which can parse YAML-file.                                ##
##

# Source: https://gist.github.com/pkuczynski/8665367

if test -z "$(which gawk)"; then
  echo "ERROR! GNU awk not found."
  exit 1
fi

parse_yaml() {
   local prefix=${2:-'secret_'}
   local callback=${3:-'%s%s%s=\"%s\";'}
   local s='[[:space:]]*' w='[a-zA-Z0-9_\-]*' fs=$(echo @|tr @ '\034'|tr -d '\015')
   sed -ne "s|,$s\]$s\$|]|" \
        -e ":1;s|^\($s\)\($w\)$s:$s\[$s\(.*\)$s,$s\(.*\)$s\]|\1\2: [\3]\n\1  - \4|;t1" \
        -e "s|^\($s\)\($w\)$s:$s\[$s\(.*\)$s\]|\1\2:\n\1  - \3|;p" $1 | \
   sed -ne "s|,$s}$s\$|}|" \
        -e ":1;s|^\($s\)-$s{$s\(.*\)$s,$s\($w\)$s:$s\(.*\)$s}|\1- {\2}\n\1  \3: \4|;t1" \
        -e    "s|^\($s\)-$s{$s\(.*\)$s}|\1-\n\1  \2|;p" | \
   sed -ne "s|^\($s\):|\1|" \
        -e "s|^\($s\)-$s[\"']\(.*\)[\"']$s\$|\1$fs$fs\2|p" \
        -e "s|^\($s\)-$s\(.*\)$s\$|\1$fs$fs\2|p" \
        -e "s|^\($s\)\($w\)$s:$s[\"']\(.*\)[\"']$s\$|\1$fs\2$fs\3|p" \
        -e "s|^\($s\)\($w\)$s:$s\(.*\)$s\$|\1$fs\2$fs\3|p" | \
   sed 's/"/\\"/g' | \
   gawk -F$fs "{
      indent = length(\$1)/2;
      vname[indent] = \$2;
      for (i in vname) {if (i > indent) {delete vname[i]}}
      if (length(\$3) > 0) {
         vn=\"\"; for (i=0; i<indent; i++) {vn=(vn)(vname[i])(\"_\")}
         printf(\"$callback\n\", \"$prefix\", vn, \$2, \$3);
      }
   }"
}
