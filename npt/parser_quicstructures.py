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

import npt.parser
from typing     import Any, cast, Optional, Union, List, Tuple

from abc         import ABC, abstractmethod
from dataclasses import dataclass

def stem(phrase):
    if phrase[-1] == 's':
        return phrase[:-1]
    else:
        return phrase

def valid_field_name_convertor(name):
    if name is not None:
        return name.lower().replace(" ", "_").replace("-","_")
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
    

class QUICStructureParser(npt.parser.Parser):
    def __init__(self) -> None:
        super().__init__()

    def _process_field(self, struct: npt.parser.Structure, field: npt.parser.Field) -> npt.protocol.StructField:
        field_name = valid_field_name_convertor(field.name)
        struct_name = valid_type_name_convertor(struct.name)
        bitstring_name = f'{struct_name}_{field_name}'
        size = field.size
        # Temporarily handle arbitrary and range fields
        if isinstance(field.size, npt.parser.Range):
            size = 1337
        # Temporarily handle variable length encoded fields
        if field.size == 'i':
            size = 8000
        field_type = npt.protocol.BitString(
                name = bitstring_name,
                size = npt.protocol.ConstantExpression(npt.protocol.Number(), size)
        )
        struct_field = npt.protocol.StructField(
                field_name = field_name,
                field_type = field_type
        )
        self.proto.add_type(field_type)
        return struct_field

    def _traverse_field(self, struct: npt.parser.Structure, field: Union[npt.parser.FieldType, npt.parser.StructContainer]) -> npt.protocol.StructField:
        if isinstance(field, npt.parser.Field):
            struct_field = self._process_field(struct, field)
            return struct_field
        # TODO: Handle container fields
        if isinstance(field, npt.parser.StructContainer):
            temp = npt.parser.Field(field.name, field.size, None)
            struct_field = self._process_field(struct, temp)
            return struct_field
        if isinstance(field, npt.parser.RepeatingField) or isinstance(field, npt.parser.OptionalField):
            if isinstance(field.target, npt.parser.Field):
                temp = npt.parser.Field(field.target.name, field.target.size, field.target.value)
                struct_field = self._process_field(struct, temp)
            else:
                struct_field = self._traverse_field(struct, field.target)
            return struct_field

    def _process_structure(self, struct: npt.parser.Structure) -> npt.protocol.Struct:
        fields = []
        for field in struct.fields:
            fields.append(self._traverse_field(struct, field))
        return npt.protocol.Struct(
                name        = valid_type_name_convertor(struct.name),
                fields      = fields,
                constraints = [],
                actions     = []
        )

    def _process_enum(self, enum: npt.parser.Enum) -> npt.protocol.Enum:
        pass
        # TODO: Handle conversion of Enums

    def process_parsed_representation(self, representation: npt.parser.ParsedRepresentation) -> List[npt.protocol.Struct]:
        structures: List[npt.protocol.Struct] = []
        enums: List[npt.protocol.Enum] = []
        for struct in representation.structs:
            structure = self._process_structure(struct)
            if structure is not None:
                structures.append(structure)
            else:
                # TODO: custom exceptions for failures
                print(f'Failed to convert {struct.name} to internal structure')
        for enum in representation.enums:
            pass
            # TODO: Handle converted enums
        return structures

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

        quic_representation = npt.parser.ParsedRepresentation(input, 'npt/grammar_quicstructures.txt')
        quic_representation.remove_struct('Example Structure')
        structures: List[npt.protocol.Struct] = self.process_parsed_representation(quic_representation)
        for struct in structures:
            self.proto.add_type(struct)
            self.proto.define_pdu(valid_type_name_convertor(struct.name))
        self.proto.set_protocol_name(quic_representation.name)
        return self.proto
