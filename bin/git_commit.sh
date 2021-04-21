#!/usr/bin/env bash
#
# This script pushes my selected files to my GitHub repository
#
# Copyright (c) 2020-2021, Andrey "Limych" Khrolenok <andrey@khrolenok.ru>
# Creative Commons BY-NC-SA 4.0 International Public License
# (see LICENSE.md or https://creativecommons.org/licenses/by-nc-sa/4.0/)
#

WDIR=$(cd `dirname $0` && pwd)
ROOT=$(dirname ${WDIR})

# Check for required utilites and install it if they are not available
git --version >/dev/null || apk -q add git
test -n "$(which gawk)" || apk -q add gawk


# Include parse_yaml function
. ${WDIR}/_parse_yaml.sh || exit 1

# Read yaml file
eval $(parse_yaml ${ROOT}/secrets.yaml)

cd ${ROOT}

git config user.name "${secret_git_user_name}"
git config user.email "${secret_git_user_email}"
git config core.sshCommand "ssh -i ${ROOT}/.ssh/id_rsa -oStrictHostKeyChecking=no"

if [ "${ROOT}/secrets.yaml" -nt "${ROOT}/tests/fake_secrets.yaml" ]; then
    echo "Updating fake_secrets.yaml"
    ${ROOT}/bin/make_fake_secrets.sh
fi

git add . &&\
  git commit -m "${1:-Config files on `date +'%d-%m-%Y %H:%M:%S'`}" &&\
  git push -u origin master

