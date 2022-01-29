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

import abc
from typing       import cast, List, Tuple, Dict, Optional, Any, Union
from dataclasses import dataclass
import npt.protocol
import parsley

import npt.rfc as rfc

class Parser(abc.ABC):

    @abc.abstractmethod
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
        pass

# ==== Parsing Error ====

class ParsingError(Exception):
    def __init__(self, reason):
        self.reason = reason    

# ==== Parsed Objects ====

@dataclass(frozen=True)
class Range:
    min: Optional[int]
    max: Optional[int]

    def __str__(self):
        return f'Range({self.min if self.min is not None else ""}..{self.max if self.max is not None else ""})'


@dataclass
class FieldType:
    name: str


@dataclass
class Structure:
    name: str
    fields: List[Any]

    def __str__(self):
        fields = '\n\t'.join([str(field) for field in self.fields])
        return f'Structure(name={self.name}, fields=\n\t{fields}\n)'


@dataclass
class EnumValue:
    name: str
    type: Optional[Structure] = None

    def __str__(self):
        typed = ''
        if self.type is not None:
            typed = f', type={self.type.name}'
        return f'EnumValue(name={self.name}{typed})'


@dataclass
class Enum:
    name: str
    values: List[EnumValue]

    def __str__(self):
        enumvalues = '\n\t'.join([str(value) for value in self.values])
        return f'Enum(name={self.name}, values=\n\t{enumvalues}\n)'


@dataclass
class StructContainer(FieldType):
    size: Any
    target: Structure

    def __str__(self):
        return f'StructContainer(name={self.name}, size={self.size}, target=Structure({self.target.name}))'


@dataclass
class Field(FieldType):
    size: Any
    value: Optional[Any]

    def __str__(self):
        size = self.size
        if isinstance(size, Field) or isinstance(size, Enum):
            size = size.name
        val = f', value={self.value if self.value is not None else None}'
        return f'Field(name={self.name}, size={size}{val if self.value is not None else ""})'


@dataclass
class RepeatingField(FieldType):
    target: Union[Field, StructContainer]

    def __str__(self):
        return f'RepeatingField({self.target})'


@dataclass
class OptionalField(FieldType):
    target: Union[Field, StructContainer]

    def __str__(self):
        return f'OptionalField({self.target})'


# =======================================================================================
# Parsed Representation boundaries
#
# The parsed representation is used to convert raw data into objects using 
# the Parsley grammar file. This provides a consistent representation across 
# all parsers without imposing any restrictions on the data. The representation 
# is used to increase readability by splitting the parsing and internal 
# representation into clear steps, making it easier to spot any repetition or 
# inefficient code, and increasing the overall modularity of the program. Anything
# that will end up in the internal representation (e.g structures and enums) should 
# be converted to the parsed representation before being sent to the internal 
# representation. The internal representation should be modified to accept a 
# ParsedRepresentation object which will contain all the necessary data to convert 
# into a protocol object.
#
# The parsed representation is simply used to represent data from the parser. It is 
# an intermediate step to ensure that we have all the information before it is type
# checked and converted into the internal representation. This means that the data 
# in the parsed representation does not necessarily need to be correct, as it will be 
# checked when it is converted to the internal representation. Below is a list of 
# actions that can be done by the parsed representation:
#   - Order data
#   - Make links between data
#   - Add or remove data
#
# Below is a list of actions the parsed representation cannot do:
#   - Enforce naming conventions
#   - Type checking
#   - Input validation
# =======================================================================================


