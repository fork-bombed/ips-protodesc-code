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
        if name[0].isdigit():
            name = "F" + name
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


class QUICStructureParser(npt.parser.Parser):
    def __init__(self) -> None:
        super().__init__()
        self.structs = {}
        self.enums = {}

    def _to_number_expression(self, field: npt.protocol.StructField) -> npt.protocol.MethodInvocationExpression:
        return npt.protocol.MethodInvocationExpression(
                npt.protocol.FieldAccessExpression(npt.protocol.SelfExpression(), field.field_name), 
                'to_number', 
                []
        )

    def _argument_expression(self, expression: npt.protocol.Expression) -> npt.protocol.ArgumentExpression:
        return npt.protocol.ArgumentExpression(
                'other', 
                expression
        )

    def _const_expression(self, number: int) -> npt.protocol.ConstantExpression:
        return npt.protocol.ConstantExpression(npt.protocol.Number(), number)

    def _process_field_value(self, struct_field: npt.protocol.StructField, value: Union[int, npt.parser.Range]) -> Optional[List[npt.protocol.MethodInvocationExpression]]:
        if value is None: return
        if isinstance(value, int):
            const_expr = self._const_expression(value)
            return [
                npt.protocol.MethodInvocationExpression(
                    self._to_number_expression(struct_field),
                    'eq',
                    [self._argument_expression(const_expr)]
                )
            ]
        elif isinstance(value, npt.parser.Range):
            if value.max is None: return
            minval = value.min or 0
            maxval = value.max
            min_expr = self._const_expression(minval)
            max_expr = self._const_expression(maxval)
            ge_expr = npt.protocol.MethodInvocationExpression(
                        self._to_number_expression(struct_field),
                        'ge',
                        [self._argument_expression(min_expr)]
                    )
            le_expr = npt.protocol.MethodInvocationExpression(
                        self._to_number_expression(struct_field),
                        'le',
                        [self._argument_expression(max_expr)]
                    )
            return [
                npt.protocol.MethodInvocationExpression(
                    ge_expr,
                    'and',
                    [self._argument_expression(le_expr)]
                )
            ]
        else:
            return

    def _process_field(self, struct: npt.parser.Structure, field: npt.parser.Field) -> npt.protocol.StructField:
        field_name = valid_field_name_convertor(field.name)
        struct_name = valid_type_name_convertor(struct.name)
        bitstring_name = f'{struct_name}_{field_name}'
        size = field.size
        value = field.value
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
        struct_constraints = self._process_field_value(struct_field, value)
        self.proto.add_type(field_type)
        return struct_field, struct_constraints

    def _traverse_field(self, struct: npt.parser.Structure, field: Union[npt.parser.FieldType, npt.parser.StructContainer]) -> npt.protocol.StructField:
        if isinstance(field, npt.parser.Field):
            struct_field, struct_constraints = self._process_field(struct, field)
        # TODO: Handle container fields
        if isinstance(field, npt.parser.StructContainer):
            temp = npt.parser.Field(field.name, field.size, None)
            struct_field, struct_constraints = self._process_field(struct, temp)
        if isinstance(field, npt.parser.RepeatingField) or isinstance(field, npt.parser.OptionalField):
            if isinstance(field.target, npt.parser.Field):
                temp = npt.parser.Field(field.target.name, field.target.size, field.target.value)
                struct_field, struct_constraints = self._process_field(struct, temp)
            else:
                struct_field, struct_constraints = self._traverse_field(struct, field.target)
        return struct_field, struct_constraints
        

    def _process_structure(self, struct: npt.parser.Structure) -> npt.protocol.Struct:
        fields = []
        constraints = []
        for field in struct.fields:
            field_type, field_constraints = self._traverse_field(struct, field)
            fields.append(field_type)
            if field_constraints is not None:
                constraints += field_constraints
        return npt.protocol.Struct(
                name        = valid_type_name_convertor(struct.name),
                fields      = fields,
                constraints = constraints,
                actions     = []
        )

    def _process_enum(self, enum: npt.parser.Enum) -> npt.protocol.Enum:
        variants = []
        for value in enum.values:
            if value.type is None:
                raise npt.protocol.ProtocolTypeError("Enum must point to a type")
            type_name = valid_type_name_convertor(value.type.name)
            variant = self.structs.get(type_name)
            if variant is not None:
                variants.append(variant)
        return npt.protocol.Enum(valid_type_name_convertor(enum.name), variants)

    def process_parsed_representation(self, representation: npt.parser.ParsedRepresentation) -> None:
        for struct in representation.structs:
            processed_struct = self._process_structure(struct)
            if processed_struct is not None:
                self.structs[processed_struct.name] = processed_struct
                self.proto.add_type(processed_struct)
        for enum in representation.enums:
            processed_enum = self._process_enum(enum)
            if processed_enum is not None:
                self.enums[processed_enum.name] = processed_enum
                self.proto.add_type(processed_enum)

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

        quic_representation = npt.parser.ParsedRepresentation(cast(rfc.RFC,input), 'npt/grammar_quicstructures.txt')
        self.proto.set_protocol_name(quic_representation.name)
        self.process_parsed_representation(quic_representation)
        for struct in self.structs.values():
            self.proto.define_pdu(valid_type_name_convertor(struct.name))
        for struct in self.enums.values():
            self.proto.define_pdu(valid_type_name_convertor(struct.name))
        return self.proto
