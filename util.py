#!/usr/bin/python3

import argparse
import pathlib
import json
import requests
import re
import functools
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional
from ietfdata import datatracker, rfcindex

# supported document extensions
valid_extns = [".xml", ".txt"]


@dataclass
class RootWorkingDir:
    root    : pathlib.Path
    doctypes: List[str] = field(default_factory=lambda: ["rfc", "draft"])

    def __post_init__(self) -> None:
        self.root = self.root.resolve()

        if not self.root.exists():
            raise AssertionError(f"Error writing to directory {self.root}")

        assert self.root.exists(), f"Root dir <{self.root}> does not exist."
        assert self.root.is_dir(), f"<{self.root} is not a directory"
        # TODO : Also add check to see if directory is writable
        self.sync = self.root / ".sync"
        self.rfc = self.root / "rfc"
        self.draft = self.root / "draft"
        self.output = self.root / "output"
        self.draft_out = self.root / "output" / "draft"
        self.rfc_out = self.root / "output" / "rfc"

        self.draft.mkdir(exist_ok=True)
        self.rfc.mkdir(exist_ok=True)
        self.output.mkdir(exist_ok=True)
        self.draft_out.mkdir(exist_ok=True)
        self.rfc_out.mkdir(exist_ok=True)

    def __enter__(self):
        self.sync_time = datetime.utcnow()
        self._meta = None
        if self.sync.exists():
            with open(self.sync, 'r') as fp:
                self._meta = json.load(fp)
        return self

    def __exit__(self, ex_type, ex, ex_tb):
        #print(f"ex-type --> {ex_type}, type --> {type(ex_type)}")
        #print(f"ex --> {ex}, type --> {type(ex)}")
        #print(f"ex-tb  --> {ex_tb}, type --> {type(ex_tb)}")
        pass

    def prev_sync_time(self,
                       doc_type: str,
                       override: Optional[str] = None) -> datetime:
        if override:
            return datetime.strptime(override, "%Y-%m-%d %H:%M:%S")

        if self._meta == None:
            return datetime(year=1970,
                            month=1,
                            day=1,
                            hour=0,
                            minute=0,
                            second=0)

        if doc_type in self._meta:
            return datetime.strptime(self._meta[doc_type], "%Y-%m-%d %H:%M:%S")
        else:
            return datetime(year=1970,
                            month=1,
                            day=1,
                            hour=0,
                            minute=0,
                            second=0)

    def _new_sync(self) -> Dict[str, str]:
        start = datetime(year=1970, month=1, day=1, hour=0, minute=0, second=0)
        dt = start.strftime("%Y-%m-%d %H:%M:%S")
        return {"rfc": dt, "draft": dt}

    def update_sync_time(self, doc_type: str) -> None:
        if self._meta == None:
            self._meta = self._new_sync()

        if doc_type in self._meta or doc_type in self.doctypes:
            self._meta[doc_type] = self.sync_time.strftime("%Y-%m-%d %H:%M:%S")

        with open(self.sync, 'w') as fp:
            json.dump(self._meta, fp)


@dataclass(frozen=True)
class DownloadOptions:
    force: bool = False  # if set to True, override files in cache


@dataclass
class IETF_URI:
    name : str
    extn : str
    rev  : str = field(default=None)
    dtype: str = field(default=None)
    url  : str = field(default=None)

    def _document_name(self):
        return f"{self.name}-{self.rev}" if self.rev else f"{self.name}"

    def gen_filepath(self, root: pathlib.Path) -> pathlib.Path:
        if self.rev:
            self.infile = root / self.name / self.rev / f"{self._document_name()}{self.extn}"
        else:
            self.infile = root / self.name / f"{self._document_name()}{self.extn}"
        return self.infile

    def set_filepath(self, filename: pathlib.Path) -> pathlib.Path:
        self.infile = filename
        return filename

    def get_filepath(self) -> Optional[pathlib.Path]:
        return getattr(self, "infile", None)


@dataclass
class DownloadClient:
    fs: RootWorkingDir
    dlopts: Optional[DownloadOptions] = field(default_factory=DownloadOptions)

    def __enter__(self) -> None:
        self.session = requests.Session()
        return self

    def __exit__(self, ex_type, ex, ex_tb) -> None:
        self.session.close()
        self.session = None

    def _write_file(self, file_path: pathlib.Path, data: str) -> bool:
        written = False
        file_path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)

        with open(str(file_path), "w") as fp:
            fp.write(data)
            written = True
        return written

    def _resolve_file_root(self, doc: IETF_URI) -> pathlib.Path:
        return self.fs.draft if doc.dtype == "draft" else self.fs.rfc

    def download_files(self, urls: List[IETF_URI]) -> List[IETF_URI]:
        doclist = list()
        for doc in urls:
            infile = doc.gen_filepath(self._resolve_file_root(doc))

            if not self.dlopts.force:
                if infile.exists():
                    continue

            dl = self.session.get(doc.url, verify=True, stream=False)
            if dl.status_code != 200:
                print(f"Error : {dl.status_code} while downloading {doc.url(self.base_uri)}")
                continue

            if self._write_file(infile, dl.text):
                doclist.append(doc)
                print(f"Stored input file {infile}")
            else:
                print("Error storing input file {infile}")
        return doclist


