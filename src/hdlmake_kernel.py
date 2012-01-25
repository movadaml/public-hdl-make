#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2011 Pawel Szostek (pawel.szostek@cern.ch)
#
#    This source code is free software; you can redistribute it
#    and/or modify it in source code form under the terms of the GNU
#    General Public License as published by the Free Software
#    Foundation; either version 2 of the License, or (at your option)
#    any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA
#


import os
import msg as p
from makefile_writer import MakefileWriter
from flow import ISEProject
from flow_altera import QuartusProject

class HdlmakeKernel(object):
    def __init__(self, modules_pool, connection, options):
        self.modules_pool = modules_pool
        self.connection = connection
        self.make_writer = MakefileWriter("Makefile")
        self.options = options

    @property
    def top_module(self):
        return self.modules_pool.get_top_module()

    def run(self):
        tm = self.top_module

        if not self.modules_pool.is_everything_fetched():
            self.fetch(unfetched_only = True)

        if tm.action == "simulation":
            self.generate_modelsim_makefile()
        elif tm.action == "synthesis":
            if tm.syn_project == None:
                p.rawprint("syn_project variable must be defined in the manfiest")
                p.quit()
            if tm.target.lower() == "xilinx":
                self.generate_ise_project()
                self.generate_ise_makefile()
                self.generate_remote_synthesis_makefile()
            elif tm.target.lower() == "altera":
                self.generate_quartus_project()
