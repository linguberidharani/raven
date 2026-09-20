"""Unit tests for the EVTX loader.

All event XML below is SYNTHETIC test data built in this file. It is not real telemetry.
The EVTX reader (python-evtx) is replaced by small fakes, so no EVTX file is needed and
every test writes only into a temporary directory.
"""

from xml.sax.saxutils import escape

import pytest

from raven.collectors import evtx_loader
from raven.collectors.evtx_loader import EvtxLoadError, load_evtx, main, parse_event_xml
from raven.collectors.raw_jsonl import read_raw_jsonl, sha256_file
from raven.collectors.raw_schema import RAW_FIELDS, UNNAMED_KEY, validate_raw_record

NS = "http://schemas.microsoft.com/win/2004/08/events/event"


def make_event_xml(
    event_id=1,
    record_id=1,
    data=(),
    computer="SYNTHETIC-LAB-HOST",
    system_time="2020-01-01 00:00:00.123456+00:00",
    with_event_data=True,
):
    """XML shaped like the output of python-evtx (SYNTHETIC test data)."""
    parts = [
        f'<Event xmlns="{NS}"><System>',
        '<Provider Name="Synthetic-Provider" Guid="{00000000-0000-0000-0000-000000000000}"></Provider>\n',
        f'<EventID Qualifiers="">{event_id}</EventID>\n',
        f'<TimeCreated SystemTime="{system_time}"></TimeCreated>\n',
        f"<EventRecordID>{record_id}</EventRecordID>\n",
        f"<Computer>{escape(computer)}</Computer>\n",
        "</System>\n",
    ]
    if with_event_data:
        parts.append("<EventData>")
        for name, value in data:
            label = "" if name is None else f' Name="{name}"'
            parts.append(f"<Data{label}>{escape(value)}</Data>\n")
        parts.append("</EventData>\n")
    parts.append("</Event>\n")
    return "".join(parts)


PROCESS_XML = make_event_xml(
    1,
    42,
    [
        ("RuleName", "-"),
        ("UtcTime", "2020-01-01 00:00:00.123"),
        ("ProcessId", "1234"),
        ("Image", "C:\\Test\\synthetic.exe"),
        ("CommandLine", 'synthetic.exe --flag "quoted" & <x>'),
        ("Hashes", "SHA256=" + "A" * 64),
    ],
)


# ---------------------------------------------------------------- parse_event_xml


def test_parse_process_event():
    record = parse_event_xml(PROCESS_XML)
    assert list(record) == list(RAW_FIELDS)
    assert record["event_id"] == 1
    assert record["record_id"] == 42
    assert record["computer"] == "SYNTHETIC-LAB-HOST"
    assert record["time_created"] == "2020-01-01 00:00:00.123456+00:00"
    assert record["event_data"]["Image"] == "C:\\Test\\synthetic.exe"
    assert record["event_data"]["CommandLine"] == 'synthetic.exe --flag "quoted" & <x>'
    assert record["event_data"]["Hashes"] == "SHA256=" + "A" * 64
    assert record["raw_xml"] == PROCESS_XML
    assert validate_raw_record(record) == []


def test_data_order_is_kept():
    record = parse_event_xml(PROCESS_XML)
    assert list(record["event_data"]) == ["RuleName", "UtcTime", "ProcessId", "Image", "CommandLine", "Hashes"]


def test_empty_data_becomes_an_empty_string():
    record = parse_event_xml(make_event_xml(data=[("Empty", "")]))
    assert record["event_data"] == {"Empty": ""}


def test_event_without_event_data_gives_an_empty_object():
    record = parse_event_xml(make_event_xml(with_event_data=False))
    assert record["event_data"] == {}


def test_unnamed_data_is_kept_under_the_unnamed_key():
    record = parse_event_xml(make_event_xml(data=[(None, "first"), ("Named", "x"), (None, "second")]))
    assert record["event_data"] == {"Named": "x", UNNAMED_KEY: ["first", "second"]}
    assert validate_raw_record(record) == []


def test_a_repeated_data_name_is_an_error():
    with pytest.raises(EvtxLoadError, match="more than once"):
        parse_event_xml(make_event_xml(data=[("A", "1"), ("A", "2")]))


def test_invalid_xml_is_an_error():
    with pytest.raises(EvtxLoadError, match="invalid event XML"):
        parse_event_xml("<Event><oops></Event>")


