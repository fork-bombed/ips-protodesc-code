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

from npt.parser import Parser, ParsedRepresentation
from typing     import Any, cast, Optional, Union, List, Tuple

from abc         import ABC, abstractmethod
from dataclasses import Field, dataclass, field

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

def variable_length_convertor(self, data: int) -> int:
        '''
        RFC9000 Appendix A.1
        '''
        byte_data = list(int_to_bytes(data))
        v = byte_data[0] & 0x3f
        for b in byte_data[1:]:
            v = (v << 8) + b
        return v


class FieldType(ABC):
    '''
    Base class to simplify field constraints
    '''
    @abstractmethod
    def generate_constraints(self, field: npt.protocol.StructField) -> List[npt.protocol.MethodInvocationExpression]:
        ''' Abstract class, all field types must generate corresponding constraints '''


@dataclass(frozen=True)
class SimpleConstraint:
    def to_number(self, field: npt.protocol.StructField) -> npt.protocol.MethodInvocationExpression:
        return npt.protocol.MethodInvocationExpression(
                npt.protocol.FieldAccessExpression(npt.protocol.SelfExpression(), field.field_name), 
                'to_number', 
                []
        )

    def argument(self, expression: npt.protocol.Expression) -> npt.protocol.ArgumentExpression:
        return npt.protocol.ArgumentExpression(
                'other', 
                expression
        )


@dataclass(frozen=True)
class FixedField(FieldType, SimpleConstraint):
    value: Union[npt.protocol.Expression, tuple]

    def generate_constraints(self, field: npt.protocol.StructField) -> List[npt.protocol.MethodInvocationExpression]:
        if isinstance(self.value, npt.protocol.Expression):
            return [
                npt.protocol.MethodInvocationExpression(
                    super().to_number(field),
                    'eq',
                    [super().argument(self.value)]
                )
            ]
        else:
            return [
                npt.protocol.MethodInvocationExpression(
                    npt.protocol.MethodInvocationExpression(
                        super().to_number(field),
                        'ge',
                        [super().argument(self.value[0])]
                    ),
                    'and',
                    [
                        super().argument(
                            npt.protocol.MethodInvocationExpression(
                                super().to_number(field),
                                'le',
                                [super().argument(self.value[1])]
                            )
                        )
                    ]
                )
            ]

@dataclass
class FieldWrapper:
    '''
    Wrapper for holding fields with corresponding constraints
    '''
    field: npt.protocol.StructField
    constraints: Optional[List[npt.protocol.MethodInvocationExpression]]
    

class QUICStructureParser(Parser):
    def __init__(self) -> None:
        super().__init__()

    def get_struct(self, name: str) -> Optional[npt.protocol.Struct]:
        for struct in self.structs:
            if name == struct.name:
                return struct
        return None

    def new_field(self, name: str, size: Optional[npt.protocol.Expression], constraints: Optional[FieldType] = None) -> npt.protocol.StructField:
        field = npt.protocol.StructField(
                field_name = valid_field_name_convertor(name),
                field_type = npt.protocol.BitString(
                        # Temporary naming, will be replaced when field is built
                        name = 'T'+valid_field_name_convertor(name),
                        size = size
                )
        )
        field_constraints = None
        if constraints is not None:
            field_constraints = constraints.generate_constraints(field)
        return FieldWrapper(field, field_constraints)

    def new_struct(self, name: str, wrapped_fields: List[FieldWrapper]) -> npt.protocol.Struct:
        constraints = []
        fields = []
        struct_name = valid_field_name_convertor(name).capitalize()
        for field in wrapped_fields:
            if field.constraints is not None:
                constraints += field.constraints
            field_type = field.field.field_type
            if isinstance(field_type, npt.protocol.BitString):
                # Update temporary naming to include structure name
                field_type.name = f'{struct_name}_{field_type.name[1:]}'
                fields.append(field.field)
        return npt.protocol.Struct(
                name        = valid_field_name_convertor(name).capitalize(),
                fields      = [x.field for x in wrapped_fields], 
                constraints = constraints, 
                actions     = []
        )

    def new_constant(self, value: Any) -> npt.protocol.ConstantExpression:
        return npt.protocol.ConstantExpression(npt.protocol.Number(), value)

    def build_parser(self):
        self.structs: List[npt.protocol.Struct] = []
        self.enums = []
        with open("npt/grammar_quicstructures.txt") as grammarFile:
            return parsley.makeGrammar(grammarFile.read(),
                                   {
                                     "new_field"                : self.new_field,
                                     "new_struct"               : self.new_struct,
                                     "new_constant"             : self.new_constant,
                                     "FixedField"               : FixedField
                                   })

    def process_structure(self, artwork: rfc.Artwork, parser):
        if type(artwork.content) is rfc.Text:
            try:
                structure = parser(artwork.content.content).packet()
                print(structure)
            except Exception as e:
                print(e)


    def process_section(self, section: rfc.Section, parser):
        for content in section.content:
            if isinstance(content, rfc.Figure):
                for artwork in content.content:
                    if isinstance(artwork, rfc.Artwork):
                        self.process_structure(artwork, parser)
        if section.sections is not None:
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

        # parser = self.build_parser()
        # structs : List[npt.protocol.Struct] = []

        # # TESTING PACKET PARSING
        # test_packet = '''
        # Example FRAME {
        #     Basic Field (10),
        #     Another Basic Field (10),
        #     Fixed Field (8) = 1..5,
        # }
        # '''
        # structure: npt.protocol.Struct = parser(test_packet).packet()
        # print(structure)
        # for field in structure.fields.values():
        #     print(f'Field ({field.field_name})')
        #     print(f'\tBitstring ({field.field_type.name})')
        
        # for constraint in structure.constraints:
        #     print(f'Constraint ({constraint})')

        # self.structs.append(structure)

        quic_representation = ParsedRepresentation()
        parser = quic_representation.build_grammar('npt/grammar_quicstructures.txt')

        structs = quic_representation.generate_representation(input, parser)
        for struct in structs:
            print(struct)

        # if isinstance(input, rfc.RFC):
        #     for section in input.middle.content:
        #         self.process_section(section, parser)

        self.proto.set_protocol_name('QUIC')
        return self.proto
