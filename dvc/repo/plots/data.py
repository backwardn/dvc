import csv
import io
import json
import os
from collections import OrderedDict
from copy import copy

import yaml
from funcy import first
from yaml import SafeLoader

from dvc.exceptions import DvcException


class PlotMetricTypeError(DvcException):
    def __init__(self, file):
        super().__init__(
            "'{}' - file type error\n"
            "Only JSON, YAML, CSV and TSV formats are supported.".format(file)
        )


class PlotDataStructureError(DvcException):
    def __init__(self):
        super().__init__(
            "Plot data extraction failed. Please see "
            "https://man.dvc.org/plot for supported data formats."
        )


class NoMetricInHistoryError(DvcException):
    def __init__(self, path):
        super().__init__(f"Could not find '{path}'.")


def plot_data(filename, revision, content):
    _, extension = os.path.splitext(filename.lower())
    if extension == ".json":
        return JSONPlotData(filename, revision, content)
    elif extension == ".csv":
        return CSVPlotData(filename, revision, content)
    elif extension == ".tsv":
        return CSVPlotData(filename, revision, content, delimiter="\t")
    elif extension == ".yaml":
        return YAMLPlotData(filename, revision, content)
    raise PlotMetricTypeError(filename)


def _filter_fields(data_points, filename, revision, fields=None, **kwargs):
    if not fields:
        return data_points
    assert isinstance(fields, set)

    new_data = []
    for data_point in data_points:
        new_dp = copy(data_point)

        keys = set(data_point.keys())
        if keys & fields != fields:
            raise DvcException(
                "Could not find fields: '{}' for '{}' at '{}'.".format(
                    ", ".join(fields), filename, revision
                )
            )

        to_del = keys - fields
        for key in to_del:
            del new_dp[key]
        new_data.append(new_dp)
    return new_data


def _apply_path(data, path=None, **kwargs):
    if not path or not isinstance(data, dict):
        return data

    import jsonpath_ng

    found = jsonpath_ng.parse(path).find(data)
    first_datum = first(found)
    if (
        len(found) == 1
        and isinstance(first_datum.value, list)
        and isinstance(first(first_datum.value), dict)
    ):
        data_points = first_datum.value
    elif len(first_datum.path.fields) == 1:
        field_name = first(first_datum.path.fields)
        data_points = [{field_name: datum.value} for datum in found]
    else:
        raise PlotDataStructureError()

    if not isinstance(data_points, list) or not (
        isinstance(first(data_points), dict)
    ):
        raise PlotDataStructureError()

    return data_points


def _lists(dictionary):
    for _, value in dictionary.items():
        if isinstance(value, dict):
            yield from (_lists(value))
        elif isinstance(value, list):
            yield value


def _find_data(data, fields=None, **kwargs):
    if not isinstance(data, dict):
        return data

    if not fields:
        # just look for first list of dicts
        fields = set()

    for l in _lists(data):
        if all(isinstance(dp, dict) for dp in l):
            if set(first(l).keys()) & fields == fields:
                return l
    raise PlotDataStructureError()


def _append_index(data_points, append_index=False, **kwargs):
    if not append_index:
        return data_points

    if PlotData.INDEX_FIELD in first(data_points).keys():
        raise DvcException(
            "Cannot append index. Field of same name ('{}') found in data. "
            "Use `-x` to specify x axis field.".format(PlotData.INDEX_FIELD)
        )

    for index, data_point in enumerate(data_points):
        data_point[PlotData.INDEX_FIELD] = index
    return data_points


def _append_revision(data_points, revision, **kwargs):
    for data_point in data_points:
        data_point[PlotData.REVISION_FIELD] = revision
    return data_points


class PlotData:
    REVISION_FIELD = "rev"
    INDEX_FIELD = "index"

    def __init__(self, filename, revision, content, **kwargs):
        self.filename = filename
        self.revision = revision
        self.content = content

    def raw(self, **kwargs):
        raise NotImplementedError

    def _processors(self):
        return [_filter_fields, _append_index, _append_revision]

    def to_datapoints(self, **kwargs):
        data = self.raw(**kwargs)

        for data_proc in self._processors():
            data = data_proc(
                data, filename=self.filename, revision=self.revision, **kwargs
            )
        return data


class JSONPlotData(PlotData):
    def raw(self, **kwargs):
        return json.loads(self.content, object_pairs_hook=OrderedDict)

    def _processors(self):
        parent_processors = super()._processors()
        return [_apply_path, _find_data] + parent_processors


class CSVPlotData(PlotData):
    def __init__(self, filename, revision, content, delimiter=","):
        super().__init__(filename, revision, content)
        self.delimiter = delimiter

    def raw(self, header=True, **kwargs):
        first_row = first(csv.reader(io.StringIO(self.content)))

        if header:
            reader = csv.DictReader(
                io.StringIO(self.content), delimiter=self.delimiter,
            )
        else:
            reader = csv.DictReader(
                io.StringIO(self.content),
                delimiter=self.delimiter,
                fieldnames=[str(i) for i in range(len(first_row))],
            )

        fieldnames = reader.fieldnames
        data = list(reader)

        return [
            OrderedDict([(field, data_point[field]) for field in fieldnames])
            for data_point in data
        ]


class YAMLPlotData(PlotData):
    def raw(self, **kwargs):
        class OrderedLoader(SafeLoader):
            pass

        def construct_mapping(loader, node):
            loader.flatten_mapping(node)
            return OrderedDict(loader.construct_pairs(node))

        OrderedLoader.add_constructor(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping
        )

        return yaml.load(self.content, OrderedLoader)

    def _processors(self):
        parent_processors = super()._processors()
        return [_find_data] + parent_processors
