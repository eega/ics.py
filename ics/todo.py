#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals, absolute_import

from six.moves import map

import arrow
import copy
from datetime import timedelta, datetime

from .alarm import AlarmFactory
from .component import Component
from .utils import (
    parse_duration,
    timedelta_to_duration,
    iso_to_arrow,
    get_arrow,
    arrow_to_iso,
    uid_gen,
    unescape_string,
    escape_string,
)
from .parse import ContentLine, Container


class Todo(Component):

    """A todo list entry.

    Can have a start time and duration, or start and due time,
    or only start/due time.
    """

    _TYPE = "VTODO"
    _EXTRACTORS = []
    _OUTPUTS = []

    def __init__(self,
                 uid=None,
                 completed=None,
                 created=None,
                 description=None,
                 begin=None,
                 location=None,
                 percent=None,
                 priority=None,
                 name=None,
                 url=None,
                 due=None,
                 duration=None,
                 alarms=None):
        """Instantiates a new :class:`ics.todo.Todo`.

        Args:
            uid (string): must be unique
            completed (Arrow-compatible)
            created (Arrow-compatible)
            description (string)
            begin (Arrow-compatible)
            location (string)
            percent (int): 0-100
            priority (int): 0-9
            name (string) : rfc5545 SUMMARY property
            url (string)
            due (Arrow-compatible)
            duration (datetime.timedelta)
            alarms (:class:`ics.alarm.Alarm`)

        Raises:
            ValueError: if `duration` and `due` are specified at the same time
        """

        self._begin = None
        self._due_time = None
        self._duration = None

        self.uid = uid_gen() if not uid else uid
        self.completed = get_arrow(completed)
        self.created = get_arrow(created)
        self.description = description
        self.begin = begin
        self.location = location
        self.percent = percent
        self.priority = priority
        self.name = name
        self.url = url
        self.alarms = set()
        self._unused = Container(name='VTODO')

        if duration and due:
            raise ValueError(
                'Todo() may not specify a duration and due date\
                at the same time')
        elif duration:
            if not begin:
                raise ValueError(
                    'Todo() must specify a begin if a duration\
                    is specified')
            self.duration = duration
        elif due:
            self.due = due

        if alarms is not None:
            self.alarms.update(set(alarms))

    @property
    def begin(self):
        """Get or set the beginning of the todo.

        |  Will return an :class:`Arrow` object.
        |  May be set to anything that :func:`Arrow.get` understands.
        |  If a due time is defined (not a duration), .begin must not
            be set to a superior value.
        """
        return self._begin

    @begin.setter
    def begin(self, value):
        value = get_arrow(value)
        if value and self._due_time and value > self._due_time:
            raise ValueError('Begin must be before due time')
        self._begin = value

    @property
    def due(self):
        """Get or set the end of the todo.

        |  Will return an :class:`Arrow` object.
        |  May be set to anything that :func:`Arrow.get` understands.
        |  If set to a non null value, removes any already
            existing duration.
        |  Setting to None will have unexpected behavior if
            begin is not None.
        |  Must not be set to an inferior value than self.begin.
        """

        if self._duration:
            # if due is duration defined return the beginning + duration
            return self.begin + self._duration
        elif self._due_time:
            # if due is time defined
            return self._due_time
        else:
            return None

    @due.setter
    def due(self, value):
        value = get_arrow(value)
        if value and value < self._begin:
            raise ValueError('Due must be after begin')

        self._due_time = value

        if value:
            self._duration = None

    @property
    def duration(self):
        """Get or set the duration of the todo.

        |  Will return a timedelta object.
        |  May be set to anything that timedelta() understands.
        |  May be set with a dict ({"days":2, "hours":6}).
        |  If set to a non null value, removes any already
            existing end time.
        """
        if self._duration:
            return self._duration
        elif self.due:
            return self.due - self.begin
        else:
            # todo has neither due, nor start and duration
            return None

    @duration.setter
    def duration(self, value):
        if isinstance(value, dict):
            value = timedelta(**value)
        elif isinstance(value, timedelta):
            value = value
        elif value is not None:
            value = timedelta(value)

        self._duration = value

        if value:
            self._due_time = None

    def __urepr__(self):
        """Should not be used directly. Use self.__repr__ instead.

        Returns:
            unicode: a unicode representation (__repr__) of the todo.
        """
        name = "'{}' ".format(self.name) if self.name else ''
        if self.begin is None:
            return "<Todo '{}'>".format(self.name) if self.name else "<Todo>"
        else:
            return "<Todo {}begin:{} due:{}>".format(name, self.begin, self.due)

    def starts_within(self, other):
        if not isinstance(other, Todo):
            raise NotImplementedError(
                'Cannot compare Todo and {}'.format(type(other)))

        # This todo can only start within another todo if we have a begin and
        # the other todo has a begin and due.
        if not self.begin or not other.begin or not other.due:
            return False

        return other.begin <= self.begin <= other.due

    def due_within(self, other):
        if not isinstance(other, Todo):
            raise NotImplementedError(
                'Cannot compare Todo and {}'.format(type(other)))

        # This todo can only end within another todo if we have a due and
        # the other todo has a begin and due.
        if not self.begin or not other.begin or not other.due:
            return False

        return other.begin <= self.due <= other.due

    def intersects(self, other):
        if not isinstance(other, Todo):
            raise NotImplementedError(
                'Cannot compare Todo and {}'.format(type(other)))
        return (self.starts_within(other)
                or self.due_within(other)
                or other.starts_within(self)
                or other.due_within(self))

    __xor__ = intersects

    def __lt__(self, other):
        if isinstance(other, Todo):
            if self.due is None and other.due is None:
                if self.name is None and other.name is None:
                    return False
                elif self.name is None:
                    return True
                elif other.name is None:
                    return False
                else:
                    return self.name < other.name
            return self.due < other.due
        if isinstance(other, datetime):
            return self.due < other
        raise NotImplementedError(
            'Cannot compare Todo and {}'.format(type(other)))

    def __le__(self, other):
        if isinstance(other, Todo):
            if self.due is None and other.due is None:
                if self.name is None and other.name is None:
                    return True
                elif self.name is None:
                    return True
                elif other.name is None:
                    return False
                else:
                    return self.name <= other.name
            return self.due <= other.due
        if isinstance(other, datetime):
            return self.due <= other
        raise NotImplementedError(
            'Cannot compare Todo and {}'.format(type(other)))

    def __gt__(self, other):
        if isinstance(other, Todo):
            if self.due is None and other.due is None:
                # TODO : handle py3 case when a name is None
                return self.name > other.name
            return self.due > other.due
        if isinstance(other, datetime):
            return self.due > other
        raise NotImplementedError(
            'Cannot compare Todo and {}'.format(type(other)))

    def __ge__(self, other):
        if isinstance(other, Todo):
            if self.due is None and other.due is None:
                # TODO : handle py3 case when a name is None
                return self.name >= other.name
            return self.due >= other.due
        if isinstance(other, datetime):
            return self.due >= other
        raise NotImplementedError(
            'Cannot compare Todo and {}'.format(type(other)))

    def __eq__(self, other):
        """Two todos are considered equal if they have the same uid."""
        if isinstance(other, Todo):
            return self.uid == other.uid
        raise NotImplementedError(
            'Cannot compare Todo and {}'.format(type(other)))

    def __ne__(self, other):
        """Two todos are considered not equal if they do not have the same uid."""
        if isinstance(other, Todo):
            return self.uid != other.uid
        raise NotImplementedError(
            'Cannot compare Todo and {}'.format(type(other)))

    def time_equals(self, other):
        if not self.begin or not other.begin:
            if self.due and other.due:
                return self.due == other.due
            else:
                return False
        elif not self.due or not other.due:
            if self.begin and other.begin:
                return self.begin == other.begin
            else:
                return False
        return (self.begin == other.begin) and (self.due == other.due)

    def clone(self):
        """
        Returns:
            Todo: an exact copy of self"""
        clone = copy.copy(self)
        clone._unused = clone._unused.clone()
        clone.alarms = copy.copy(self.alarms)
        return clone

    def __hash__(self):
        """
        Returns:
            int: hash of self. Based on self.uid."""
        return int(''.join(map(lambda x: '%.3d' % ord(x), self.uid)))


