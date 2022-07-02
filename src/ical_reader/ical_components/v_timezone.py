from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple, Union

from pendulum import Date, DateTime

from ical_reader.base_classes.component import Component
from ical_reader.help_classes.timespan import Timespan
from ical_reader.ical_properties.dt import DTStart, LastModified
from ical_reader.ical_properties.pass_properties import Comment, TZID, TZName, TZURL
from ical_reader.ical_properties.periods import RDate
from ical_reader.ical_properties.rrule import RRule
from ical_reader.ical_properties.tz_offset import TZOffsetFrom, TZOffsetTo
from ical_reader.ical_utils import dt_utils, property_utils


@dataclass(repr=False)
class _TimeOffsetPeriod(Component):
    # Required
    dtstart: Optional[DTStart] = None
    tzoffsetto: Optional[TZOffsetTo] = None
    tzoffsetfrom: Optional[TZOffsetFrom] = None
    # Optional, may only occur once.
    rrule: Optional[RRule] = None
    # Optional, may occur more than once.
    comment: Optional[List[Comment]] = None
    rdate: Optional[List[RDate]] = None
    tzname: Optional[List[TZName]] = None

    def timezone_aware_start(self) -> DateTime:
        dt: DateTime = dt_utils.convert_time_object_to_datetime(self.dtstart.datetime_or_date_value)
        return dt.in_timezone(tz=self.tzoffsetfrom.as_timezone_object())

    def get_time_sequence(
        self, max_datetime: Optional[DateTime] = None
    ) -> Iterator[Tuple[DateTime, "_TimeOffsetPeriod"]]:
        for rtime in property_utils.expand_event_in_range_only_return_first(
            rdate_list=self.rdate or [],
            rrule=self.rrule,
            first_event_start=self.timezone_aware_start(),
            return_range=Timespan(self.dtstart.datetime_or_date_value, max_datetime),
            make_tz_aware=self.tzoffsetfrom.as_timezone_object(),
        ):
            if not isinstance(rtime, DateTime):
                raise TypeError(f"{rtime} was expected to be a DateTime object.")
            yield rtime, self


@dataclass
class DayLight(_TimeOffsetPeriod):
    pass


@dataclass
class Standard(_TimeOffsetPeriod):
    pass


@dataclass
class VTimeZone(Component):
    """This class represents the VTIMEZONE component specified in RFC 5545 in '3.6.5. Time Zone Component'."""

    # Fully done AFAIK.. Remains to be verified though.
    # Required properties, must occur one.
    tzid: Optional[TZID] = None
    # Optional properties, may only occur once.
    last_mod: Optional[LastModified] = None
    tzurl: Optional[TZURL] = None
    # Required components, may occur multiple times.
    standardc: Optional[List[Standard]] = field(default_factory=list)
    daylightc: Optional[List[DayLight]] = field(default_factory=list)

    __storage_of_results: Dict[DateTime, List[Tuple[DateTime, _TimeOffsetPeriod]]] = field(default_factory=dict)

    def get_ordered_timezone_overview(self, max_datetime: DateTime) -> List[Tuple[DateTime, _TimeOffsetPeriod]]:
        if max_datetime in self.__storage_of_results.keys():
            return self.__storage_of_results[max_datetime]
        all_timezones: List[Tuple[Union[DateTime, Date], _TimeOffsetPeriod]] = []
        for a_standard in self.standardc:
            all_timezones.extend(a_standard.get_time_sequence(max_datetime=max_datetime))
        for a_daylight in self.daylightc:
            all_timezones.extend(a_daylight.get_time_sequence(max_datetime=max_datetime))
        sorted_list = sorted(all_timezones, key=lambda tup: tup[0])
        self.__storage_of_results[max_datetime] = sorted_list
        return sorted_list

    def convert_naive_datetime_to_aware(self, dt: DateTime) -> DateTime:
        if dt.tzinfo is not None:
            return dt

        dt_object: DateTime
        time_offset_period: _TimeOffsetPeriod
        for i, (dt_object, time_offset_period) in enumerate(self.get_ordered_timezone_overview(DateTime(2100, 1, 1))):
            if i == 0 and dt < dt_object.replace(tzinfo=None):
                return dt.in_timezone(time_offset_period.tzoffsetfrom.as_timezone_object())
            if dt > dt_object.replace(tzinfo=None):
                return dt.in_timezone(time_offset_period.tzoffsetto.as_timezone_object())
        return dt