@pytest.mark.parametrize(
    "broken, message",
    [
        (PROCESS_XML.replace('<EventID Qualifiers="">1</EventID>\n', ""), "System/EventID is missing"),
        (PROCESS_XML.replace('<EventID Qualifiers="">1</EventID>', '<EventID Qualifiers="">abc</EventID>'), "not an integer"),
        (PROCESS_XML.replace("<EventRecordID>42</EventRecordID>\n", ""), "System/EventRecordID is missing"),
        (PROCESS_XML.replace("<Computer>SYNTHETIC-LAB-HOST</Computer>\n", ""), "System/Computer is missing"),
        (PROCESS_XML.replace('<TimeCreated SystemTime="2020-01-01 00:00:00.123456+00:00"></TimeCreated>\n', ""), "TimeCreated"),
        (f'<Event xmlns="{NS}"></Event>', "System section is missing"),
    ],
)
def test_missing_or_bad_system_fields_are_errors(broken, message):
    with pytest.raises(EvtxLoadError, match=message):
        parse_event_xml(broken)


# ---------------------------------------------------------------- fakes for load_evtx


class FakeRecord:
    def __init__(self, xml):
        self._xml = xml

    def xml(self):
        if isinstance(self._xml, Exception):
            raise self._xml
        return self._xml


class FakeChunk:
    def __init__(self, xmls, declared=None, magic_ok=True):
        self._records = [FakeRecord(x) for x in xmls]
        self._declared = len(self._records) if declared is None else declared
        self._magic_ok = magic_ok

    def check_magic(self):
        return self._magic_ok

    def file_first_record_number(self):
        return 1

    def file_last_record_number(self):
        return self._declared

    def records(self):
        return iter(self._records)


class FakeFileHeader:
    def __init__(self, ok):
        self._ok = ok

    def check_magic(self):
        return self._ok


def install_fake_evtx(monkeypatch, chunks, header_ok=True, open_error=None):
    class FakeEvtx:
        def __init__(self, path):
            if open_error is not None:
                raise open_error
            self.path = path

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def get_file_header(self):
            return FakeFileHeader(header_ok)

        def chunks(self):
            return iter(chunks)

    monkeypatch.setattr(evtx_loader, "Evtx", FakeEvtx)


@pytest.fixture
def evtx_file(tmp_path):
    path = tmp_path / "input.evtx"
    path.write_bytes(b"placeholder: the reader is faked in these tests")
    return path


THREE_XMLS = [
    make_event_xml(1, 10, [("Image", "C:\\a.exe")]),
    make_event_xml(11, 11, [("TargetFilename", "C:\\Test\\b.txt")]),
    make_event_xml(3, 12, [("DestinationIp", "127.0.0.1")]),
]


# ---------------------------------------------------------------- load_evtx


def test_load_writes_every_record_in_file_order(monkeypatch, evtx_file, tmp_path):
    install_fake_evtx(monkeypatch, [FakeChunk(THREE_XMLS[:2]), FakeChunk(THREE_XMLS[2:])])
    output = tmp_path / "out" / "raw.jsonl"
    assert load_evtx(evtx_file, output) == 3
    records = list(read_raw_jsonl(output))
    assert [r["record_id"] for r in records] == [10, 11, 12]
    assert [r["event_id"] for r in records] == [1, 11, 3]
    assert [r["raw_xml"] for r in records] == THREE_XMLS


def test_unsupported_event_ids_are_kept(monkeypatch, evtx_file, tmp_path):
    xmls = [make_event_xml(5, 1, [("Image", "C:\\a.exe")]), make_event_xml(255, 2, [("ID", "DriverCommunication")])]
    install_fake_evtx(monkeypatch, [FakeChunk(xmls)])
    output = tmp_path / "raw.jsonl"
    assert load_evtx(evtx_file, output) == 2
    assert [r["event_id"] for r in read_raw_jsonl(output)] == [5, 255]


def test_loading_twice_gives_identical_files(monkeypatch, evtx_file, tmp_path):
    install_fake_evtx(monkeypatch, [FakeChunk(THREE_XMLS)])
    first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    load_evtx(evtx_file, first)
    load_evtx(evtx_file, second)
    assert first.read_bytes() == second.read_bytes()


def test_missing_input_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_evtx(tmp_path / "missing.evtx", tmp_path / "out.jsonl")


def test_output_must_differ_from_input(evtx_file):
    with pytest.raises(ValueError, match="must differ"):
        load_evtx(evtx_file, evtx_file)


def test_wrong_file_signature(monkeypatch, evtx_file, tmp_path):
    install_fake_evtx(monkeypatch, [FakeChunk(THREE_XMLS)], header_ok=False)
    output = tmp_path / "raw.jsonl"
    with pytest.raises(EvtxLoadError, match="not an EVTX file"):
        load_evtx(evtx_file, output)
    assert not output.exists()