# ------------------
# ----- Inputs -----
# ------------------
# TODO why does DTSTAMP map to created?
@Todo._extracts('DTSTAMP', required=True)
def dtstamp(todo, line):
    if line:
        # get the dict of vtimezones passed to the classmethod
        tz_dict = todo._classmethod_kwargs['tz']
        todo.created = iso_to_arrow(line, tz_dict)


# TODO : add option somewhere to ignore some errors
@Todo._extracts('UID', required=True)
def uid(todo, line):
    if line:
        todo.uid = line.value


@Todo._extracts('COMPLETED')
def completed(todo, line):
    if line:
        # get the dict of vtimezones passed to the classmethod
        tz_dict = todo._classmethod_kwargs['tz']
        todo.completed = iso_to_arrow(line, tz_dict)


# TODO why does DTSTAMP map to created?
# @Todo._extracts('CREATED')
# def created(todo, line):
#     if line:
#         # get the dict of vtimezones passed to the classmethod
#         tz_dict = todo._classmethod_kwargs['tz']
#         todo.created = iso_to_arrow(line, tz_dict)


@Todo._extracts('DESCRIPTION')
def description(todo, line):
    todo.description = unescape_string(line.value) if line else None


@Todo._extracts('DTSTART')
def start(todo, line):
    if line:
        # get the dict of vtimezones passed to the classmethod
        tz_dict = todo._classmethod_kwargs['tz']
        todo.begin = iso_to_arrow(line, tz_dict)