#                self.generate_quartus_makefile()
#                self.generate_quartus_remote_synthesis_makefile()
            else:
                raise RuntimeError("Unrecognized target: "+tm.target)
        else:
            p.print_action_help() and quit()

    def list_modules(self):
        import path
        for m in self.modules_pool:
            if not m.isfetched:
                print("#!UNFETCHED")
                print(m.url+'\n')
            else:
                print(path.relpath(m.path))
                if m.source in ["svn", "git"]:
                    print ("#"+m.url)
                if not len(m.files):
                    print("   # no files")
                else:
                    for f in m.files:
                        print("   " + path.relpath(f.path, m.path))
                print("")
    def list_files(self):
        files_str = [] 
        for m in self.modules_pool:
            if not m.isfetched:
                continue
            files_str.append(" ".join([f.path for f in m.files]))
        print(" ".join(files_str))

    def fetch(self, unfetched_only = False):
        p.rawprint("Fetching needed modules...")
        self.modules_pool.fetch_all(unfetched_only)
        p.vprint(str(self.modules_pool))

    def generate_modelsim_makefile(self):
        from dep_solver import DependencySolver
        p.rawprint("Generating makefile for simulation...")
        solver = DependencySolver()

        pool = self.modules_pool
        if not pool.is_everything_fetched():
            p.echo("A module remains unfetched. Fetching must be done prior to makefile generation")
            p.echo(str([str(m) for m in self.modules_pool.modules if not m.isfetched]))
            quit()
        tm = pool.get_top_module()
        flist = pool.build_global_file_list();
        flist_sorted = solver.solve(flist);
        self.make_writer.generate_modelsim_makefile(flist_sorted, tm)

    def generate_ise_makefile(self):
        p.rawprint("Generating makefile for local synthesis...")

        ise_path = self.__figure_out_ise_path()

        self.make_writer.generate_ise_makefile(top_mod=self.modules_pool.get_top_module(), ise_path=ise_path)

    def generate_remote_synthesis_makefile(self):
        from srcfile import SourceFileFactory
        if self.connection.ssh_user == None or self.connection.ssh_server == None:
            p.rawprint("Connection data is not given. Accessing environmental variables in the makefile")
        p.rawprint("Generating makefile for remote synthesis...")

        top_mod = self.modules_pool.get_top_module()
        if not os.path.exists(top_mod.fetchto):
            p.echo("There are no modules fetched. Are you sure it's correct?")

        ise_path = self.__figure_out_ise_path()
        tcl = self.__search_tcl_file()

        if tcl == None:
            self.__generate_tcl()
            tcl = "run.tcl"
        files = self.modules_pool.build_very_global_file_list()

        sff = SourceFileFactory()
        files.add(sff.new(tcl))
        files.add(sff.new(top_mod.syn_project))

        self.make_writer.generate_remote_synthesis_makefile(files=files, name=top_mod.syn_name, 
        cwd=os.getcwd(), user=self.connection.ssh_user, server=self.connection.ssh_server, ise_path=ise_path)

    def generate_ise_project(self):
        p.rawprint("Generating/updating ISE project...")
        if self.__is_xilinx_screwed():
            p.rawprint("Xilinx environment variable is unset or is wrong.\nCannot generate ise project")
            quit()
        if not self.modules_pool.is_everything_fetched():
            p.echo("A module remains unfetched. Fetching must be done prior to makefile generation")
            p.echo(str([str(m) for m in self.modules_pool.modules if not m.isfetched]))
            quit()
        ise = self.__check_ise_version()
        if os.path.exists(self.top_module.syn_project):
            self.__update_existing_ise_project(ise=ise)
        else:
            self.__create_new_ise_project(ise=ise)

    def generate_quartus_project(self):
        p.rawprint("Generating/updating Quartus project...")

        if not self.modules_pool.is_everything_fetched():
            p.echo("A module remains unfetched. Fetching must be done prior to makefile generation")
            p.echo(str([str(m) for m in self.modules_pool.modules if not m.isfetched]))
            quit()

        if os.path.exists(self.top_module.syn_project + ".qsf"):
            self.__update_existing_quartus_project()
        else:
            self.__create_new_quartus_project()



    def __figure_out_ise_path(self):
        import path
        if self.options.force_ise != None:
            if self.options.force_ise == 0:
                ise = self.__check_ise_version()
            else:
                ise = self.options.force_ise
        else:
            ise = 0

        try:
            ise_path = path.ise_path_32[str(ise)]+'/'
        except KeyError:
            if ise != 0:
                ise_path = "/opt/Xilinx/"+str(ise)+"/ISE_DS/ISE/bin/lin/"
            else:
                ise_path = ""
        return ise_path

    def __is_xilinx_screwed(self):
        if self.__check_ise_version() == None:
            return True
        else:
            return False

    def __check_ise_version(self):
        import subprocess
        xst = subprocess.Popen('which xst', shell=True,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, close_fds=True)
        lines = xst.stdout.readlines()
        if len(lines) == 0:
            p.rawprint("ERROR: Xilinx binaries are not in the PATH variable")
            p.rawprint("       Can't determine ISE version")
            quit()

        xst = str(lines[0].strip())
        if xst == '':
            return None
        else:
            import re
            vp = re.compile(".*?(\d\d\.\d).*")
            m = re.match(vp, xst)
            if m == None:
                return None
            return m.group(1)

    def __update_existing_ise_project(self, ise):
        from dep_solver import DependencySolver
        from srcfile import IDependable
        from flow import ISEProject
        from srcfile import SourceFileSet
        top_mod = self.modules_pool.get_top_module()
        fileset = self.modules_pool.build_global_file_list()
        solver = DependencySolver()
        non_dependable = fileset.inversed_filter(IDependable)
        dependable = solver.solve(fileset)
        all = SourceFileSet()
        all.add(non_dependable)
        all.add(dependable)

        prj = ISEProject(ise=ise, top_mod=self.modules_pool.get_top_module())
        prj.add_files(all)
        prj.add_libs(all.get_libs())
        prj.load_xml(top_mod.syn_project)
        prj.emit_xml(top_mod.syn_project)

    def __create_new_ise_project(self, ise):
        from dep_solver import DependencySolver
        from srcfile import IDependable
        from flow import ISEProject, ISEProjectProperty
        top_mod = self.modules_pool.get_top_module()
        fileset = self.modules_pool.build_global_file_list()
        solver = DependencySolver()
        non_dependable = fileset.inversed_filter(IDependable)
        fileset = solver.solve(fileset)
        fileset.add(non_dependable)

        prj = ISEProject(ise=ise, top_mod=self.modules_pool.get_top_module())
        prj.add_files(fileset)
        prj.add_libs(fileset.get_libs())
        prj.add_initial_properties(syn_device=top_mod.syn_device,
            syn_grade = top_mod.syn_grade,
            syn_package = top_mod.syn_package,
            syn_top = top_mod.syn_top)

        prj.emit_xml(top_mod.syn_project)

    def __create_new_quartus_project(self):
        from dep_solver import DependencySolver
        from srcfile import IDependable
        from flow import ISEProject, ISEProjectProperty
        top_mod = self.modules_pool.get_top_module()
        fileset = self.modules_pool.build_global_file_list()
        solver = DependencySolver()
        non_dependable = fileset.inversed_filter(IDependable)
        fileset = solver.solve(fileset)
        fileset.add(non_dependable)
        
        prj = QuartusProject(top_mod.syn_project)
        prj.add_files(fileset)
        
        prj.add_initial_properties( top_mod.syn_device, 
                                   top_mod.syn_grade, 
                                   top_mod.syn_package, 
                                   top_mod.syn_top);
        prj.preflow = None
        prj.postflow = None
    
        prj.emit()

    def __update_existing_quartus_project(self):
        from dep_solver import DependencySolver
        from srcfile import IDependable
        top_mod = self.modules_pool.get_top_module()
        fileset = self.modules_pool.build_global_file_list()
        solver = DependencySolver()
        non_dependable = fileset.inversed_filter(IDependable)
        fileset = solver.solve(fileset)
        fileset.add(non_dependable)
        prj = QuartusProject(top_mod.syn_project)
        prj.read()
        prj.preflow = None
        prj.postflow = None
        prj.add_files(fileset)
        prj.emit()

    def run_local_synthesis(self):
        tm = self.modules_pool.get_top_module()
        if tm.target == "xilinx":
            if not os.path.exists("run.tcl"):
                self.__generate_tcl()
            os.system("xtclsh run.tcl");
        else:
            p.echo("Target " + tm.target + " is not synthesizable")

    def run_remote_synthesis(self):
        from srcfile import SourceFileFactory
        ssh = self.connection
        cwd = os.getcwd()

        p.vprint("The program will be using ssh connection: "+str(ssh))
        if not ssh.is_good():
            p.echo("SSH connection failure. Remote host doesn't response.")
            quit()

        if not os.path.exists(self.top_module.fetchto):
            p.echo("There are no modules fetched. Are you sure it's correct?")

        files = self.modules_pool.build_very_global_file_list()
        tcl = self.__search_tcl_file()
        if tcl == None:
            self.__generate_tcl()
            tcl = "run.tcl"

        sff = SourceFileFactory()
        files.add(sff.new(tcl))
        files.add(sff.new(self.top_module.syn_project))

        dest_folder = ssh.transfer_files_forth(files, dest_folder=self.top_module.syn_name)
        syn_cmd = "cd "+dest_folder+cwd+" && xtclsh run.tcl"

        p.vprint("Launching synthesis on " + str(ssh) + ": " + syn_cmd)
        ret = ssh.system(syn_cmd)
        if ret == 1:
            p.echo("Synthesis failed. Nothing will be transfered back")
            quit()

        cur_dir = os.path.basename(cwd)
        os.chdir("..")
        ssh.transfer_files_back(what=dest_folder+cwd, where=".")
        os.chdir(cur_dir)

    def __search_tcl_file(self, directory = None):
        if directory == None:
            directory = "."
        dir = os.listdir(directory)
        tcls = []
        for file in dir:
            file_parts = file.split('.')
            if file_parts[len(file_parts)-1] == "tcl":
                tcls.append(file)
        if len(tcls) == 0:
            return None
        if len(tcls) > 1:
            p.rawprint("Multiple tcls in the current directory!")
            p.rawprint(str(tcls))
            quit()
        return tcls[0]

    def __generate_tcl(self):
        f = open("run.tcl","w");
        f.write("project open " + self.top_module.syn_project + '\n')
        f.write("process run {Generate Programming File} -force rerun_all\n")
        f.close()

    def clean_modules(self):
        p.rawprint("Removing fetched modules..")
        remove_list = [m for m in self.modules_pool if m.source in ["svn", "git"] and m.isfetched]
        if len(remove_list):
            for m in remove_list:
                p.rawprint("\t" + m.url + " in " + m.path)
            for m in remove_list:
                m.remove_dir_from_disk()
        else:
            p.rawprint("There are no modules to be removed")

    def generate_fetch_makefile(self):
        pool = self.modules_pool

        if pool.get_fetchable_modules() == []:
            p.rawprint("There are no fetchable modules. No fetch makefile is produced")
            quit()

        if not pool.is_everything_fetched():
            p.echo("A module remains unfetched. Fetching must be done prior to makefile generation")
            quit()
        self.make_writer.generate_fetch_makefile(pool)