def test_file_that_cannot_be_opened(monkeypatch, evtx_file, tmp_path):
    install_fake_evtx(monkeypatch, [], open_error=OSError("disk error"))
    with pytest.raises(EvtxLoadError, match="cannot open input.evtx as an EVTX file: disk error"):
        load_evtx(evtx_file, tmp_path / "raw.jsonl")


def test_file_without_records(monkeypatch, evtx_file, tmp_path):
    install_fake_evtx(monkeypatch, [FakeChunk([])])
    output = tmp_path / "raw.jsonl"
    with pytest.raises(EvtxLoadError, match="contains no records"):
        load_evtx(evtx_file, output)
    assert not output.exists()


def test_chunk_with_fewer_records_than_declared(monkeypatch, evtx_file, tmp_path):
    install_fake_evtx(monkeypatch, [FakeChunk(THREE_XMLS[:1]), FakeChunk(THREE_XMLS[1:], declared=5)])
    output = tmp_path / "raw.jsonl"
    with pytest.raises(EvtxLoadError, match=r"chunk 2 of input.evtx: 2 record\(s\) could be read, the chunk header declares 5"):
        load_evtx(evtx_file, output)
    assert not output.exists()


def test_chunk_with_an_invalid_header(monkeypatch, evtx_file, tmp_path):
    install_fake_evtx(monkeypatch, [FakeChunk(THREE_XMLS[:1]), FakeChunk(THREE_XMLS[1:], magic_ok=False)])
    with pytest.raises(EvtxLoadError, match="chunk 2 of input.evtx has an invalid header"):
        load_evtx(evtx_file, tmp_path / "raw.jsonl")


def test_a_record_that_cannot_be_rendered(monkeypatch, evtx_file, tmp_path):
    install_fake_evtx(monkeypatch, [FakeChunk([THREE_XMLS[0], RuntimeError("bad binary xml"), THREE_XMLS[2]])])
    with pytest.raises(EvtxLoadError, match="cannot read record 2 of input.evtx: bad binary xml"):
        load_evtx(evtx_file, tmp_path / "raw.jsonl")


def test_a_record_with_invalid_content_names_its_position(monkeypatch, evtx_file, tmp_path):
    broken = THREE_XMLS[1].replace("<Computer>SYNTHETIC-LAB-HOST</Computer>\n", "")
    install_fake_evtx(monkeypatch, [FakeChunk([THREE_XMLS[0], broken])])
    with pytest.raises(EvtxLoadError, match="record 2 of input.evtx: System/Computer is missing"):
        load_evtx(evtx_file, tmp_path / "raw.jsonl")


def test_a_failed_load_keeps_the_previous_output(monkeypatch, evtx_file, tmp_path):
    output = tmp_path / "raw.jsonl"
    output.write_text("previous content\n", encoding="utf-8")
    install_fake_evtx(monkeypatch, [FakeChunk(THREE_XMLS, declared=9)])
    with pytest.raises(EvtxLoadError):
        load_evtx(evtx_file, output)
    assert output.read_text(encoding="utf-8") == "previous content\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["input.evtx", "raw.jsonl"]


def test_a_real_non_evtx_file_is_rejected(evtx_file, tmp_path):
    """No fake here: the real python-evtx reader must not turn a non-EVTX file into an empty success."""
    evtx_file.write_bytes(bytes(range(256)) * 40)
    output = tmp_path / "raw.jsonl"
    with pytest.raises(EvtxLoadError):
        load_evtx(evtx_file, output)
    assert not output.exists()


# ---------------------------------------------------------------- command line


def test_main_success(monkeypatch, evtx_file, tmp_path, capsys):
    install_fake_evtx(monkeypatch, [FakeChunk(THREE_XMLS)])
    output = tmp_path / "raw.jsonl"
    assert main([str(evtx_file), str(output)]) == 0
    printed = capsys.readouterr().out
    assert "records written: 3" in printed
    assert sha256_file(output) in printed


def test_main_failure(monkeypatch, evtx_file, tmp_path, capsys):
    install_fake_evtx(monkeypatch, [FakeChunk(THREE_XMLS, declared=9)])
    assert main([str(evtx_file), str(tmp_path / "raw.jsonl")]) == 1
    assert "ERROR" in capsys.readouterr().err
    assert main([str(tmp_path / "missing.evtx"), str(tmp_path / "raw.jsonl")]) == 1