@Todo._extracts('LOCATION')
def location(todo, line):
    todo.location = unescape_string(line.value) if line else None


@Todo._extracts('PERCENT-COMPLETE')
def percent(todo, line):
    if line.value < 0 or line.value > 100:
        raise ValueError('PERCENT-COMPLETE must be [0, 100]')
    todo.percent = line.value if line else None


@Todo._extracts('PRIORITY')
def priority(todo, line):
    if line.value < 0 or line.value > 9:
        raise ValueError('PRIORITY must be [0, 9]')
    todo.priority = line.value if line else None


@Todo._extracts('SUMMARY')
def summary(todo, line):
    todo.name = unescape_string(line.value) if line else None


@Todo._extracts('URL')
def url(todo, line):
    todo.url = unescape_string(line.value) if line else None


@Todo._extracts('DUE')
def due(todo, line):
    if line:
        #TODO: DRY [1]
        if todo._duration:
            raise ValueError("A todo can't have both DUE and DURATION")
        # get the dict of vtimezones passed to the classmethod
        tz_dict = todo._classmethod_kwargs['tz']
        todo._due_time = iso_to_arrow(line, tz_dict)


@Todo._extracts('DURATION')
def duration(todo, line):
    if line:
        #TODO: DRY [1]
        if todo._due_time:  # pragma: no cover
            raise ValueError("An todo can't have both DUE and DURATION")
        todo._duration = parse_duration(line.value)


@Todo._extracts('VALARM', multiple=True)
def alarms(todo, lines):
    def alarm_factory(x):
        af = AlarmFactory.get_type_from_container(x)
        return af._from_container(x)

    todo.alarms = list(map(alarm_factory, lines))


# -------------------
# ----- Outputs -----
# -------------------
# TODO why isn't there an output for dtstamp in addition to created
# @Todo._outputs
# def o_dtstamp(todo, container):
#     if todo.created:
#         instant = todo.created
#     else:
#         instant = arrow.now()
#
#     container.append(ContentLine('DTSTAMP', value=arrow_to_iso(instant)))


@Todo._outputs
def o_uid(todo, container):
    if todo.uid:
        uid = todo.uid
    else:
        uid = uid_gen()

    container.append(ContentLine('UID', value=uid))


@Todo._outputs
def o_completed(todo, container):
    if todo.completed:
        instant = todo.completed
    else:
        instant = arrow.now()

    container.append(ContentLine('COMPLETED', value=arrow_to_iso(instant)))


# TODO why isn't there an output for dtstamp in addition to created
@Todo._outputs
def o_created(todo, container):
    if todo.created:
        instant = todo.created
    else:
        instant = arrow.now()

    # TODO this should be 'CREATED'
    container.append(ContentLine('DTSTAMP', value=arrow_to_iso(instant)))


@Todo._outputs
def o_description(todo, container):
    if todo.description:
        container.append(ContentLine('DESCRIPTION', value=escape_string(todo.description)))


@Todo._outputs
def o_start(todo, container):
    if todo.begin:
        container.append(ContentLine('DTSTART', value=arrow_to_iso(todo.begin)))


@Todo._outputs
def o_location(todo, container):
    if todo.location:
        container.append(ContentLine('LOCATION', value=escape_string(todo.location)))


@Todo._outputs
def o_percent(todo, container):
    if todo.percent:
        container.append(ContentLine('PERCENT-COMPLETE', value=todo.percent))


@Todo._outputs
def o_priority(todo, container):
    if todo.priority:
        container.append(ContentLine('PRIORITY', value=todo.priority))


@Todo._outputs
def o_summary(todo, container):
    if todo.name:
        container.append(ContentLine('SUMMARY', value=escape_string(todo.name)))


@Todo._outputs
def o_url(todo, container):
    if todo.url:
        container.append(ContentLine('URL', value=escape_string(todo.url)))


@Todo._outputs
def o_due(todo, container):
    if todo._due_time:
        container.append(ContentLine('DUE', value=arrow_to_iso(todo._due_time)))


@Todo._outputs
def o_duration(todo, container):
    # TODO : DURATION
    if todo._duration and todo.begin:
        representation = timedelta_to_duration(todo._duration)
        container.append(ContentLine('DURATION', value=representation))


@Todo._outputs
def o_alarm(todo, container):
    for alarm in todo.alarms:
        container.append(str(alarm))