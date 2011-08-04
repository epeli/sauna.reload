# -*- coding: utf-8 -*-
# Copyright (c) 2011 University of Jyväskylä
#
# Authors:
#     Esa-Matti Suuronen <esa-matti@suuronen.org>
#     Asko Soukka <asko.soukka@iki.fi>
#
# This file is part of sauna.reload.
#
# sauna.reload is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# sauna.reload is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with sauna.reload.  If not, see <http://www.gnu.org/licenses/>.

import time
import os
import signal
import atexit

from zope.event import notify

from sauna.reload import autoinclude, fiveconfigure
from sauna.reload.db import FileStorageIndex
from sauna.reload.events import NewChildForked


class ForkLoop(object):

    def __init__(self):

        self.fork = True # Create child on start
        self.active = False
        self.pause = False
        self.killed_child = True
        self.forking = False

        self.parent_pid = os.getpid()
        self.child_pid = None

        # Timers
        self.boot_started = None
        self.child_started = None

    def isChild(self):
        return self.child_pid == 0

    def startBootTimer(self):
        if not self.boot_started:
            self.boot_started = time.time()

    def startChildBooTimer(self):
        self.child_started = time.time()

    def isChildAlive(self):

        if self.isChild():
            return True

        return (self.child_pid is not None
            and os.path.exists("/proc/%i" % self.child_pid))

    def _scheduleFork(self, signum=None, frame=None):
        self.fork = True

    def _childIsGoingToDie(self, signum=None, frame=None):
        self.killed_child = True

    def start(self):
        """
        Start fork loop.
        """

        self.active = True

        # SIGCHLD tells us that child process has really died and we can spawn
        # new child
        signal.signal(signal.SIGCHLD, self._waitChildToDieAndScheduleNew)
        signal.signal(signal.SIGUSR1, self._childIsGoingToDie)

        print "Fork loop starting on process", os.getpid()
        while True:
            self.forking = False

            if self.fork:
                self.fork = False

                if self.pause:
                    print "Pause mode, fork canceled"
                    continue

                if not self.killed_child:
                    print
                    print "Child died on bootup. Pausing fork loop for now. "
                    print "Fix possible errors and save edits and we'll try booting again."

                    # Child died because of unknown reason. Mark it as killed
                    # and go into pause mode.
                    self.killed_child = True
                    self.pause = True
                    continue


                if self.isChildAlive():
                    print "Child %i is still alive. Waiting it to die." % self.child_pid
                    continue

                self.forking = True
                self.startChildBooTimer()
                self.child_pid = os.fork()
                if self.child_pid == 0:
                    break
                self.killed_child = False

            time.sleep(1)

        self._prepareNewChild()
        notify(NewChildForked())
        self.forking = False

    def _prepareNewChild(self):
        """
        Prepare newly forked child. Make sure that it can properly read DB
        and install deferred products.
        """

        # Register exit listener. We cannot immediately spawn new child when we
        # get a modified event. Must wait that child has closed database etc.
        atexit.register(self._exitHandler)

        from Globals import DB
        db_index = FileStorageIndex(DB.storage)
        db_index.restore()

        autoinclude.include_deferred()
        fiveconfigure.install_deferred()

        print "Booted up new new child in %s seconds. Pid %s" % (
            time.time() - self.child_started, os.getpid())

    def spawnNewChild(self):
        """
        STEP 1 (parent): New child spawning starts by killing the current
        child.
        """

        # TODO: get rid of prints here. Use exceptions.

        if not self.active:
            print "Loop not started yet"
            return

        if self.forking:
            print "Serious forking action is already going on. Cannot fork now."
            return

        if self.child_pid is None:
            print "No killing yet. Not started child yet"
            return


        self.pause = False

        if not self.killed_child or self.isChild():
            print "sending SIGINT to child"
            self._killChild()
        else:
            # Ok, we already have sent the SIGINT the child, but asking for new child
            print "Not sending SIGINT because we already killed the child. Just scheduling new fork."
            self._scheduleFork()

        self.killed_child = True


    def _killChild(self):
        if self.isChild():
            print "Killing from child. Kill itself"
            # Signal parent that this is requested kill, not an error situation
            os.kill(self.parent_pid, signal.SIGUSR1)
            # Kill itself
            os.kill(os.getpid(), signal.SIGINT)
        else:
            os.kill(self.child_pid, signal.SIGINT)

    def _exitHandler(self):
        """
        STEP 2 (child): Child is about to die. Fix DB.
        """

        # TODO: Fetch adapter with interface
        # Must import here because we don't have DB on bootup yet
        from Globals import DB
        db_index = FileStorageIndex(DB.storage)
        db_index.save()


    def _waitChildToDieAndScheduleNew(self, signal, frame):
        """
        STEP 3 (parent): Child told us via SIGCHLD that we can spawn new child
        """

        # Acknowledge dead child
        os.wait()

        # Schedule new
        self._scheduleFork()

