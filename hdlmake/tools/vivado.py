#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 - 2015 CERN
# Author: Pawel Szostek (pawel.szostek@cern.ch)
# Multi-tool support by Javier D. Garcia-Lasheras (javier@garcialasheras.com)
#
# This file is part of Hdlmake.
#
# Hdlmake is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Hdlmake is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Hdlmake.  If not, see <http://www.gnu.org/licenses/>.
#

"""Module providing support for Xilinx Vivado synthesis"""


from __future__ import absolute_import
from .xilinx import ToolXilinx
from .make_sim import ToolSim
from hdlmake.srcfile import (XDCFile, XCIFile, NGCFile, XMPFile,
                             XCOFile, COEFile, BDFile, TCLFile,
                             MIFFile)


class ToolVivado(ToolXilinx, ToolSim):

    """Class providing the interface for Xilinx Vivado synthesis"""

    TOOL_INFO = {
        'name': 'vivado',
        'id': 'vivado',
        'windows_bin': 'vivado -mode tcl -source',
        'linux_bin': 'vivado -mode tcl -source',
        'project_ext': 'xpr'
    }

    STANDARD_LIBS = ['ieee', 'std']

    SUPPORTED_FILES = [XDCFile, XCIFile, NGCFile, XMPFile,
                       XCOFile, COEFile, BDFile, TCLFile,
                       MIFFile]

    CLEAN_TARGETS = {'clean': ["run.tcl", ".Xil", "*.jou", "*.log", "*.pb",
                               "$(PROJECT).cache", "$(PROJECT).data", "work",
                               "$(PROJECT).runs", "$(PROJECT).hw",
                               "$(PROJECT).ip_user_files", "$(PROJECT_FILE)"]}

    TCL_CONTROLS = {'bitstream': 'launch_runs impl_1 -to_step write_bitstream'
                                 '\n'
                                 'wait_on_run impl_1'}

    SIMULATOR_CONTROLS = {'vlog': 'xvlog $<',
                          'vhdl': 'xvhdl $<',
                          'compiler': 'xelab -debug all $(TOP_MODULE) '
                                      '-s $(TOP_MODULE)'}

    def __init__(self):
        super(ToolVivado, self).__init__()
        self._tool_info.update(ToolVivado.TOOL_INFO)
        self._supported_files.extend(ToolVivado.SUPPORTED_FILES)
        self._standard_libs.extend(ToolVivado.STANDARD_LIBS)
        self._clean_targets.update(ToolVivado.CLEAN_TARGETS)
        self._tcl_controls.update(ToolVivado.TCL_CONTROLS)
        self._simulator_controls.update(ToolVivado.SIMULATOR_CONTROLS)

    def makefile_sim_compilation(self):
        """Generate compile simulation Makefile target for Vivado Simulator"""
        self.writeln("simulation: $(VERILOG_OBJ) $(VHDL_OBJ)")
        self.writeln("\t\t" + ToolVivado.SIMULATOR_CONTROLS['compiler'])
        self.writeln()
        self.makefile_sim_dep_files()
