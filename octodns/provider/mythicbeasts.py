#
#
#

from __future__ import absolute_import, division, print_function, \
    unicode_literals

import re

from requests import Session
from logging import getLogger

from ..record import Record
from .base import BaseProvider


def add_trailing_dot(value):
    '''
    Add trailing dots to values
    '''
    assert value, 'Missing value'
    assert value[-1] != '.', 'Value already has trailing dot'
    return value + '.'


def remove_trailing_dot(value):
    '''
    Remove trailing dots from values
    '''
    assert value, 'Missing value'
    assert value[-1] == '.', 'Value already missing trailing dot'
    return value[:-1]


class MythicBeastsProvider(BaseProvider):
    '''
    Mythic Beasts DNS API Provider

    mythicbeasts:
      class: octodns.provider.mythicbeasts.MythicBeastsProvider
        zones:
          my-zone: 'password'
    '''

    SUPPORTS_GEO = False
    SUPPORTS_DYNAMIC = False
    SUPPORTS = set(('A', 'AAAA', 'ALIAS', 'CNAME', 'MX', 'NS',
                    'SRV', 'SSHFP', 'CAA', 'TXT'))
    BASE = 'https://dnsapi.mythic-beasts.com/'

    def __init__(self, identifier, passwords, *args, **kwargs):
        self.log = getLogger('MythicBeastsProvider[{}]'.format(identifier))

        assert isinstance(passwords, dict), 'Missing passwords'

        self.log.debug(
            '__init__: id=%s, registered zones; %s',
            identifier,
            passwords.keys())
        super(MythicBeastsProvider, self).__init__(identifier, *args, **kwargs)

        self._passwords = passwords
        sess = Session()
        self._sess = sess

    def _request(self, method, path, data=None):
        self.log.debug('_request: method=%s, path=%s data=%s',
                       method, path, data)

        resp = self._sess.request(method, path, data=data)
        self.log.debug(
            '_request:   status=%d data=%s',
            resp.status_code,
            resp.text[:20])

        if resp.status_code == 401:
            raise Exception('Mythic Beasts unauthorized for domain: {}'
                            .format(data['domain']))
        resp.raise_for_status()
        return resp

    def _post(self, data=None):
        return self._request('POST', self.BASE, data=data)

    def records(self, zone):
        assert zone in self._passwords, 'Missing password for domain: {}' \
            .format(remove_trailing_dot(zone))

        return self._post({
            'domain': remove_trailing_dot(zone),
            'password': self._passwords[zone],
            'showall': 0,
            'command': 'LIST',
        })

    @staticmethod
    def _data_for_single(_type, data):
        return {
            'type': _type,
            'value': data['raw_values'][0]['value'],
            'ttl': data['raw_values'][0]['ttl']
        }

    @staticmethod
    def _data_for_multiple(_type, data):
        return {
            'type': _type,
            'values':
                [raw_values['value'] for raw_values in data['raw_values']],
            'ttl':
                max([raw_values['ttl'] for raw_values in data['raw_values']]),
        }

    @staticmethod
    def _data_for_MX(_type, data):
        ttl = max([raw_values['ttl'] for raw_values in data['raw_values']])
        values = []

        for raw_value in \
                [raw_values['value'] for raw_values in data['raw_values']]:
            match = re.match('^([0-9]+)\\s+(\\S+)$', raw_value, re.IGNORECASE)

            assert match is not None, 'Unable to parse MX data'

            exchange = match.group(2)

            if not exchange.endswith('.'):
                exchange = '{}.{}'.format(exchange, data['zone'])

            values.append({
                'preference': match.group(1),
                'exchange': exchange,
            })

        return {
            'type': _type,
            'values': values,
            'ttl': ttl,
        }

    @staticmethod
    def _data_for_CNAME(_type, data):
        ttl = data['raw_values'][0]['ttl']
        value = data['raw_values'][0]['value']
        if not value.endswith('.'):
            value = '{}.{}'.format(value, data['zone'])

        return MythicBeastsProvider._data_for_single(
            _type,
            {'raw_values': [
                {'value': value, 'ttl': ttl}
            ]})

    @staticmethod
    def _data_for_ANAME(_type, data):
        ttl = data['raw_values'][0]['ttl']
        value = data['raw_values'][0]['value']
        return MythicBeastsProvider._data_for_single(
            'ALIAS',
            {'raw_values': [
                {'value': value, 'ttl': ttl}
            ]})

    @staticmethod
    def _data_for_SRV(_type, data):
        ttl = max([raw_values['ttl'] for raw_values in data['raw_values']])
        values = []

        for raw_value in \
                [raw_values['value'] for raw_values in data['raw_values']]:

            match = re.match(
                '^([0-9]+)\\s+([0-9]+)\\s+([0-9]+)\\s+(\\S+)$',
                raw_value,
                re.IGNORECASE)

            assert match is not None, 'Unable to parse SRV data'

            target = match.group(4)
            if not target.endswith('.'):
                target = '{}.{}'.format(target, data['zone'])

            values.append({
                'priority': match.group(1),
                'weight': match.group(2),
                'port': match.group(3),
                'target': target,
            })

        return {
            'type': _type,
            'values': values,
            'ttl': ttl,
        }

    @staticmethod
    def _data_for_SSHFP(_type, data):
        ttl = max([raw_values['ttl'] for raw_values in data['raw_values']])
        values = []

        for raw_value in \
                [raw_values['value'] for raw_values in data['raw_values']]:
            match = re.match(
                '^([0-9]+)\\s+([0-9]+)\\s+(\\S+)$',
                raw_value,
                re.IGNORECASE)

            assert match is not None, 'Unable to parse SSHFP data'

            values.append({
                'algorithm': match.group(1),
                'fingerprint_type': match.group(2),
                'fingerprint': match.group(3),
            })

        return {
            'type': _type,
            'values': values,
            'ttl': ttl,
        }

    @staticmethod
    def _data_for_CAA(_type, data):
        ttl = data['raw_values'][0]['ttl']
        raw_value = data['raw_values'][0]['value']

        match = re.match(
            '^([0-9]+)\\s+(issue|issuewild|iodef)\\s+(\\S+)$',
            raw_value,
            re.IGNORECASE)

        assert match is not None, 'Unable to parse CAA data'

        value = {
            'flags': match.group(1),
            'tag': match.group(2),
            'value': match.group(3),
        }

        return MythicBeastsProvider._data_for_single(
            'CAA',
            {'raw_values': [{'value': value, 'ttl': ttl}]})

    _data_for_NS = _data_for_multiple
    _data_for_TXT = _data_for_multiple
    _data_for_A = _data_for_multiple
    _data_for_AAAA = _data_for_multiple

    def populate(self, zone, target=False, lenient=False):
        self.log.debug('populate: name=%s, target=%s, lenient=%s', zone.name,
                       target, lenient)

        resp = self.records(zone.name)

        before = len(zone.records)
        exists = False
        data = dict()

        exists = True
        for line in resp.content.splitlines():
            match = re.match(
                '^(\\S+)\\s+(\\d+)\\s+(\\S+)\\s+(.*)$',
                line,
                re.IGNORECASE)

            if match is None:
                self.log.debug('failed to match line: %s', line)
                continue

            if match.group(1) == '@':
                _name = ''
            else:
                _name = match.group(1)

            _type = match.group(3)
            _ttl = int(match.group(2))
            _value = match.group(4).strip()

            if _type == 'TXT':
                _value = _value.replace(';', '\\;')

            if hasattr(self, '_data_for_{}'.format(_type)):

                if _type not in data:
                    data[_type] = dict()

                if _name not in data[_type]:
                    data[_type][_name] = {
                        'raw_values': [{'value': _value, 'ttl': _ttl}],
                        'name': _name,
                        'zone': zone.name,
                    }

                else:
                    data[_type][_name].get('raw_values').append(
                        {'value': _value, 'ttl': _ttl}
                    )
            else:
                self.log.debug('skipping %s as not supported', _type)

        for _type in data:
            for _name in data[_type]:
                data_for = getattr(self, '_data_for_{}'.format(_type))

                record = Record.new(
                    zone,
                    _name,
                    data_for(_type, data[_type][_name]),
                    source=self
                )
                zone.add_record(record, lenient=lenient)

        self.log.debug('populate:   found %s records, exists=%s',
                       len(zone.records) - before, exists)

        return exists

    def _compile_commands(self, action, change):
        commands = []

        record = None

        if action == 'ADD':
            record = change.new
        else:
            record = change.existing

        hostname = remove_trailing_dot(record.fqdn)
        ttl = record.ttl
        _type = record._type

        if _type == 'ALIAS':
            _type = 'ANAME'

        if hasattr(record, 'values'):
            values = record.values
        else:
            values = [record.value]

        base = '{} {} {} {}'.format(action, hostname, ttl, _type)

        if re.match('[A]{1,4}', _type) is not None:
            for value in values:
                commands.append('{} {}'.format(base, value))

        elif _type == 'SSHFP':
            data = values[0].data
            commands.append('{} {} {} {}'.format(
                base,
                data['algorithm'],
                data['fingerprint_type'],
                data['fingerprint']
            ))

        elif _type == 'SRV':
            for value in values:
                data = value.data
                commands.append('{} {} {} {} {}'.format(
                    base,
                    data['priority'],
                    data['weight'],
                    data['port'],
                    data['target']))

        elif _type == 'MX':
            for value in values:
                data = value.data
                commands.append('{} {} {}'.format(
                    base,
                    data['preference'],
                    data['exchange']))

        else:
            if hasattr(self, '_data_for_{}'.format(_type)):
                commands.append('{} {}'.format(
                    base, values[0]))
            else:
                self.log.debug('skipping %s as not supported', _type)

        return commands

    def _apply_Create(self, change):
        zone = change.new.zone
        commands = self._compile_commands('ADD', change)

        for command in commands:
            self._post({
                'domain': remove_trailing_dot(zone.name),
                'origin': '.',
                'password': self._passwords[zone.name],
                'command': command,
            })
        return True

    def _apply_Update(self, change):
        self._apply_Delete(change)
        self._apply_Create(change)

    def _apply_Delete(self, change):
        zone = change.existing.zone
        commands = self._compile_commands('DELETE', change)

        for command in commands:
            self._post({
                'domain': remove_trailing_dot(zone.name),
                'origin': '.',
                'password': self._passwords[zone.name],
                'command': command,
            })
        return True

    def _apply(self, plan):
        desired = plan.desired
        changes = plan.changes
        self.log.debug('_apply: zone=%s, len(changes)=%d', desired.name,
                       len(changes))

        for change in changes:
            class_name = change.__class__.__name__
            getattr(self, '_apply_{}'.format(class_name))(change)
