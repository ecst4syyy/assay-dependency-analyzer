import json
from pathlib import Path

import pytest

from app.services.parser import (
    MAX_PACKAGES,
    PackageRef,
    ParseError,
    import_to_distribution,
    is_valid_name,
    normalise_name,
    parse_package_json,
    parse_requirements,
    parse_single,
    parse_text,
    parse_upload,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def names(result):
    return [(p.ecosystem, p.name) for p in result.packages]


def pypi(*items):
    return [("pypi", n) for n in items]


def npm(*items):
    return [("npm", n) for n in items]


# Pasted text: (input, expected (ecosystem, name) pairs in order)
PASTE_CASES = [
    ("pip install requests", pypi("requests")),
    ("pip3 install requests flask", pypi("requests", "flask")),
    ("python -m pip install --upgrade numpy", pypi("numpy")),
    ("python3.12 -m pip install -U 'pandas>=2' scipy", pypi("pandas", "scipy")),
    ("!pip install transformers", pypi("transformers")),
    ("%pip install -q datasets", pypi("datasets")),
    ("$ pip install httpx", pypi("httpx")),
    ("sudo pip install ansible", pypi("ansible")),
    ("RUN pip install --no-cache-dir gunicorn==22.0.0", pypi("gunicorn")),
    ("poetry add fastapi", pypi("fastapi")),
    ("uv add polars", pypi("polars")),
    ("uv pip install ruff", pypi("ruff")),
    ("pipenv install django", pypi("django")),
    ("pip install -r requirements.txt rich", pypi("rich")),
    ("pip install -i https://example.com/simple tqdm", pypi("tqdm")),
    ('pip install "requests[security]>=2.0"', pypi("requests")),
    ("pip install Flask_SQLAlchemy", pypi("flask-sqlalchemy")),
    ("npm install express", npm("express")),
    ("npm i -D typescript @types/node", npm("typescript", "@types/node")),
    ("yarn add react react-dom", npm("react", "react-dom")),
    ("yarn global add nodemon", npm("nodemon")),
    ("pnpm add zod", npm("zod")),
    ("bun add hono", npm("hono")),
    ("npm install --registry https://registry.example.com left-pad", npm("left-pad")),
    ("npm install @angular/core@17.1.0", npm("@angular/core")),
    ("Run `pip install requests` and then `npm i axios`.", pypi("requests") + npm("axios")),
    ("pip install black && npm install prettier", pypi("black") + npm("prettier")),
    ("import numpy as np", pypi("numpy")),
    ("import os, json, yaml", pypi("pyyaml")),
    ("from sklearn.model_selection import train_test_split", pypi("scikit-learn")),
    ("import cv2\nfrom PIL import Image\nimport jwt", pypi("opencv-python", "pillow", "pyjwt")),
    ("from bs4 import BeautifulSoup", pypi("beautifulsoup4")),
    ("from dateutil import parser", pypi("python-dateutil")),
    ("from google.cloud import storage", pypi("google-cloud-storage")),
    ("import google.protobuf", pypi("protobuf")),
    ("from . import views\nfrom .models import User", []),
    ("from __future__ import annotations", []),
    ("const express = require('express');", npm("express")),
    ('const fs = require("fs");\nconst p = require("node:path");', []),
    ("import React, { useState } from 'react';", npm("react")),
    ("import { join } from 'path';\nimport x from './x';", []),
    ("import 'dotenv/config';", npm("dotenv")),
    ("const m = await import('chalk');", npm("chalk")),
    ("import { S3Client } from '@aws-sdk/client-s3';", npm("@aws-sdk/client-s3")),
    ("import get from 'lodash/get';", npm("lodash")),
    ("export { default } from 'some-lib';", npm("some-lib")),
    ("import {\n  a,\n  b,\n} from 'multi-line-lib';", npm("multi-line-lib")),
    ("requests\nflask==3.0.0\n# comment\n\nnumpy", pypi("requests", "flask", "numpy")),
]


@pytest.mark.parametrize("text,expected", PASTE_CASES)
def test_paste(text, expected):
    assert names(parse_text(text)) == expected


# Prose that mentions install commands must not produce packages.
@pytest.mark.parametrize(
    "text",
    [
        "Then just pip install the remaining packages you need.",
        "You can npm install whatever you like.",
        "We need to import data from the spreadsheet.",
        "Flip install mode before starting.",
    ],
)
def test_prose_is_not_mistaken_for_commands(text):
    assert parse_text(text).packages == []


def test_realistic_chat_answer():
    text = (FIXTURES / "chat_answer.md").read_text()
    # Install commands come first, then anything only seen in imports.
    assert names(parse_text(text)) == (
        pypi("pillow", "boto3", "image-resizer-pro")
        + npm("sharp", "aws-sdk-v3-helper")
        + pypi("opencv-python")
        + npm("@aws-sdk/client-s3")
    )


def test_versions_are_kept_only_when_exact():
    result = parse_text("pip install requests==2.31.0 flask>=3 django~=5.0 numpy===1.26.4")
    versions = {p.name: p.version for p in result.packages}
    assert versions == {
        "requests": "2.31.0",
        "flask": None,
        "django": None,
        "numpy": "1.26.4",
    }


def test_npm_versions_are_kept_only_when_exact():
    result = parse_text("npm i express@4.19.2 react@^18 vue@latest @nestjs/core@10.3.0")
    versions = {p.name: p.version for p in result.packages}
    assert versions == {
        "express": "4.19.2",
        "react": None,
        "vue": None,
        "@nestjs/core": "10.3.0",
    }


def test_duplicates_are_merged_and_a_later_version_fills_the_gap():
    result = parse_text("import requests\npip install Requests==2.31.0 requests")
    assert result.packages == [PackageRef("pypi", "requests", "2.31.0")]


def test_bare_list_uses_the_chosen_ecosystem():
    assert names(parse_text("express\nlodash@4.17.21", ecosystem="npm")) == npm("express", "lodash")


def test_pasted_package_json_is_recognised():
    text = json.dumps({"dependencies": {"express": "4.19.2"}})
    assert names(parse_text(text)) == npm("express")


def test_unknown_ecosystem_is_refused():
    with pytest.raises(ParseError):
        parse_text("requests", ecosystem="rubygems")


# ---- requirements.txt and package.json ----


def test_requirements_file():
    result = parse_requirements((FIXTURES / "requirements.txt").read_text())
    assert names(result) == pypi(
        "flask", "flask-sqlalchemy", "requests", "pywin32", "python-dateutil", "django"
    )
    versions = {p.name: p.version for p in result.packages}
    assert versions["flask"] == "3.0.3"
    assert versions["python-dateutil"] == "2.9.0"  # joined across the line continuation
    assert result.rejected == 2  # ./local_pkg and the tarball URL


def test_package_json_file():
    result = parse_package_json((FIXTURES / "package.json").read_text())
    assert names(result) == npm("express", "@types/node", "lodash", "jest")
    assert result.rejected == 2  # file: and git+ dependencies
    assert dict((p.name, p.version) for p in result.packages)["express"] == "4.19.2"


def test_package_json_tilde_range_is_a_version_not_a_path():
    text = json.dumps({"dependencies": {"lodash": "~4.17.21", "local": "~/code/local"}})
    result = parse_package_json(text)
    assert names(result) == npm("lodash")
    assert result.rejected == 1


def test_package_json_ignores_non_string_and_non_dict_sections():
    text = json.dumps({"dependencies": ["express"], "devDependencies": {"jest": 29}})
    assert names(parse_package_json(text)) == npm("jest")


@pytest.mark.parametrize("text", ["[1, 2, 3]", '"just a string"', "{not json"])
def test_package_json_must_be_an_object(text):
    with pytest.raises(ParseError):
        parse_package_json(text)


def test_deeply_nested_json_is_refused_before_parsing():
    with pytest.raises(ParseError, match="nested"):
        parse_package_json('{"a":' * 1000 + "1" + "}" * 1000)


# ---- uploads ----


def test_upload_requirements():
    data = (FIXTURES / "requirements.txt").read_bytes()
    assert ("pypi", "flask") in names(parse_upload("requirements.txt", data))


def test_upload_package_json():
    data = (FIXTURES / "package.json").read_bytes()
    assert ("npm", "express") in names(parse_upload("package.json", data))


def test_upload_content_decides_the_format():
    data = b'{"dependencies": {"express": "4.19.2"}}'
    assert names(parse_upload("deps.txt", data)) == npm("express")


def test_upload_strips_utf8_bom():
    assert names(parse_upload("requirements.txt", b"\xef\xbb\xbfrequests\n")) == pypi("requests")


@pytest.mark.parametrize(
    "filename,data,message",
    [
        ("evil.exe", b"requests", "Only .txt and .json"),
        ("requirements", b"requests", "Only .txt and .json"),
        ("requirements.txt.php", b"requests", "Only .txt and .json"),
        ("requirements.txt", b"PK\x03\x04\x00\x00binary", "binary"),
        ("requirements.txt", b"\xff\xfe\xfa not utf-8", "UTF-8"),
        ("package.json", b"requests==2.0", "not valid JSON"),
        ("requirements.txt", b"a" * (256 * 1024 + 1), "too large"),
    ],
)
def test_upload_rejections(filename, data, message):
    with pytest.raises(ParseError, match=message):
        parse_upload(filename, data)


# ---- single package ----


def test_single_package():
    result = parse_single("pypi", "Flask_Login", "0.6.3")
    assert result.packages == [PackageRef("pypi", "flask-login", "0.6.3")]


def test_single_scoped_npm_package():
    result = parse_single("npm", "@Types/Node", None)
    assert result.packages == [PackageRef("npm", "@types/node", None)]


@pytest.mark.parametrize(
    "ecosystem,name,version",
    [
        ("maven", "requests", None),
        ("pypi", "../../etc/passwd", None),
        ("pypi", "", None),
        ("npm", "express", "^4.0.0"),
        ("pypi", "requests", "1.0; rm -rf /"),
    ],
)
def test_single_package_rejections(ecosystem, name, version):
    with pytest.raises(ParseError):
        parse_single(ecosystem, name, version)


# ---- hostile input ----


@pytest.mark.parametrize(
    "ecosystem,name",
    [
        ("pypi", "../etc/passwd"),
        ("pypi", ".."),
        ("pypi", ".env"),
        ("pypi", "-rf"),
        ("pypi", "requests/../../admin"),
        ("pypi", "evil.com/x"),
        ("pypi", "https://evil.example/pkg"),
        ("pypi", "requests\nHost: evil.example"),
        ("pypi", "requests\r\nX-Injected: 1"),
        ("pypi", "req uests"),
        ("pypi", "requests%2F..%2F"),
        ("pypi", "requests?x=1"),
        ("pypi", "requests#frag"),
        ("pypi", "reqυests"),  # Greek upsilon homoglyph
        ("pypi", "a" * 215),
        ("npm", "@evil.com"),
        ("npm", "@scope"),
        ("npm", "@scope/"),
        ("npm", "@scope/../../x"),
        ("npm", "@SCOPE/Name"),
        ("npm", "user@evil.example"),
        ("pypi", "@scope/name"),
    ],
)
def test_hostile_names_are_invalid(ecosystem, name):
    assert not is_valid_name(ecosystem, name)


def test_longest_legal_name_is_accepted():
    assert is_valid_name("npm", "a" * 214)


def test_hostile_paste_yields_only_safe_names():
    text = (
        "pip install ../../etc/passwd https://evil.example/x.whl git+https://evil.example/r.git "
        "'requests\nHost: evil.example' " + "a" * 300 + "\n"
        "npm install user/repo ./local file:../x @evil.com\n"
        "import ..evil\n"
    )
    result = parse_text(text)
    for package in result.packages:
        assert is_valid_name(package.ecosystem, package.name)
        assert "/" not in package.name or package.name.startswith("@")
    assert result.rejected >= 6


def test_nul_bytes_are_stripped_from_paste():
    assert names(parse_text("pip install req\x00uests")) == pypi("requests")


def test_paste_size_limit():
    with pytest.raises(ParseError, match="too large"):
        parse_text("x" * (256 * 1024 + 1))


def test_results_are_capped_at_200():
    text = "\n".join(f"pip install package-{i}" for i in range(250))
    result = parse_text(text)
    assert len(result.packages) == MAX_PACKAGES
    assert result.truncated is True


@pytest.mark.parametrize(
    "text",
    [
        "` " * 120_000,
        "&&" * 120_000,
        "pip install " + "-" * 250_000,
        "pip install " + "'" * 250_000,
        "import " + "a, " * 80_000 + "!",
        "from " + "a." * 120_000 + " import",
        ("import " + "x " * 600 + "from ") * 200,
    ],
    ids=["backticks", "ampersands", "dashes", "quotes", "import-list", "dotted-from", "js-from"],
)
def test_pathological_input_stays_fast(text):
    import time

    start = time.perf_counter()
    parse_text(text[: 256 * 1024])
    assert time.perf_counter() - start < 0.5


# ---- helpers ----


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Flask_SQLAlchemy", "flask-sqlalchemy"),
        ("zope.interface", "zope-interface"),
        ("a__b..c--d", "a-b-c-d"),
        ("PyYAML", "pyyaml"),
    ],
)
def test_pep503_normalisation(raw, expected):
    assert normalise_name("pypi", raw) == expected


def test_npm_names_keep_dots_and_underscores():
    assert normalise_name("npm", "Socket.IO_client") == "socket.io_client"


@pytest.mark.parametrize(
    "module,expected",
    [
        ("os.path", None),
        ("asyncio", None),
        ("__future__", None),
        ("yaml", "PyYAML"),
        ("Crypto.Cipher", "pycryptodome"),
        ("google.cloud.bigquery", "google-cloud-bigquery"),
        ("azure.storage.blob", "azure-storage-blob"),
        ("totally_unknown_mod", "totally_unknown_mod"),
    ],
)
def test_import_to_distribution(module, expected):
    assert import_to_distribution(module) == expected
