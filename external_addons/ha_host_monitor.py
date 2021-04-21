#!/usr/bin/env python

#  Copyright (c) 2020, Andrey "Limych" Khrolenok <andrey@khrolenok.ru>
#  Creative Commons Attribution-NonCommercial-ShareAlike License v4.0
#  (see COPYING, LICENSE or https://creativecommons.org/licenses/by-nc-sa/4.0/)

# An actual version of this script you always can download from
# https://github.com/Limych/HomeAssistantConfiguration/tree/master/external_addons

import argparse
import datetime
import json
import multiprocessing
import os
import re
import socket
import subprocess

import psutil
import requests
import urllib3

VERSION = '1.1.1'

FREENAS = False
# noinspection PyBroadException
try:
    FREENAS = 'FreeNAS' in open('/etc/version').read()
except Exception:
    pass


class HddTemp:
    @staticmethod
    def hdd_temp(hdd):
        # noinspection PyBroadException
        try:
            for line in subprocess.Popen(
                    ['smartctl', '-A', str('/dev/' + hdd)],
                    stdout=subprocess.PIPE, encoding='utf8'
            ).stdout.read().split('\n'):
                line = line.split()
                if len(line) and line[0] == '194':
                    return [hdd, line[9]]
        except Exception:
            pass

    def hdds_temp_dict(self, hdds_list):
        pool = multiprocessing.Pool(
            min(8, max(multiprocessing.cpu_count(), 2)))
        results = []
        for hdd in hdds_list:
            results.append(pool.apply_async(func=self.hdd_temp, args=(hdd,)))
        pool.close()
        pool.join()
        hddict = {}
        for res in results:
            val = res.get()
            if val:
                hddict[val[0]] = val[1]
        return hddict

    def all_hdds_temp_dict(self):
        drives = []
        if psutil.WINDOWS:
            for part in psutil.disk_partitions(all=False):
                if 'cdrom' in part.opts or part.fstype == '':
                    # skip cd-rom drives
                    continue
                drives.append(part.mountpoint)
        else:
            reg = []
            if psutil.FREEBSD:
                reg.append("ad[0-9]+")
                reg.append("da[0-9]+")
                # reg.append("pass[0-9]+")
                reg.append("ada[0-9]+")
                reg.append("ciss[0-9]")
            elif psutil.LINUX:
                reg.append("sd[a-z]")
                reg.append("nst.*")
                reg.append("sg.*")
                reg.append("tw[eal][0-9]")
                reg.append("sg[0-9].*")
            combined = "(" + ")|(".join(reg) + ")"
            for dev in os.scandir("/dev/"):
                if re.match(combined, dev.name):
                    drives.append(dev.name)
        return self.hdds_temp_dict(drives)


def log(title, value):
    if args.verbose:
        print('{}: {}'.format(title, value))


def zpool_stat():
    zp = {}
    # noinspection PyBroadException
    try:
        for line in subprocess.Popen(
                ['zpool', 'list', '-Hp'],
                stdout=subprocess.PIPE, encoding='utf8'
        ).stdout.read().split('\n'):
            line = line.split('\t')
            if len(line) > 2 and line[10] != '-':
                zp[line[0]] = {
                    'total': int(line[1]),
                    'used': int(line[2]),
                    'free': int(line[3]),
                    'percent': round(int(line[2]) * 100 / int(line[1]), 1),
                    'health': line[9],
                }
    except Exception:
        pass
    return zp


def cpu_temp():
    t = 0
    # noinspection PyBroadException
    try:
        for line in subprocess.Popen(
                ['sysctl', 'dev.cpu'],
                stdout=subprocess.PIPE, encoding='utf8'
        ).stdout.read().split('\n'):
            line = line.split()
            if len(line) > 1 and re.search(r"temperature", line[0]):
                t = max(t, float(re.sub(r"[^0-9.]+", "", line[1])))
    except Exception:
        pass
    return t


# ==================== Main Code ====================
if __name__ == '__main__':
    stat = {}

    if socket.gethostname().find('.') >= 0:
        hostname = socket.gethostname()
    else:
        hostname = socket.gethostbyaddr(socket.gethostname())[0]

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-V', '--version', action='version',
        version='Home Assistant HTTP host monitor v' + VERSION)
    parser.add_argument(
        '-v', '--verbose', action='store_true', help='turns on verbose mode')
    parser.add_argument(
        '-n', '--name', default=re.sub(r"[^a-z0-9_]", "_", hostname.lower()),
        help='device name for Home Assistant sensor: [a-z0-9_].'
             ' Default current host name: %(default)s')
    parser.add_argument(
        '-s', '--server',
        default="https://" + re.sub(r"^[^.]+", "hassio", hostname) + ":8123",
        help='HTTP server URL: http[s]://host.domain[:port]'
             ' Default: %(default)s')
    parser.add_argument(
        '-c', '--no-check-ssl', action='store_false',
        help='disable SSL certificate check')
    parser.add_argument(
        'token', metavar='TOKEN',
        help='token to access to Home Assistant API')
    args = parser.parse_args()

    # Basic stat
    stat['last_boot'] = datetime.datetime.fromtimestamp(
        psutil.boot_time()).strftime("%FT%T%z")

    # CPU stat
    # noinspection PyBroadException
    try:
        lavg = os.getloadavg()
        v = ['1m', '5m', '15m']
        for k in range(3):
            stat['cpu_load_' + v[k]] = '%.02f' % lavg[k]
    except Exception:
        pass
    stat['cpu_temperature'] = cpu_temp()
    stat['cpu_stat'] = psutil.cpu_times_percent(
        interval=1, percpu=False)._asdict()

    # Mem stat
    stat['memory_stat'] = psutil.virtual_memory()._asdict()

    # Swap stat
    stat['swap_stat'] = psutil.swap_memory()._asdict()

    # Disks stat
    disks = {}
    for part in psutil.disk_partitions(all=False):
        if psutil.WINDOWS:
            if 'cdrom' in part.opts or part.fstype == '':
                # skip cd-rom drives
                continue
        else:
            if part.fstype in ['nullfs', 'devfs', 'fdescfs', 'tmpfs']:
                # Skip some virtual filesystems
                continue
        disks[part.mountpoint] = psutil.disk_usage(part.mountpoint)._asdict()
    stat['disks_stat'] = disks
    #
    stat['disks_temperature'] = HddTemp().all_hdds_temp_dict()
    #
    stat['pools_stat'] = zpool_stat()

    if FREENAS:
        import sys

        sys.path.append('/usr/local/www/')
        from freenasUI.middleware.client import client

        alerts = []
        for al in client.call("alert.list"):
            alerts.append('[{}] {}'.format(al['level'], al['formatted']))
        stat['alerts'] = "\n".join(alerts)

    # Send data to Home Assistant
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    base_url = args.server + "/api/services/mqtt/publish"
    #
    log('Base URL', base_url)
    log('SSL certificate check', args.no_check_ssl)
    #
    name = re.sub(r"[^a-z0-9_]", "_", args.name.lower()) + "_state"
    data = json.dumps({
        'topic': 'sensor/' + name,
        'payload': json.dumps(stat),
        'retain': True,
    })
    headers = {
        'Authorization': "Bearer " + args.token,
        'Content-Type': 'application/json',
    }
    log(name, json.dumps(stat))
    r = requests.post(base_url, data=data, verify=args.no_check_ssl,
                      headers=headers)
    if args.verbose:
        r.raise_for_status()
