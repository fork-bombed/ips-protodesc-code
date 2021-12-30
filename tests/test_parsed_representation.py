# =================================================================================================
# Copyright (C) 2018-2019 University of Glasgow
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# SPDX-License-Identifier: BSD-2-Clause
# =================================================================================================

import os
import sys
import unittest

import xml.etree.ElementTree as ET

import npt.protocol
from npt.parser import *

import npt.rfc as rfc
import npt.parser_rfc_xml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class Test_Parsed_Representation(unittest.TestCase):
    def setUp(self):
        with open("examples/rfc9000.xml" , 'r') as example_file:
            raw_content = example_file.read()
            xml_tree = ET.fromstring(raw_content)
            self.document = npt.parser_rfc_xml.parse_rfc(xml_tree)
            self.parsed_representation = ParsedRepresentation(self.document, 'npt/grammar_quicstructures.txt')

    def test_representation_name(self):
        self.assertEqual(self.parsed_representation.name,  "QUIC")

    def test_struct_parser(self):
        struct = Structure(
            name="Test", 
            fields=[
                Field(name="Field One", size=2, value=2),
                Field(name="Field Two", size=Range(None,20), value=None),
                Field(name="Field Three", size='i', value=None),
                Field(name="Field Four", size=Range(None,None), value=Range(3,6))
            ]
        )
        txt_struct = '''
        Test {
            Field One (2) = 2,
            Field Two (..20),
            Field Three (i),
            Field Four (..) = 3..6,
        }
        '''
        parsed_struct = self.parsed_representation.parser(txt_struct).structure()
        self.assertEqual(parsed_struct, struct)

    def _verify_example_structure(self, struct: Structure):
        self.assertEqual(struct.name, 'Example Structure')

    def test_quic_structures(self):
        structs = self.parsed_representation.structs
        self.assertEqual(len(self.parsed_representation.structs), 36)

        self._verify_example_structure(structs[0])
        

