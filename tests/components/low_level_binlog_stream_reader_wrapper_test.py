# -*- coding: utf-8 -*-
import mock
import pytest
import time

from pymysqlreplication.constants.BINLOG import WRITE_ROWS_EVENT_V2
from pymysqlreplication.event import GtidEvent
from pymysqlreplication.event import QueryEvent
from pymysqlreplication.row_event import WriteRowsEvent

from data_pipeline.message import RefreshMessage
from replication_handler import config
from replication_handler.components.low_level_binlog_stream_reader_wrapper import LowLevelBinlogStreamReaderWrapper
from replication_handler.util.position import GtidPosition
from replication_handler.util.position import LogPosition
from testing.events import RowsEvent


class TestLowLevelBinlogStreamReaderWrapper(object):

    @pytest.yield_fixture
    def patch_config_db(self, test_schema):
        with mock.patch.object(
            config.DatabaseConfig,
            "entries",
            new_callable=mock.PropertyMock
        ) as mock_entries:
            yield mock_entries

    @pytest.yield_fixture
    def patch_stream(self):
        with mock.patch(
            'replication_handler.components.low_level_binlog_stream_reader_wrapper.BinLogStreamReader',
        ) as mock_stream:
            yield mock_stream

    def test_schema_event(self, patch_stream):
        gtid_event = mock.Mock(spec=GtidEvent)
        schema_event = mock.Mock(spec=QueryEvent)
        patch_stream.return_value.fetchone.side_effect = [
            gtid_event,
            schema_event
        ]
        stream = LowLevelBinlogStreamReaderWrapper(
            GtidPosition(gtid="sid:5")
        )
        assert stream.peek() == gtid_event
        assert stream.pop() == gtid_event
        assert stream.peek() == schema_event
        assert stream.pop() == schema_event

    def test_flattern_data_events(self, patch_stream):
        data_event = self._prepare_data_event('fake_table')
        gtid_event = mock.Mock(spec=GtidEvent)
        query_event = mock.Mock(spec=QueryEvent)
        patch_stream.return_value.fetchone.side_effect = [
            gtid_event,
            query_event,
            data_event,
        ]
        assert len(data_event.rows) == 3
        stream = LowLevelBinlogStreamReaderWrapper(
            LogPosition(
                log_pos=100,
                log_file="binlog.001",
            )
        )
        assert stream.peek() == gtid_event
        assert stream.pop() == gtid_event
        assert stream.pop() == query_event
        assert stream.pop().row == data_event.rows[0]
        assert stream.pop().row == data_event.rows[1]
        assert stream.pop().row == data_event.rows[2]

    def test_get_data_events_refresh(self, patch_stream):
        data_event = self._prepare_data_event(
            'fake_table_data_pipeline_refresh'
        )
        patch_stream.return_value.fetchone.side_effect = [data_event]
        assert len(data_event.rows) == 3
        stream = LowLevelBinlogStreamReaderWrapper(
            LogPosition(
                log_pos=100,
                log_file="binlog.001",
            )
        )
        assert stream.pop().table == 'fake_table'
        assert stream.pop().message_type == RefreshMessage

    def _prepare_data_event(self, table):
        data_event = mock.Mock(spec=WriteRowsEvent)
        data_event.rows = RowsEvent.make_add_rows_event().rows
        data_event.schema = 'fake_schema'
        data_event.table = table
        data_event.event_type = WRITE_ROWS_EVENT_V2
        data_event.log_pos = 100
        data_event.log_file = "binglog.001"
        data_event.timestamp = int(time.time())
        return data_event

    def test_none_events(self, patch_stream):
        query_event = mock.Mock(spec=QueryEvent)
        patch_stream.return_value.fetchone.side_effect = [
            None,
            query_event,
        ]
        stream = LowLevelBinlogStreamReaderWrapper(
            LogPosition(
                log_pos=100,
                log_file="binlog.001",
            )
        )
        assert stream.peek() == query_event
        assert stream.pop() == query_event

    @pytest.yield_fixture
    def patch_config_whitelist(self):
        with mock.patch.object(
            config.EnvConfig,
            'table_whitelist',
            new_callable=mock.PropertyMock
        ) as mock_whitelist:
            yield mock_whitelist

    def test_get_only_tables(self, patch_config_whitelist):
        patch_config_whitelist.return_value = ['tab1', 'tab2', 'tab1_data_pipeline_refresh']
        expected_only_tables = ['tab1', 'tab1_data_pipeline_refresh', 'tab2', 'tab2_data_pipeline_refresh']
        stream = LowLevelBinlogStreamReaderWrapper(
            LogPosition(
                log_pos=100,
                log_file="binlog.001",
            )
        )

        assert expected_only_tables == stream._get_only_tables()
