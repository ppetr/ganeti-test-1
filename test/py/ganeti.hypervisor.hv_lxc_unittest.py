#!/usr/bin/python
#

# Copyright (C) 2011 Google Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.


"""Script for testing ganeti.hypervisor.hv_lxc"""

import unittest

from ganeti import constants
from ganeti import errors
from ganeti import objects
from ganeti import hypervisor
from ganeti import utils

from ganeti.hypervisor import hv_base
from ganeti.hypervisor import hv_lxc
from ganeti.hypervisor.hv_lxc import LXCHypervisor

import mock
import os
import shutil
import tempfile
import testutils
from testutils import patch_object


def setUpModule():
  # Creating instance of LXCHypervisor will fail by permission issue of
  # instance directories
  global temp_dir
  temp_dir = tempfile.mkdtemp()
  LXCHypervisor._ROOT_DIR = utils.PathJoin(temp_dir, "root")
  LXCHypervisor._LOG_DIR = utils.PathJoin(temp_dir, "log")


def tearDownModule():
  shutil.rmtree(temp_dir)


def RunResultOk(stdout):
  return utils.RunResult(0, None, stdout, "", [], None, None)


class LXCHypervisorTestCase(unittest.TestCase):
  """Used to test classes instantiating the LXC hypervisor class.

  """
  def setUp(self):
    self.ensure_fn = LXCHypervisor._EnsureDirectoryExistence
    LXCHypervisor._EnsureDirectoryExistence = mock.Mock(return_value=False)
    self.hv = LXCHypervisor()

  def tearDown(self):
    LXCHypervisor._EnsureDirectoryExistence = self.ensure_fn


class TestConsole(unittest.TestCase):
  def test(self):
    instance = objects.Instance(name="lxc.example.com",
                                primary_node="node199-uuid")
    node = objects.Node(name="node199", uuid="node199-uuid",
                        ndparams={})
    group = objects.NodeGroup(name="group991", ndparams={})
    cons = hv_lxc.LXCHypervisor.GetInstanceConsole(instance, node, group,
                                                   {}, {})
    self.assertEqual(cons.Validate(), None)
    self.assertEqual(cons.kind, constants.CONS_SSH)
    self.assertEqual(cons.host, node.name)
    self.assertEqual(cons.command[-1], instance.name)


class TestLXCIsInstanceAlive(unittest.TestCase):
  @patch_object(utils, "RunCmd")
  def testActive(self, runcmd_mock):
    runcmd_mock.return_value = RunResultOk("inst1 inst2 inst3\ninst4 inst5")
    self.assertTrue(LXCHypervisor._IsInstanceAlive("inst4"))

  @patch_object(utils, "RunCmd")
  def testInactive(self, runcmd_mock):
    runcmd_mock.return_value = RunResultOk("inst1 inst2foo")
    self.assertFalse(LXCHypervisor._IsInstanceAlive("inst2"))


class TestLXCHypervisorGetInstanceInfo(LXCHypervisorTestCase):
  def setUp(self):
    super(TestLXCHypervisorGetInstanceInfo, self).setUp()
    self.hv._GetCgroupCpuList = mock.Mock(return_value=[1, 3])
    self.hv._GetCgroupMemoryLimit = mock.Mock(return_value=128*(1024**2))

  @patch_object(LXCHypervisor, "_IsInstanceAlive")
  def testRunningInstance(self, isalive_mock):
    isalive_mock.return_value = True
    self.assertEqual(self.hv.GetInstanceInfo("inst1"),
                     ("inst1", 0, 128, 2, hv_base.HvInstanceState.RUNNING, 0))

  @patch_object(LXCHypervisor, "_IsInstanceAlive")
  def testInactiveOrNonexistentInstance(self, isalive_mock):
    isalive_mock.return_value = False
    self.assertEqual(self.hv.GetInstanceInfo("inst1"), None)


class TestCgroupMount(LXCHypervisorTestCase):
  @patch_object(utils, "GetMounts")
  @patch_object(LXCHypervisor, "_MountCgroupSubsystem")
  def testGetOrPrepareCgroupSubsysMountPoint(self, mntcgsub_mock, getmnt_mock):
    getmnt_mock.return_value = [
      ("/dev/foo", "/foo", "foo", "cpuset"),
      ("cpuset", "/sys/fs/cgroup/cpuset", "cgroup", "rw,relatime,cpuset"),
      ("devices", "/sys/fs/cgroup/devices", "cgroup", "rw,devices,relatime"),
      ("cpumem", "/sys/fs/cgroup/cpumem", "cgroup", "cpu,memory,rw,relatime"),
      ]
    mntcgsub_mock.return_value = "/foo"
    self.assertEqual(self.hv._GetOrPrepareCgroupSubsysMountPoint("cpuset"),
                     "/sys/fs/cgroup/cpuset")
    self.assertEqual(self.hv._GetOrPrepareCgroupSubsysMountPoint("devices"),
                     "/sys/fs/cgroup/devices")
    self.assertEqual(self.hv._GetOrPrepareCgroupSubsysMountPoint("cpu"),
                     "/sys/fs/cgroup/cpumem")
    self.assertEqual(self.hv._GetOrPrepareCgroupSubsysMountPoint("memory"),
                     "/sys/fs/cgroup/cpumem")
    self.assertEqual(self.hv._GetOrPrepareCgroupSubsysMountPoint("freezer"),
                     "/foo")
    mntcgsub_mock.assert_called_with("freezer")


