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


"""Script for testing ganeti.hypervisor.hv_fake"""

import unittest

from ganeti import constants
from ganeti import objects
from ganeti import hypervisor

from ganeti.hypervisor import hv_fake

import testutils


class TestConsole(unittest.TestCase):
  def test(self):
    instance = objects.Instance(name="fake.example.com")
    node = objects.Node(name="fakenode.example.com", ndparams={})
    group = objects.NodeGroup(name="default", ndparams={})
    cons = hv_fake.FakeHypervisor.GetInstanceConsole(instance, node, group,
                                                     {}, {})
    self.assertEqual(cons.Validate(), None)
    self.assertEqual(cons.kind, constants.CONS_MESSAGE)


if __name__ == "__main__":
  testutils.GanetiTestProgram()