class ParsedRepresentation:
    def __init__(self, document: rfc.RFC, grammar_filename: str) -> None:
        self.parser = self.build_grammar(grammar_filename)
        self.structs: List[Structure] = []
        self.enums: List[Enum] = []
        self.name: str = ""
        self.generate_representation(document, self.parser)

    def add_struct(self, struct: Structure) -> None:
        self.structs.append(struct)

    def find_struct(self, struct_name: str) -> Optional[Structure]:
        for struct in self.structs:
            if struct.name == struct_name:
                return struct
        return None

    def remove_struct(self, struct_name: str) -> None:
        for struct in self.structs:
            if struct.name == struct_name:
                self.structs.remove(struct)

    def new_enum(self, enum_name: str, fields: List[EnumValue]) -> Enum:
        return Enum(enum_name, fields)

    def new_enum_value(self, value_name: str) -> EnumValue:
        return EnumValue(value_name)

    def new_struct(self, struct_name: str, fields: List[Field]) -> Structure:
        return Structure(struct_name, fields)

    def new_field(self, field_name: str, size: Union[int, Range], value: Union[int, Range] = None) -> FieldType:
        return Field(field_name, size, value)

    def new_repeating_field(self, target: Field) -> FieldType:
        return RepeatingField(target.name, target)

    def new_optional_field(self, target: Field) -> FieldType:
        return OptionalField(target.name, target)

    def new_range(self, min: int = None, max: int = None) -> Range:
        return Range(min=min, max=max)

    def build_grammar(self, filename: str, bindings: dict = {}):
        parser_bindings = {
            'new_range'             : self.new_range,
            'new_field'             : self.new_field,
            'new_struct'            : self.new_struct,
            'new_optional_field'    : self.new_optional_field,
            'new_repeating_field'   : self.new_repeating_field,
            'new_enum'              : self.new_enum,
            'new_enum_value'        : self.new_enum_value,
        }
        with open(filename) as grammarFile:
            # Combine the parser bindings and user-defined bindings
            return parsley.makeGrammar(grammarFile.read(),{**parser_bindings,**bindings})

    def _get_protocol_name(self, document: rfc.RFC) -> Optional[str]:
        title = document.front.title
        if title.content is not None:
            if title.content.content is not None:
                if ':' in title.content.content:
                    return title.content.content.split(':')[0]
        return None

    def _process_structure(self, artwork: rfc.Artwork, parser) -> Optional[Union[Structure, Enum]]:
        if type(artwork.content) is rfc.Text:
            try:
                return cast(Structure, parser(artwork.content.content).structure())
            # NOTE: ParseError cannot be caught as Parsley doesn't implement its own exceptions.
            #       Have to catch all exceptions for now...
            except Exception as e:
                pass
            try:
                return cast(Enum, parser(artwork.content.content).enum())
            except Exception as e:
                pass
        return None

    def _process_section(self, section: rfc.Section, parser) -> None:
        for content in section.content:
            if isinstance(content, rfc.Figure):
                for artwork in content.content:
                    if isinstance(artwork, rfc.Artwork):
                        struct = self._process_structure(artwork, parser)
                        if struct is not None:
                            if isinstance(struct, Structure):
                                self.structs.append(struct)
                            elif isinstance(struct, Enum):
                                self.enums.append(struct)
        if section.sections is not None:
            for sub_section in section.sections:
                self._process_section(sub_section, parser)

    def _parse_structures(self, document: rfc.RFC, parser) -> None:
        if isinstance(document, rfc.RFC):
            for section in document.middle.content:
                self._process_section(section, parser)

    def _get_struct_container(self, field: FieldType) -> Optional[FieldType]:
        for struct in self.structs:
            if struct.name == field.name:
                container: FieldType
                if isinstance(field, Field):
                    container = StructContainer(field.name, field.size, struct)
                elif isinstance(field, OptionalField):
                    container = OptionalField(field.name, StructContainer(field.target.name, field.target.size, struct))
                elif isinstance(field, RepeatingField):
                    container = RepeatingField(field.name, StructContainer(field.target.name, field.target.size, struct))
                return container
        return None

    def _find_field_length(self, struct: Structure, field: Field) -> Optional[Field]:
        field_name = field.name
        for struct_field in struct.fields:
            if struct_field != field:
                if isinstance(struct_field, Field):
                    struct_field_name = struct_field.name.lower()
                    if field_name.lower() in struct_field_name and ' length' in struct_field_name:
                        return struct_field
        return None      

    def _traverse_structures(self) -> None:
        for struct in self.structs:
            fields = []
            for field in struct.fields:
                if isinstance(field, FieldType):
                    container = self._get_struct_container(field)
                    if container is not None:
                        fields.append(container)
                    else:
                        if isinstance(field, Field):
                            if isinstance(field.size, Range):
                                length_field = self._find_field_length(struct, field)
                                if length_field is not None:
                                    field.size = length_field
                            elif isinstance(field.size, str):
                                for struct in self.structs:
                                    if struct.name == field.size:
                                        field.size = struct
                                for enum in self.enums:
                                    if enum.name == field.size:
                                        field.size = enum
                        fields.append(field)
                else:
                    fields.append(field)
            struct.fields = fields

    def _traverse_enums(self) -> None:
        for enum in self.enums:
            for field in enum.values:
                if isinstance(field, EnumValue):
                    if field.type is None:
                        struct = self.find_struct(field.name)
                        if struct is not None:
                            field.type = struct

    def generate_representation(self, document: rfc.RFC, parser) -> None:
        self._parse_structures(document, parser)
        if self.structs is None:
            raise Exception('No structures to represent')
        protocol_name = self._get_protocol_name(document)
        if protocol_name is not None:
            self.name = protocol_name
        self._traverse_structures()
        self._traverse_enums()

    def __str__(self):
        enums = '\n'.join([str(value) for value in self.enums])
        structs = '\n'.join([str(value) for value in self.structs])
        return f'ParsedRepresentation(name={self.name}):\n{enums}\n{structs}'
        