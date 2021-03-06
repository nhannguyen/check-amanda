#!/usr/bin/env python

from subprocess import Popen, PIPE
from os import path, makedirs
from shutil import rmtree
from random import choice
from datetime import datetime, timedelta
import json
import re


AMRECOVER = '/usr/sbin/amrecover'


def enter_line(stream, line):
    stream.write(line + '\n')


def read_all(in_stream, out_stream):

    # Add some junk input to get a delimiter
    INVALID_DIR = 'intentionally-invalid'
    INVALID_RES = 'Invalid directory - %s' % INVALID_DIR
    enter_line(in_stream, 'cd %s' % INVALID_DIR)

    lines = []
    while True:
        line = str(out_stream.readline().strip())
        if line == INVALID_RES:
            return lines
        lines.append(line)


def get_file_list(config, hostname, disk):

    # To match 2013-10-31-00-00-02
    pattern = re.compile('\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}')

    now = datetime.today()
    # Plus one in case the backup for today hasn't run
    delta = {
        'daily': 5,
        'weekly': 35,
        'monthly': 150,
    }[config] + 1
    oldest = now - timedelta(days=delta)

    p = Popen([AMRECOVER, config], stdin=PIPE, stdout=PIPE)
    stdin = p.stdin
    stdout = p.stdout

    enter_line(stdin, 'sethost %s' % hostname)
    enter_line(stdin, 'setdisk %s' % disk)
    read_all(stdin, stdout)

    current_path = '%s/' % disk
    tries = 0

    # TODO: What if there are a lot of empty dirs?
    while current_path.endswith('/') and tries < 1000:

        enter_line(stdin, 'cd %s' % current_path)
        enter_line(stdin, 'ls')
        lines = read_all(stdin, stdout)

        # Ignore lines not containing amrecover ls output
        lines = [line for line in lines if pattern.match(line)]
        paths = []

        for line in lines:

            date_str, the_path = line.split(None, 1)
            # date_str is like '2013-10-21-07-49-40'
            the_date = datetime.strptime(date_str, '%Y-%m-%d-%H-%M-%S')
            assert oldest <= the_date, '%s was backed up at %s. It is older than %s.' % (current_path + the_path, the_date, oldest)

            if the_path != '.':
                # Ignore current directory
                paths.append(current_path + the_path)

        # If paths is empty, that means the directory is empty. Retry another path
        if paths:
            current_path = choice(paths)
        else:
            tries += 1
            current_path = '%s/' % disk

    assert current_path
    return current_path


def test_extraction(config, hostname, disk, target):

    prefix = '/tmp/check-amanda'
    try:
        makedirs(prefix)
    except OSError:
        print 'Directory %s already exists.' % prefix

    output_path = path.join(prefix, target)

    p = Popen([AMRECOVER, config], stdin=PIPE, stdout=PIPE)
    stdin = p.stdin

    enter_line(stdin, 'lcd %s' % prefix)
    enter_line(stdin, 'sethost %s' % hostname)
    enter_line(stdin, 'setdisk %s' % disk)
    enter_line(stdin, 'add %s' % target)
    enter_line(stdin, 'extract')
    enter_line(stdin, 'Y')
    enter_line(stdin, 'Y')
    enter_line(stdin, 'exit')

    output, error = p.communicate()
    assert error is None
    assert p.returncode == 0

    p = Popen(['file', output_path], stdin=PIPE, stdout=PIPE)
    output, error = p.communicate()
    print output.strip()
    assert error is None
    assert p.returncode == 0

    if not path.islink(output_path):
        size = path.getsize(output_path)
        assert size > 0
        print 'File size is %s.' % size

    rmtree(prefix)


def main():

    dna = json.load(open('/etc/chef/node.json'))
    locations = dna['amanda']['backup_locations']

    hosts = [host['hostname'] for host in locations]
    hostname = choice(hosts)

    disks = [host['locations'] for host in locations if host['hostname'] == hostname][0]
    disk = choice(disks)

    config = choice(('daily', 'weekly', 'monthly'))

    #config = ''
    #hostname = ''
    #disk = ''
    print 'Checking %s backup of %s:%s ...' % (config, hostname, disk)

    random_file = get_file_list(config, hostname, disk)

    print 'Trying to extract %s ...' % random_file
    test_extraction(config, hostname, disk, random_file[len(disk) + 1:])

    print 'Everything looks OK.'


if __name__ == '__main__':
    main()
