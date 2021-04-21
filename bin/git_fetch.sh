#!/usr/bin/env bash
#
# This script pulls my selected files from my GitHub repository and
# treats them as the 'master' copy
#
# Copyright (c) 2020-2021, Andrey "Limych" Khrolenok <andrey@khrolenok.ru>
# Creative Commons BY-NC-SA 4.0 International Public License
# (see LICENSE.md or https://creativecommons.org/licenses/by-nc-sa/4.0/)
#

WDIR=$(cd `dirname $0` && pwd)
ROOT=$(dirname ${WDIR})

# Check for required utilites and install it if they are not available
git --version >/dev/null || apk -q add git
gpg --version >/dev/null || apk -q add gnupg
test -n "$(which gawk)" || apk -q add gawk

# Include parse_yaml function
. ${WDIR}/_parse_yaml.sh

# Read yaml file
eval $(parse_yaml ${ROOT}/secrets.yaml)

cd ${ROOT}
git config user.name "${secret_git_user_name}"
git config user.email "${secret_git_user_email}"
git config core.sshCommand "ssh -i ${ROOT}/.ssh/id_rsa -oStrictHostKeyChecking=no"
git fetch origin master

gpg --import ${ROOT}/gpg_keys/*.asc
if git verify-commit origin/master; then
    # Update files only if commit is verified. Then restart Home Assistant
    git reset --hard origin/master && hassio homeassistant restart
    exit
fi

echo "Commit verification failed"
exit 1
