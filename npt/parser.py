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
from typing       import Dict, List, Tuple, Optional, Any, Union
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
class StructContainer(FieldType):
    size: Union[int, Range]
    target: Structure

    def __str__(self):
        return f'StructContainer(name={self.name}, size={self.size}, target=Structure({self.target.name}))'


@dataclass
class Field(FieldType):
    size: Union[int, Range]
    value: Optional[Any]

    def __str__(self):
        val = f', value={self.value if self.value is not None else None}'
        return f'Field(name={self.name}, size={self.size}{val if self.value is not None else ""})'


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


# ==== Parsed Representation ====


class ParsedRepresentation:
    def __init__(self, document: Union[str, rfc.RFC], grammar_filename: str) -> None:
        self.parser = self.build_grammar(grammar_filename)
        self.name, self.structs = self.generate_representation(document, self.parser)

    def add_struct(self, struct: Structure) -> None:
        self.structs.append(struct)

    def remove_struct(self, struct_name: str) -> None:
        for struct in self.structs:
            if struct.name == struct_name:
                self.structs.remove(struct)

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
        }
        with open(filename) as grammarFile:
            # Combine the parser bindings and user-defined bindings
            return parsley.makeGrammar(grammarFile.read(),{**parser_bindings,**bindings})

    def _get_protocol_name(self, document: Union[str, rfc.RFC]) -> str:
        if isinstance(document, rfc.RFC):
            title = document.front.title
            if title.content is not None:
                if title.content.content is not None:
                    if ':' in title.content.content:
                        return title.content.content.split(':')[0]
            elif title.abbrev is not None:
                return title.abbrev
        # TODO: Fix this for str documents
        return 'Something'

    def _process_structure(self, artwork: rfc.Artwork, parser):
        if type(artwork.content) is rfc.Text:
            try:
                return parser(artwork.content.content).structure()
            except Exception as e:
                pass

    def _process_section(self, section: rfc.Section, parser) -> List[Structure]:
        structs: List[Structure] = []
        for content in section.content:
            if isinstance(content, rfc.Figure):
                for artwork in content.content:
                    if isinstance(artwork, rfc.Artwork):
                        struct = self._process_structure(artwork, parser)
                        if struct is not None:
                            structs.append(struct)
        if section.sections is not None:
            for sub_section in section.sections:
                section_structs = self._process_section(sub_section, parser)
                if section_structs is not None:
                    structs += section_structs
        return structs

    def _parse_structures(self, document: Union[str, rfc.RFC], parser) -> List[Structure]:
        structs: List[Structure] = []
        if isinstance(document, rfc.RFC):
            for section in document.middle.content:
                section_struct = self._process_section(section, parser)
                if section_struct is not None:
                    structs += section_struct
        return structs

    def _get_struct_container(self, field: FieldType, structs: List[Structure]) -> Optional[FieldType]:
        for struct in structs:
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

    def generate_representation(self, document: Union[str, rfc.RFC], parser) -> Tuple[str, List[Structure]]:
        structs: List[Structure] = self._parse_structures(document, parser)
        protocol_name: str = self._get_protocol_name(document)
        for struct in structs:
            fields = []
            for field in struct.fields:
                if isinstance(field, FieldType):
                    container = self._get_struct_container(field, structs)
                    if container is not None:
                        fields.append(container)
                    else:
                        fields.append(field)
                else:
                    fields.append(field)
            struct.fields = fields
        return protocol_name, structs