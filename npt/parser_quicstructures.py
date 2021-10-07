# =================================================================================================
# Copyright (C) 2018-2020 University of Glasgow
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

import string
import parsley

import npt.rfc as rfc
import npt.protocol

from npt.parser import Parser
from typing     import Any, cast, Optional, Union, List, Tuple

def stem(phrase):
    if phrase[-1] == 's':
        return phrase[:-1]
    else:
        return phrase

def valid_field_name_convertor(name):
    if name is not None:
        return name.lower().replace(" ", "_")
    else:
        return None

def valid_type_name_convertor(name):
    if name[0].isdigit():
        name = "T" + name
    name = ' '.join(name.replace('\n',' ').split())
    return name.capitalize().replace(" ", "_").replace("-", "_")

def int_to_bytes(x: int) -> bytes:
    return x.to_bytes((x.bit_length() + 7) // 8, 'big')

class QUICStructureParser(Parser):
    def __init__(self) -> None:
        super().__init__()

    def variable_length_convertor(self, data: int) -> int:
        '''
        RFC9000 Appendix A.1
        '''
        byte_data = list(int_to_bytes(data))
        v = byte_data[0] & 0x3f
        for b in byte_data[1:]:
            v = (v << 8) + b
        return v

    def get_struct(self, name: str) -> npt.protocol.Struct:
        for struct in self.structs:
            if name == struct.name:
                return struct

    def new_field(self, name: str, size: Optional[npt.protocol.Expression], value: Optional[Any] = None) -> npt.protocol.StructField:
        return npt.protocol.StructField(
            field_name=valid_field_name_convertor(name),
            field_type=npt.protocol.BitString(name=valid_field_name_convertor(name).capitalize(), size=size)
        )

    def new_struct(self, name: str, fields: List[npt.protocol.StructField]) -> npt.protocol.Struct:
        return npt.protocol.Struct(name=valid_field_name_convertor(name).capitalize(), fields=fields, constraints=[], actions=[])

    def new_constant(self, value: Any) -> npt.protocol.ConstantExpression:
        return npt.protocol.ConstantExpression(npt.protocol.Number, value)

    def build_parser(self):
        self.structs = []
        self.enums = []
        with open("npt/grammar_quicstructures.txt") as grammarFile:
            return parsley.makeGrammar(grammarFile.read(),
                                   {
                                     "ascii_uppercase"          : string.ascii_uppercase,
                                     "ascii_lowercase"          : string.ascii_lowercase,
                                     "ascii_letters"            : string.ascii_letters,
                                     "punctuation"              : string.punctuation,
                                     "new_field"                : self.new_field,
                                     "new_struct"               : self.new_struct,
                                     "new_constant"             : self.new_constant,
                                   })

    def process_structure(self, artwork: rfc.Artwork, parser):
        try:
            print(artwork.content.content)
            structure = parser(artwork.content.content).packet()
            print(structure)
        except Exception as e:
            print(f'{artwork.name} is not a structure')


    def process_section(self, section: rfc.Section, parser):
        for content in section.content:
            if isinstance(content, rfc.Figure):
                for artwork in content.content:
                    if isinstance(artwork, rfc.Artwork):
                        self.process_structure(artwork, parser)
        for sub_section in section.sections:
            self.process_section(sub_section, parser)

        
    def build_protocol(self, proto: Optional[npt.protocol.Protocol], input: Union[str, rfc.RFC], name: str=None) -> npt.protocol.Protocol:
        """
        Build a Protocol object for the protocol represented by the input string.

        Arguments:
            proto -- A protocol object. If specified, the input parser should augment this Protocol
                     rather than creating a new Protocol. This allows input parsers to be chained
                     together to define a single Protocol.
            input -- A string representing a protocol definition or RFC DOM object

        Returns:
            A Protocol object
        """
        if proto is None:
            self.proto = npt.protocol.Protocol()
        else:
            self.proto = proto

        parser = self.build_parser()
        structs : List[npt.protocol.Struct] = []

        # TESTING PACKET PARSING
        test_packet = '''
        Example FRAME {
            Basic Field (10),
            Another Basic Field (10),
        }
        '''
        structure: npt.protocol.Struct = parser(test_packet).packet()
        for field in structure.fields.values():
            print(field.field_name, field.field_type.size)

        # if isinstance(input, rfc.RFC):
        #     for section in input.middle.content:
        #         self.process_section(section, parser)

        self.proto.set_protocol_name('QUIC')
        return self.proto