def fetch_new_drafts(since: datetime) -> List[IETF_URI]:
    trk = datatracker.DataTracker()
    draft_itr = trk.documents(
        since=since.strftime("%Y-%m-%dT%H:%M:%S"),
        doctype=trk.document_type(
            datatracker.DocumentTypeURI("/api/v1/name/doctypename/draft/")))

    urls = []
    for draft in draft_itr:
        for uri in draft.submissions:
            submission = trk.submission(uri)
            if not submission:
                break

            urls += [ IETF_URI(submission.name,
                               _extn,
                               rev=submission.rev,
                               dtype="draft",
                               url=_url) 
                      for _extn, _url in submission.urls()
                          if _extn in valid_extns ]
    return urls


class PositionalArg:
    def __init__(self, arg):
        self.arg = arg

    def _match_name(self, fname: str) -> Tuple[str, str, str, str]:
        extn_str = functools.reduce(lambda x, y: x + f'|{y}', valid_extns)
        # document with revision
        regex_rev = re.compile(f"(?P<dtype>draft-|Draft-|DRAFT-)"
                               f"(?P<name>[a-zA-Z0-9_\-]+)"
                               f"-(?P<rev>[0-9]+)"
                               f"(?P<extn>{extn_str})?$")
        # document without revision
        regex_std = re.compile(f"(?P<dtype>draft-|Draft-|DRAFT-|rfc|RFC|Rfc)?"
                               f"(?P<name>[a-zA-Z0-9_\-]+)"
                               f"(?P<extn>{extn_str})?$")

        _match = regex_rev.match(fname)
        if _match != None:
            return ("draft", 
                    _match.group('dtype') + _match.group("name"),
                    _match.group("rev"), 
                    _match.group("extn"))

        _match = regex_std.match(fname)
        if _match != None:
            dtype = None
            if _match.group('dtype'):
                if _match.group('dtype').lower() == "draft-":
                    dtype = "draft"
                elif _match.group('dtype').lower() == "rfc":
                    dtype = "rfc"
            return (dtype, 
                    _match.group("dtype") + _match.group("name"), 
                    None,
                    _match.group("extn"))
        return None

    def resolve_argtype(self):
        ret_type, urls = "", []
        fp = pathlib.Path(self.arg).resolve()

        if fp.exists() and fp.is_file():
            # Actual file passed in
            assert fp.suffix in valid_extns, f"File {fp} does not have a valid extension type -- {valid_extns}"
            ret_type = "local"
            rname = self._match_name(fp.name)
            if rname:
                dtype, name, rev, extn = rname
                ietf_uri = IETF_URI(name, extn, rev=rev, dtype=dtype)
            else:
                ietf_uri = IETF_URI(fp.stem, fp.suffix, rev=None, dtype=None)
            ietf_uri.set_filepath(fp)
            urls.append(ietf_uri)
        else:
            ret_type = "remote"
            rname = self._match_name(fp.name)
            assert rname != None, f"remote-uri {self.arg} misformed. Cannot resolve with datatracker"
            dtype, name, rev, extn = rname
            urls += self._query_datatracker(dtype, name, rev, extn)
        return (ret_type, urls)

    def _query_datatracker(self, doctype, name, rev, extn):
        assert doctype in ['draft', 'rfc'], f"Could not resolve document type {dtype}.Only draft,rfc supported."
        urls = []

        if doctype == 'draft':
            trk = datatracker.DataTracker()
            draft = trk.document_from_draft(name)
            assert draft != None, f"Could not resolve remote draft -- name = {name} , rev = {rev}, extension = {extn}"
            for uri in draft.submissions:
                submission = trk.submission(uri)
                if not submission:
                    continue

                if rev and rev != submission.rev:
                    continue

                if extn == None:
                    urls += [ IETF_URI(submission.name,
                                       _ext,
                                       rev=submission.rev,
                                       dtype="draft",
                                       url=_url) 
                              for _ext, _url in submission.urls()
                                  if _ext in valid_extns
                            ]
                elif extn in valid_extns:
                    for _sub_extn, _sub_url in submission.urls():
                        if _sub_extn != extn:
                            continue
                        urls.append( IETF_URI(submission.name,
                                              extn,
                                              rev=submission.rev,
                                              dtype="draft",
                                              url=_sub_url))

        elif doctype == 'rfc':
            trk = rfcindex.RFCIndex()
            rfc = trk.rfc(name.upper())
            assert rfc != None, f"Invalid rfc -- {name}"

            extn_rfc_convert = lambda _ext: "ASCII" if _ext == ".txt" else _ext[1:].upper()
            rfc_extn_convert = lambda _ext: ".txt" if _ext == "ascii" else f".{_ext.lower()}"

            rfc_extensions = [ rfc_extn_convert(_ext.lower()) for _ext in rfc.formats ]
            dt_extns = [_ext for _ext in rfc_extensions if _ext in valid_extns]

            if extn:
                assert extn in dt_extns, f"File format extn of {name}{extn} not amongst {dt_extns}"
                urls.append( IETF_URI(name,
                                      extn,
                                      rev=None,
                                      dtype="rfc",
                                      url=rfc.content_url(extn_rfc_convert(extn))))
            else:
                urls += [ IETF_URI(name,
                                   _extn,
                                   rev=None,
                                   dtype="rfc",
                                   url=rfc.content_url(extn_rfc_convert(_extn)))
                          for _extn in dt_extns 
                        ]
        return urls


