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
from typing     import cast, Optional, Union, List, Tuple

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

class QUICStructureParser(Parser):
    def __init__(self) -> None:
        super().__init__()

    def new_field(self, full_label, short_label, options, size, units, value_constraint, is_present, is_array):
        return {
                "full_label": valid_field_name_convertor(full_label),
                "options" : options, 
                "size": size, 
                "units": units, 
                "value_constraint": value_constraint, 
                "is_present": is_present, 
                "is_array": is_array 
                }

    def new_this(self):
        return ("this")

    def new_methodinvocation(self, target, method, arguments):
        return("methodinvocation", target, method, arguments)

    def new_fieldaccess(self, target, field_name):
        return ("fieldaccess", target, field_name)

    def new_constant(self, type_name, value):
        return ("const", type_name, value)

    def build_parser(self):
        self.structs = {}
        self.enums = {}
        self.functions = {}
        self.serialise_to = {}
        self.parse_from = {}
        with open("npt/grammar_quicstructures.txt") as grammarFile:
            return parsley.makeGrammar(grammarFile.read(),
                                   {
                                     "ascii_uppercase"          : string.ascii_uppercase,
                                     "ascii_lowercase"          : string.ascii_lowercase,
                                     "ascii_letters"            : string.ascii_letters,
                                     "punctuation"              : string.punctuation,
                                   })

    def process_structure(self, structure: str):
        pass

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
