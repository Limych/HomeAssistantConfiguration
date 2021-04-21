#!/usr/bin/env sh
#
# This script …
#
# Copyright (c) 2020-2021, Andrey "Limych" Khrolenok <andrey@khrolenok.ru>
# Creative Commons BY-NC-SA 4.0 International Public License
# (see LICENSE.md or https://creativecommons.org/licenses/by-nc-sa/4.0/)
#

WDIR=$(cd `dirname $0` && pwd)
ROOT=$(dirname ${WDIR})
DATA_DIR='/tmp'

# Check for required utilites and install it if they are not available
test -n "$(which gawk)" || apk -q add gawk

# Include parse_yaml function
. ${WDIR}/_parse_yaml.sh

# Read yaml file
eval $(parse_yaml ${ROOT}/secrets.yaml)

REPO_ID_FPATH="${DATA_DIR}/travisci_repo_id.txt"
LAST_BUILD_FPATH="${DATA_DIR}/travisci_last_build.txt"

if [ ! -f "${REPO_ID_FPATH}" ]; then
    curl -s https://api.travis-ci.org/repos/${secret_github_repo} | jq .id >"${REPO_ID_FPATH}"
fi
if [ ! -f "${LAST_BUILD_FPATH}" ]; then
    touch "${LAST_BUILD_FPATH}"
fi

repo_id=`cat ${REPO_ID_FPATH}`
last_build=`cat ${LAST_BUILD_FPATH}`

report=`curl -s -H "Travis-API-Version: 3" "https://api.travis-ci.org/repo/${repo_id}/branch/master"`

current_build=`echo "${report}" | jq .last_build.number`
current_build="${current_build%\"}"
current_build="${current_build#\"}"

current_state=`echo "${report}" | jq .last_build.state`
current_state="${current_state%\"}"
current_state="${current_state#\"}"

if [ "$current_state" == "passed" -a "$current_build" != "$last_build" ]; then
    echo "$current_build" >"${LAST_BUILD_FPATH}"
    exit
fi

exit 1