def parse_cmdline():
    epoch = '1970-01-01 00:00:00'
    ap = argparse.ArgumentParser(description=f"Parse ietf drafts and rfcs "
                                 f"and autogenerate protocol parsers")

    ap.add_argument(
        "-nd",
        "--newdraft",
        metavar="from",
        nargs='?',
        const=epoch,
        help=f"Get all new drafts from ietf data tracker. "
        f"If from date is provided, pick up drafts from given date "
        f"(fmt 'yyyy-mm-dd hh:mm:ss'). ")
    ap.add_argument(
        "-nr",
        "--newrfc",
        metavar="from",
        nargs='?',
        const=epoch,
        help=f"Get all new rfcs from ietf data tracker. "
        f"If from date is provided, pick up drafts from given date "
        f"(fmt 'yyyy-mm-dd hh:mm:ss'). ")
    ap.add_argument("-d",
                    "--dir",
                    metavar="dir",
                    nargs=1,
                    default=str(pathlib.Path().cwd() / "ietf_data_cache"),
                    help=f"Root directory for all files")
    ap.add_argument("uri",
                    metavar='uri',
                    nargs="*",
                    help="provide draft[-rev][.extn]/ rfc[.extn]/ file-name ")

    _obj = ap.parse_args()
    infiles = []

    root_dir = pathlib.Path(_obj.dir[0])

    if _obj.newdraft:
        fromdate = datetime.strptime(_obj.newdraft, "%Y-%m-%d %H:%M:%S")
        with RootWorkingDir(root=root_dir) as rwd, DownloadClient(fs=rwd) as dlclient:
            # preprocessing before actual parser call
            drafts = fetch_new_drafts( rwd.prev_sync_time( 'draft', None if _obj.newdraft == epoch else _obj.newdraft))
            for u in drafts:
                print(f"Draft --> {u}")
            dlclient.download_files(drafts)

            infiles += drafts

            # post-processing starts here
            rwd.update_sync_time("draft")
    elif _obj.newrfc:
        print(f"We got nr = {_obj.newrfc}")
        # preprocessing before actual parser call

        # to-do call parser

        # post-processing starts here
        rwd.update_sync_time("rfc")
    elif _obj.uri:
        remote, local = [], []
        for arg in [PositionalArg(uri) for uri in _obj.uri]:
            #with RootWorkingDir(root= root_dir) as rwd :
            #with DownloadClient(fs=rwd) as dlclient :
            uri_type, urls = arg.resolve_argtype()
            if uri_type == 'remote':
                remote += urls
            elif uri_type == 'local':
                local += urls
        else:
            infiles += local

        #for i, r in enumerate(remote) :
        #    print(f"remote [{i}] ->  {r}")
        #print(f"-----------------------------------")
        #for i, r in enumerate(local) :
        #    print(f"local [{i}] ->  {r} --> file = {r.get_filepath()}")
        #print(f"-----------------------------------")

        with RootWorkingDir(root=root_dir) as rwd, DownloadClient(fs=rwd) as dlclient:
            dlclient.download_files(remote)
            infiles += remote

        for idx, inf in enumerate(infiles):
            print(f"File [{idx}]  --> {inf.get_filepath()}")


if __name__ == '__main__':
    parse_cmdline()
