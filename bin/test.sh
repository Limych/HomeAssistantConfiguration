#!/usr/bin/env bash

#set -x

WDIR=$(cd `dirname $0` && pwd)
ROOT=$(dirname ${WDIR})

# Check for required utilites and install it if they are not available
test -n "$(which gawk)" || apk -q add gawk

# Include parse_yaml function
. ${WDIR}/_parse_yaml.sh

# Read yaml file
echo $(parse_yaml ${ROOT}/secrets.yaml)