class TestCgroupReadData(LXCHypervisorTestCase):
  cgroot = os.path.abspath(testutils.TestDataFilename("cgroup_root"))

  @patch_object(LXCHypervisor, "_CGROUP_ROOT_DIR", cgroot)
  def testGetCgroupMountPoint(self):
    self.assertEqual(self.hv._GetCgroupMountPoint(), self.cgroot)

  @patch_object(LXCHypervisor, "_PROC_SELF_CGROUP_FILE",
                testutils.TestDataFilename("proc_cgroup.txt"))
  def testGetCurrentCgroupSubsysGroups(self):
    expected_groups = {
      "memory": "", # root
      "cpuset": "some_group",
      "devices": "some_group",
      }
    self.assertEqual(self.hv._GetCurrentCgroupSubsysGroups(), expected_groups)

  @patch_object(LXCHypervisor, "_GetOrPrepareCgroupSubsysMountPoint")
  @patch_object(LXCHypervisor, "_GetCurrentCgroupSubsysGroups")
  def testGetCgroupInstanceSubsysDir(self, getcgg_mock, getmp_mock):
    getmp_mock.return_value = "/cg"
    getcgg_mock.return_value = {"cpuset": "grp"}
    self.assertEqual(self.hv._GetCgroupInstanceSubsysDir("instance1", "memory"),
                     "/cg/lxc/instance1")
    self.assertEqual(self.hv._GetCgroupInstanceSubsysDir("instance1", "cpuset"),
                     "/cg/grp/lxc/instance1")

  @patch_object(LXCHypervisor, "_GetCgroupInstanceSubsysDir")
  def testGetCgroupInstanceValue(self, getdir_mock):
    getdir_mock.return_value = utils.PathJoin(self.cgroot, "memory", "lxc",
                                              "instance1")
    self.assertEqual(self.hv._GetCgroupInstanceValue("instance1", "memory",
                                                     "memory.limit_in_bytes"),
                     "128")
    getdir_mock.return_value = utils.PathJoin(self.cgroot, "cpuset",
                                              "some_group", "lxc", "instance1")
    self.assertEqual(self.hv._GetCgroupInstanceValue("instance1", "cpuset",
                                                     "cpuset.cpus"),
                     "0-1")

  @patch_object(LXCHypervisor, "_GetCgroupInstanceValue")
  def testGetCgroupCpuList(self, getval_mock):
    getval_mock.return_value = "0-1"
    self.assertEqual(self.hv._GetCgroupCpuList("instance1"), [0, 1])

  @patch_object(LXCHypervisor, "_GetCgroupInstanceValue")
  def testGetCgroupMemoryLimit(self, getval_mock):
    getval_mock.return_value = "128"
    self.assertEqual(self.hv._GetCgroupMemoryLimit("instance1"), 128)


class TestVerifyLXCCommands(unittest.TestCase):
  def setUp(self):
    runcmd_mock = mock.Mock(return_value="")
    self.RunCmdPatch = patch_object(utils, "RunCmd", runcmd_mock)
    self.RunCmdPatch.start()
    version_patch = patch_object(LXCHypervisor, "_LXC_MIN_VERSION_REQUIRED",
                                 "1.2.3")
    self._LXC_MIN_VERSION_REQUIRED_Patch = version_patch
    self._LXC_MIN_VERSION_REQUIRED_Patch.start()
    self.hvc = LXCHypervisor

  def tearDown(self):
    self.RunCmdPatch.stop()
    self._LXC_MIN_VERSION_REQUIRED_Patch.stop()

  def testParseLXCVersion(self):
    self.assertEqual(self.hvc._ParseLXCVersion("1.0.0"), (1, 0, 0))
    self.assertEqual(self.hvc._ParseLXCVersion("1.0.0.alpha1"), (1, 0, 0))
    self.assertEqual(self.hvc._ParseLXCVersion("1.0"), None)
    self.assertEqual(self.hvc._ParseLXCVersion("1.2a.0"), None)

  @patch_object(LXCHypervisor, "_LXC_COMMANDS_REQUIRED", ["lxc-stop"])
  def testCommandVersion(self):
    utils.RunCmd.return_value = RunResultOk("1.2.3\n")
    self.assertFalse(self.hvc._VerifyLXCCommands())
    utils.RunCmd.return_value = RunResultOk("1.10.0\n")
    self.assertFalse(self.hvc._VerifyLXCCommands())
    utils.RunCmd.return_value = RunResultOk("1.2.2\n")
    self.assertTrue(self.hvc._VerifyLXCCommands())

  @patch_object(LXCHypervisor, "_LXC_COMMANDS_REQUIRED", ["lxc-stop"])
  def testCommandVersionInvalid(self):
    utils.RunCmd.return_value = utils.RunResult(1, None, "", "", [], None, None)
    self.assertTrue(self.hvc._VerifyLXCCommands())
    utils.RunCmd.return_value = RunResultOk("1.2a.0\n")
    self.assertTrue(self.hvc._VerifyLXCCommands())

  @patch_object(LXCHypervisor, "_LXC_COMMANDS_REQUIRED", ["lxc-stop"])
  def testCommandNotExists(self):
    utils.RunCmd.side_effect = errors.OpExecError
    self.assertTrue(self.hvc._VerifyLXCCommands())

  @patch_object(LXCHypervisor, "_LXC_COMMANDS_REQUIRED", ["lxc-ls"])
  def testVerifyLXCLs(self):
    utils.RunCmd.return_value = RunResultOk("garbage\n--running\ngarbage")
    self.assertFalse(self.hvc._VerifyLXCCommands())
    utils.RunCmd.return_value = RunResultOk("foo")
    self.assertTrue(self.hvc._VerifyLXCCommands())


if __name__ == "__main__":
  testutils.GanetiTestProgram()
